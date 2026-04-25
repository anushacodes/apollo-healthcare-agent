from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from app.agent.graph import run_graph_streaming
from app.agent.seed_patient import get_case, list_cases

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/cases")
async def get_cases():
    """List available pre-loaded demo cases."""
    return {"cases": list_cases()}


@router.get("/cases/{case_key}")
async def get_case_data(case_key: str):
    """Return the full patient data dict for a demo case."""
    case = get_case(case_key)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_key}' not found.")
    return case


@router.websocket("/run/{patient_id}")
async def run_agent_ws(websocket: WebSocket, patient_id: str):
    """
    WebSocket endpoint for streaming agent execution.

    Client sends: JSON patient_data dict (or {"case": "case_a"} to use a demo case)
    Server streams: JSON events after each node completes, each containing:
      - node: str
      - audit_entry: str
      - audit_log: list[str]
      - data: dict (node-specific partial state)

    Final event has node="summarizer" and includes final_summary.
    """
    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)

        # Allow client to send {"case": "case_a"} as a shorthand
        if "case" in payload:
            patient_data = get_case(payload["case"])
            if not patient_data:
                await websocket.send_json({"error": f"Case '{payload['case']}' not found"})
                await websocket.close()
                return
        else:
            patient_data = payload
            patient_data.setdefault("patient_id", patient_id)

        # Send start acknowledgement
        await websocket.send_json({
            "node": "__start__",
            "audit_entry": f"Apollo agent pipeline started for patient {patient_id}.",
            "audit_log": [],
        })

        # Stream node-by-node
        async for event in run_graph_streaming(patient_data):
            await websocket.send_json(event)

        # Signal completion
        await websocket.send_json({
            "node": "__done__",
            "audit_entry": "Pipeline complete.",
            "audit_log": [],
        })

    except WebSocketDisconnect:
        log.info(f"[ws] Client disconnected for patient {patient_id}")
    except Exception as exc:
        log.error(f"[ws] Error for patient {patient_id}: {exc}")
        try:
            await websocket.send_json({"node": "__error__", "error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/run/{patient_id}")
async def run_agent_http(patient_id: str, body: dict):
    """
    HTTP fallback for environments that don't support WebSockets.
    Runs the full graph and returns the complete final state (no streaming).
    """
    if "case" in body:
        patient_data = get_case(body["case"])
        if not patient_data:
            raise HTTPException(status_code=404, detail=f"Case '{body['case']}' not found.")
    else:
        patient_data = body
        patient_data.setdefault("patient_id", patient_id)

    audit_log = []
    final_summary = None
    diagnoses = {}
    interactions = {}
    calculator_results = []

    async for event in run_graph_streaming(patient_data):
        audit_log = event.get("audit_log", audit_log)
        if event.get("node") == "summarizer":
            final_summary = event.get("final_summary")
        if event.get("diagnoses"):
            diagnoses = event["diagnoses"]
        if event.get("interactions"):
            interactions = event["interactions"]
        if event.get("calculator_results"):
            calculator_results = event["calculator_results"]

    return {
        "patient_id": patient_id,
        "final_summary": final_summary,
        "diagnoses": diagnoses,
        "interactions": interactions,
        "calculator_results": calculator_results,
        "audit_log": audit_log,
    }
