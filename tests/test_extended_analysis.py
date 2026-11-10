import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.diagnostics.nodes import tool_node
from app.agent.diagnostics.state import AgentState
from app.config import settings
from app.review.store import audit_history, get_run
from app.review.workflow import create_draft
from tests.test_diagnostic_review import SOURCES, install
from tests.test_review import decision, start_reviewer


def patient():
    return {"patient_id": "extended-patient", "summary": {"summary_narrative": SOURCES["record/narrative"]["text"]}}


@pytest.mark.parametrize("mode", ["invalid", [], False, "extended"])
def test_invalid_or_disabled_mode_rejected_before_work(client, mode):
    assert client.post("/api/agent/run/demo", json={"case": "case_a", "diagnostic_mode": mode}).status_code == 422
    with client.websocket_connect("/api/agent/run/demo") as ws:
        ws.send_json({"case": "case_a", "diagnostic_mode": mode})
        assert ws.receive_json()["node"] == "__error__"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_capability_and_extended_http_persistence_and_review_gate(client, monkeypatch):
    assert client.get("/api/agent/capabilities").json() == {"extended_diagnostics_enabled": False}
    monkeypatch.setattr(settings, "extended_diagnostics_enabled", True)
    assert client.get("/api/agent/capabilities").json() == {"extended_diagnostics_enabled": True}
    calls = install(monkeypatch)
    response = client.post("/api/agent/run/extended-patient", json={**patient(), "diagnostic_mode": "extended"})
    assert response.status_code == 200
    run = response.json()["review_run"]
    assert run["analysis"]["diagnostic_mode"] == "extended"
    assert run["analysis"]["diagnoses"]["_diagnostic_review"]["status"] == "complete"
    assert len(calls) == 4
    stored = get_run(run["id"], internal=True)
    assert "diagnostic_mode" not in stored["patient_data"]
    assert client.get(f"/api/review/runs/{run['id']}").json()["analysis"] == run["analysis"]
    start_reviewer(client)
    assert client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]}).status_code == 409
    uncertainty = next(f for f in run["findings"] if f["kind"] == "diagnostic_review")
    assert decision(client, run, uncertainty).status_code == 422
    for finding in run["findings"]:
        current = decision(client, run, finding, action="rejected")
        assert current.status_code == 200
        run = current.json()
    assert client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]}).status_code == 200
    assert audit_history(run["id"])["chain_valid"]


def test_extended_websocket_and_default_compatibility(client, monkeypatch):
    monkeypatch.setattr(settings, "extended_diagnostics_enabled", True)
    install(monkeypatch)
    with client.websocket_connect("/api/agent/run/extended-patient") as ws:
        ws.send_json({**patient(), "diagnostic_mode": "extended"})
        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["node"] == "__done__":
                break
        assert any(e.get("diagnoses", {}).get("_diagnostic_review", {}).get("status") == "complete" for e in events)
        saved = next(e["review_run"] for e in events if e["node"] == "__review__")
        assert saved["analysis"]["diagnostic_mode"] == "extended"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    standard = client.post("/api/agent/run/demo", json={"case": "case_b"}).json()
    assert standard["diagnostic_mode"] == "standard"
    assert "_diagnostic_review" not in standard["diagnoses"]


def test_calculator_resume_retains_extended_mode_and_invalidates_decisions(client, monkeypatch):
    monkeypatch.setattr(settings, "extended_diagnostics_enabled", True)
    result = tool_node(AgentState(extracted_params={"calculator_calls": [{
        "tool": "ascvd_risk_calculator", "params": {"age": 60, "total_cholesterol": 190,
        "hdl_cholesterol": 45, "sex": "male", "race": "white", "on_bp_treatment": False,
        "is_smoker": False, "has_diabetes": False},
    }]}))
    run = create_draft(patient(), {**result, "diagnostic_mode": "extended"})
    start_reviewer(client)
    calls = install(monkeypatch)
    q = run["clarifications"][0]
    response = client.post(f"/api/review/runs/{run['id']}/clarifications/{q['id']}", json={
        "version": run["version"], "action": "answer", "values": {"systolic_bp": 120}, "reason": "Recorded BP",
    })
    assert response.status_code == 200
    updated = response.json()
    assert updated["analysis"]["diagnostic_mode"] == "extended"
    assert updated["analysis"]["diagnoses"]["_diagnostic_review"]["status"] == "complete"
    assert len(calls) == 4
    assert all(f["status"] == "pending" for f in updated["findings"] if f["kind"] in ("diagnosis", "diagnostic_review", "investigation"))
    assert audit_history(run["id"])["chain_valid"]
