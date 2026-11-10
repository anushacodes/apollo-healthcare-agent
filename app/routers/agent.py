import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.agent.seed_patient import get_case, list_cases
from app.config import settings
from app.review.extraction import with_reviewed_fields
from app.review.workflow import run_reviewable_analysis as run_graph_streaming

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/capabilities")
async def capabilities():
    return {"extended_diagnostics_enabled": settings.extended_diagnostics_enabled}


def analysis_request(payload: dict, patient_id: str) -> tuple[dict, str]:
    mode = payload.get("diagnostic_mode", "standard")
    if mode not in ("standard", "extended"):
        raise HTTPException(422, "Choose standard or extended diagnostic review")
    if mode == "extended" and not settings.extended_diagnostics_enabled:
        raise HTTPException(422, "Extended diagnostic review is disabled on this server")
    if "case" in payload:
        if not isinstance(payload["case"], str):
            raise HTTPException(422, "Case must be a case key string")
        patient = get_case(payload["case"])
        if not patient:
            raise HTTPException(404, "Case not found")
    else:
        patient = {key: value for key, value in payload.items() if key != "diagnostic_mode"}
        patient.setdefault("patient_id", patient_id)
    return patient, mode


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
    return with_reviewed_fields(case)


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
        if not isinstance(payload, dict):
            await websocket.send_json({"node": "__error__", "error": "Expected a JSON object"})
            return

        try:
            patient_data, diagnostic_mode = analysis_request(payload, patient_id)
        except HTTPException as exc:
            await websocket.send_json({"node": "__error__", "error": exc.detail})
            return

        # Send start acknowledgement
        await websocket.send_json({
            "node": "__start__",
            "audit_entry": f"Apollo agent pipeline started for patient {patient_id}.",
            "audit_log": [],
        })

        # Stream node-by-node
        async for event in run_graph_streaming(patient_data, diagnostic_mode):
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
    patient_data, diagnostic_mode = analysis_request(body, patient_id)

    audit_log = []
    final_summary = None
    diagnoses = {}
    interactions = {}
    calculator_results = []
    review_run = None

    async for event in run_graph_streaming(patient_data, diagnostic_mode):
        audit_log = event.get("audit_log", audit_log)
        if event.get("node") == "__review__":
            review_run = event["review_run"]
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
        "diagnostic_mode": diagnostic_mode,
        "review_run": review_run,
        "final_summary": final_summary,
        "diagnoses": diagnoses,
        "interactions": interactions,
        "calculator_results": calculator_results,
        "audit_log": audit_log,
    }
