from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.agent.rag_agent import run_rag_streaming
from app.agent.research_agent import fetch_pubmed, prefetch_pubmed_background
from app.agent.sqlite_cache import hash_text, mark_document_indexed
from app.agent.seed_patient import get_case

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

        # ⚡ Background prefetch — fire PubMed fetch in a background thread NOW,
        # so that by the time the RAG pipeline hits research_fetcher the papers
        # are already cached / embedded and the node returns instantly.
        diagnoses = [
            d.get("name", "") if isinstance(d, dict) else str(d)
            for d in patient_data.get("summary", {}).get("diagnoses", [])
        ]
        prefetch_pubmed_background(patient_id, diagnoses, question)

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


@router.get("/research/{patient_id}")
async def get_research(patient_id: str, case_key: str | None = None):
    """
    Fetch and return PubMed papers for a patient's diagnoses.
    Papers are embedded into Qdrant for subsequent RAG queries.
    """
    patient_data: dict = {}
    if case_key:
        patient_data = get_case(case_key) or {}

    diagnoses = [
        d.get("name", "") if isinstance(d, dict) else str(d)
        for d in patient_data.get("summary", {}).get("diagnoses", [])
    ]
    if not diagnoses:
        raise HTTPException(400, "No diagnoses found for this patient")

    papers = fetch_pubmed(patient_id, diagnoses)
    return {
        "patient_id":  patient_id,
        "paper_count": len(papers),
        "papers": [
            {
                "pmid":    p["pmid"],
                "title":   p["title"],
                "journal": p["journal"],
                "year":    p["year"],
                "doi":     p["doi"],
                "url":     p["url"],
                "abstract_snippet": p["abstract"][:300] + "..." if len(p["abstract"]) > 300 else p["abstract"],
            }
            for p in papers
        ],
    }


@router.post("/ingest/{patient_id}")
async def ingest_document(patient_id: str, file: UploadFile = File(...)):
    import tempfile
    import os
    from app.ingestion.parser import parse_document
    from app.ingestion.chunker import chunk_text
    from app.ingestion.embedder import embed_chunks

    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Parse
        if suffix.lower() == ".txt":
            from app.ingestion.extractors import ExtractionResult

            text = content.decode("utf-8", errors="ignore")
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
            result = parse_document(tmp_path)
            
        os.remove(tmp_path)

        # Chunk and Embed
        chunks = chunk_text(result.text, patient_id, file.filename)
        upserted = embed_chunks(chunks)
        mark_document_indexed(
            patient_id,
            file.filename,
            hash_text(result.text),
            chunk_count=len(chunks),
        )

        return {"status": "success", "file": file.filename, "chunks_embedded": upserted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sources/{patient_id}")
async def get_sources(patient_id: str):
    from app.ingestion.embedder import _get_client, _COLLECTION
    from qdrant_client.models import Filter, FieldCondition, MatchValue
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
