import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.agent.rag_agent import run_rag_streaming
from app.agent.seed_patient import get_case
from app.agent.sqlite_cache import hash_text, mark_document_indexed
from app.config import settings

_UPLOAD_CHUNK_SIZE = 1024 * 1024

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


class AskRequest(BaseModel):
    patient_id: str
    question:   str
    case_key:   str | None = None   # if set, load demo patient data


@router.websocket("/stream/{patient_id}")
async def rag_stream(websocket: WebSocket, patient_id: str):
    """
    WebSocket — streams RAG pipeline thinking + result events.
    Client sends: JSON {"question": "...", "case_key": "case_a"|null}
    Server sends: sequence of {type, node, message, data} events
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        question = payload.get("question", "").strip()
        case_key = payload.get("case_key")

        if not question:
            await websocket.send_json({"type": "error", "message": "Empty question"})
            return

        # Load patient data
        patient_data: dict = {}
        if case_key:
            patient_data = get_case(case_key) or {}
        if not patient_data:
            patient_data = {"patient_id": patient_id, "patient": {}, "summary": {}, "source_documents": {}}

        patient_data.setdefault("patient_id", patient_id)

        async for event in run_rag_streaming(patient_id, patient_data, question):
            await websocket.send_json(event)

    except WebSocketDisconnect:
        log.info("[rag_ws] Client disconnected: %s", patient_id)
    except Exception as exc:
        log.error("[rag_ws] Error for %s: %s", patient_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


async def _read_upload_capped(file: UploadFile) -> bytes:
    """Stream the upload in chunks, rejecting it as soon as it crosses the
    configured cap instead of buffering an unbounded body into memory first."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    parts: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit",
            )
        parts.append(chunk)
    return b"".join(parts)


def _decode_text(content: bytes) -> str:
    """Detect actual encoding instead of assuming UTF-8 and silently dropping
    bytes that don't fit (the old `errors='ignore'` behavior)."""
    from charset_normalizer import from_bytes

    best_guess = from_bytes(content).best()
    if best_guess is not None:
        return str(best_guess)
    log.warning("[rag] Could not detect encoding, falling back to utf-8 with replacement")
    return content.decode("utf-8", errors="replace")


@router.post("/ingest/{patient_id}")
async def ingest_document(patient_id: str, file: UploadFile = File(...)):
    import os
    import tempfile

    from app.ingestion.chunker import chunk_text
    from app.ingestion.embedder import embed_chunks_async
    from app.ingestion.parser import parse_document_async

    content = await _read_upload_capped(file)

    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Parse
            if suffix.lower() == ".txt":
                from app.ingestion.extractors import ExtractionResult

                text = _decode_text(content)
                result = ExtractionResult(
                    source_path=file.filename,
                    extractor_type="text",
                    text=text,
                    tables=[],
                    sections=[],
                    metadata={},
                    ocr_notes=[],
                    confidence=1.0,
                    needs_ocr_fallback=False,
                    formatted_output=text,
                )
            else:
                result = await parse_document_async(tmp_path)
        finally:
            os.remove(tmp_path)

        # Chunk and Embed
        chunks = chunk_text(result.text, patient_id, file.filename)
        upserted = await embed_chunks_async(chunks)
        mark_document_indexed(
            patient_id,
            file.filename,
            hash_text(result.text),
            chunk_count=len(chunks),
        )

        return {"status": "success", "file": file.filename, "chunks_embedded": upserted}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sources/{patient_id}")
async def get_sources(patient_id: str):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from app.ingestion.embedder import _COLLECTION, _get_client
    client = _get_client()
    if not client:
        return {"sources": []}
        
    try:
        must = [FieldCondition(key="patient_id", match=MatchValue(value=patient_id))]
        results = client.scroll(
            collection_name=_COLLECTION,
            scroll_filter=Filter(must=must),
            limit=500,
            with_payload=True,
            with_vectors=False
        )[0]
        sources = list({r.payload.get("source_doc") for r in results if r.payload.get("source_doc")})
        return {"sources": sources}
    except Exception as exc:
        log.error("[rag] GET sources failed: %s", exc)
        return {"sources": []}
