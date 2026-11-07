import asyncio
import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.agent.rag.graph import run_rag_streaming
from app.agent.seed_patient import get_case
from app.agent.sqlite_cache import hash_text, mark_document_indexed
from app.config import settings
from app.review.extraction import create_extraction, with_reviewed_fields

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
        if not isinstance(payload, dict):
            await websocket.send_json({"type": "error", "message": "Expected a JSON object"})
            return
        if not isinstance(payload.get("question", ""), str):
            await websocket.send_json({"type": "error", "message": "Question must be a string"})
            return
        question = payload.get("question", "").strip()
        case_key = payload.get("case_key")

        if not question:
            await websocket.send_json({"type": "error", "message": "Empty question"})
            return

        # Load patient data
        patient_data: dict = {}
        if case_key:
            patient_data = get_case(case_key) if isinstance(case_key, str) else None
            if not patient_data:
                await websocket.send_json({"type": "error", "message": "Unknown demo case"})
                return
        if not patient_data:
            patient_data = {"patient_id": patient_id, "patient": {}, "summary": {}, "source_documents": {}}

        patient_data.setdefault("patient_id", patient_id)
        patient_data = await asyncio.to_thread(with_reviewed_fields, patient_data)

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
    finally:
        try:
            await websocket.close()
        except RuntimeError:
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

    filename = file.filename or ""
    if not filename or not os.path.basename(filename):
        raise HTTPException(status_code=400, detail="A filename is required")
    filename = os.path.basename(filename)
    from app.ingestion.parser import is_supported

    if not is_supported(filename):
        raise HTTPException(status_code=415, detail="Unsupported file type")
    content = await _read_upload_capped(file)
    if not content:
        raise HTTPException(status_code=422, detail="File is empty")

    try:
        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Parse
            if suffix.lower() == ".txt":
                from app.ingestion.extractors import ExtractionResult

                text = _decode_text(content)
                result = ExtractionResult(
                    source_path=filename,
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
        chunks = chunk_text(result.text, patient_id, filename)
        if not chunks:
            raise HTTPException(status_code=422, detail="No indexable text found in this document")
        upserted = await embed_chunks_async(chunks)
        mark_document_indexed(
            patient_id,
            filename,
            hash_text(result.text),
            chunk_count=len(chunks),
        )

        # Retrieval keeps its existing upload behavior. Structured proposals remain a draft
        # until a named reviewer decides every field and finalizes the extraction.
        review_run = await asyncio.to_thread(create_extraction, patient_id, filename, result.text)
        return {"status": "success", "file": filename, "chunks_indexed": len(chunks),
                "chunks_embedded": upserted, "review_run": review_run}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("[rag] Document ingestion failed")
        raise HTTPException(status_code=500, detail="Document ingestion failed") from exc


@router.get("/sources/{patient_id}")
async def get_sources(patient_id: str):
    from app.agent.sqlite_cache import list_document_sources

    return {"sources": await asyncio.to_thread(list_document_sources, patient_id)}
