from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from app.agent.rag_agent import run_rag_streaming
from app.agent.research_agent import fetch_pubmed
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
