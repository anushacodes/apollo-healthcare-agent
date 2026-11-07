import json

import pytest

from app.agent.diagnostics.nodes import tool_node
from app.agent.diagnostics.state import AgentState
from app.agent.sqlite_cache import _get_conn
from app.review.evidence import assertion_at
from app.review.store import audit_history, get_run
from app.review.workflow import create_draft


@pytest.fixture
def draft():
    patient = {"patient_id": "review-patient", "patient": {"name": "Test"}, "summary": {
        "diagnoses": [{"name": "Diabetes", "status": "active"}, {"name": "Asthma", "status": "resolved"}],
    }, "source_documents": {"note": "No pneumonia. History of asthma. Diabetes is documented."}}
    return create_draft(patient, {"diagnoses": {"proposed_diagnoses": [
        {"name": "Pneumonia", "reasoning": "Model suggestion"}, {"name": "Unsubstantiated condition"},
    ]}})


def start_reviewer(client, name="Test Reviewer"):
    response = client.post("/api/review/session", json={"name": name})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    return response.json()["reviewer"]


def decision(client, run, finding, action="accepted", **kwargs):
    return client.post(f"/api/review/runs/{run['id']}/findings/{finding['id']}/decision", json={
        "version": run["version"], "action": action, "reason": "Checked source passage", **kwargs,
    })


def test_draft_has_assertions_and_exact_provenance(draft):
    findings = {f["title"]: f for f in draft["findings"]}
    assert findings["Diabetes"]["assertion"] == "documented"
    assert findings["Asthma"]["assertion"] == "historical"
    assert findings["Pneumonia"]["assertion"] == "negated"
    assert findings["Unsubstantiated condition"]["assertion"] == "ai_suggested"
    assert not findings["Unsubstantiated condition"]["evidence"]
    for finding in draft["findings"]:
        for evidence in finding["evidence"]:
            source = draft["sources"][evidence["source_id"]]["text"]
            assert source[evidence["start"]:evidence["end"]] == evidence["quote"]


@pytest.mark.parametrize("text,term,expected", [
    ("No diabetes. Hypertension documented.", "Hypertension", "documented"),
    ("No diabetes, but hypertension present.", "hypertension", "documented"),
    ("History of asthma, now resolved.", "asthma", "historical"),
    ("Possible pneumonia.", "pneumonia", "suspected"),
    ("Pneumonia is ruled out.", "Pneumonia", "negated"),
])
def test_assertion_scope(text, term, expected):
    start = text.index(term)
    assert assertion_at(text, start, start + len(term)) == expected


def test_review_identity_and_finalization_are_enforced(client, draft):
    base = f"/api/review/runs/{draft['id']}"
    assert client.get(base + "/final").status_code == 409
    assert client.post(base + "/finalize", json={"version": 1}).status_code == 401
    assert decision(client, draft, draft["findings"][0]).status_code == 401
    identity = start_reviewer(client)
    assert client.post(base + "/finalize", json={"version": 1}).status_code == 409
    forged = decision(client, draft, draft["findings"][0], reviewer={"name": "Someone else"})
    assert forged.status_code == 422
    updated = decision(client, draft, draft["findings"][0]).json()
    assert updated["findings"][0]["decision"]["reviewer"] == identity
    assert decision(client, draft, draft["findings"][0]).status_code == 409


def test_review_persists_edits_and_rejects_in_final_output(client, draft):
    start_reviewer(client)
    original = draft["findings"][0]["original_text"]
    assert decision(client, draft, draft["findings"][0], action="edited", edited_text=" ").status_code == 422
    current = decision(client, draft, draft["findings"][0], action="edited", edited_text="Corrected finding").json()
    for finding in current["findings"][1:]:
        current = decision(client, current, finding, action="rejected").json()
    base = f"/api/review/runs/{draft['id']}"
    response = client.post(base + "/finalize", json={"version": current["version"]})
    assert response.status_code == 200
    assert response.json()["status"] == "finalized"
    final = client.get(base + "/final").json()
    assert len(final["findings"]) == 1
    assert final["findings"][0]["text"] == "Corrected finding"
    assert final["findings"][0]["original_text"] == original
    assert decision(client, response.json(), response.json()["findings"][0]).status_code == 409
    assert get_run(draft["id"])["status"] == "finalized"
    assert client.get("/api/review/patients/review-patient/runs").json()["runs"][0]["id"] == draft["id"]
    assert audit_history(draft["id"])["chain_valid"] is True


def test_unsupported_finding_requires_edit_reject_or_clarification(client, draft):
    start_reviewer(client)
    finding = next(f for f in draft["findings"] if not f["evidence"])
    assert decision(client, draft, finding).status_code == 422
    current = decision(client, draft, finding, action="clarification_requested").json()
    q = current["clarifications"][0]
    assert current["status"] == "needs_clarification"
    assert decision(client, current, finding, action="rejected").status_code == 409
    response = client.post(f"/api/review/runs/{draft['id']}/clarifications/{q['id']}/response", json={
        "version": current["version"], "response": "Reviewer confirms this was a documentation error",
    })
    assert response.status_code == 200
    revised = response.json()
    linked = next(f for f in revised["findings"] if f["id"] == finding["id"])
    assert linked["status"] == "pending"
    assert linked["evidence"][0]["assertion"] == "reviewer_supplied"
    assert linked["assertion"] == "ai_suggested"  # Human text does not rewrite provenance.
    assert decision(client, revised, linked, action="rejected").status_code == 200


def calculator_draft():
    patient = {"patient_id": "calculator-patient", "summary": {}, "patient": {}, "source_documents": {}}
    result = tool_node(AgentState(extracted_params={"calculator_calls": [{
        "tool": "ascvd_risk_calculator", "params": {"age": 60, "total_cholesterol": 190,
        "hdl_cholesterol": 45, "sex": "male", "race": "white", "on_bp_treatment": False,
        "is_smoker": False, "has_diabetes": False},
    }]}))
    assert result["calculator_results"][0]["status"] == "needs_input"
    return create_draft(patient, result)


@pytest.mark.parametrize("action", ["answer", "skip"])
def test_calculator_clarification_is_validated_resumed_and_saved(client, action):
    draft = calculator_draft()
    start_reviewer(client)
    q = draft["clarifications"][0]
    base = f"/api/review/runs/{draft['id']}"
    assert [field["name"] for field in q["fields"]] == ["systolic_bp"]
    assert client.post(base + "/finalize", json={"version": 1}).status_code == 409
    invalid = client.post(base + f"/clarifications/{q['id']}", json={
        "version": 1, "action": "answer", "values": {"systolic_bp": -10}, "reason": "Checked record",
    })
    assert invalid.status_code == 422
    response = client.post(base + f"/clarifications/{q['id']}", json={
        "version": 1, "action": action, "values": {"systolic_bp": 120} if action == "answer" else {},
        "reason": "Recorded BP" if action == "answer" else "Unable to obtain BP",
    })
    assert response.status_code == 200
    run = response.json()
    assert run["clarifications"][0]["status"] == ("answered" if action == "answer" else "skipped")
    result = run["analysis"]["calculator_results"][0]
    assert result["status"] == ("complete" if action == "answer" else "skipped")
    assert audit_history(draft["id"])["chain_valid"] is True
    if action == "answer":
        assert result["inputs"]["systolic_bp"] == 120
        assert any(f["kind"] == "calculator" for f in run["findings"])
    stored = get_run(draft["id"], internal=True)
    assert stored["original_analysis"]["calculator_results"][0]["status"] == "needs_input"


def test_reviewer_session_cannot_be_forged_or_cross_origin(client, draft):
    client.cookies.set("apollo_reviewer", "not-a-valid-session")
    assert decision(client, draft, draft["findings"][0]).status_code == 401
    assert client.post("/api/review/session", json={"name": "Reviewer"},
                       headers={"Origin": "https://untrusted.example"}).status_code == 403


def test_audit_detects_mutation(draft):
    assert audit_history(draft["id"])["chain_valid"] is True
    with _get_conn() as conn:
        row = conn.execute("SELECT seq, payload FROM review_events WHERE run_id = ?", (draft["id"],)).fetchone()
        payload = json.loads(row["payload"])
        payload["event"] = "tampered"
        conn.execute("UPDATE review_events SET payload = ? WHERE seq = ?", (json.dumps(payload), row["seq"]))
    assert audit_history(draft["id"])["chain_valid"] is False


def test_scoped_run_and_source_lookup(client, draft):
    assert client.get("/api/review/patients/other/runs").json() == {"runs": []}
    assert client.get("/api/review/runs/does-not-exist").status_code == 404
    assert client.get(f"/api/review/runs/{draft['id']}/sources/record/diagnoses/0").status_code == 200
    assert client.get(f"/api/review/runs/{draft['id']}/sources/../secret").status_code == 404


def test_analysis_api_saves_reviewable_run(client):
    response = client.post("/api/agent/run/demo-case-b", json={"case": "case_b"})
    assert response.status_code == 200
    run = response.json()["review_run"]
    assert run["findings"]
    assert client.get(f"/api/review/runs/{run['id']}").json()["status"] == run["status"]


def test_generated_reasoning_is_retained_for_documented_diagnosis():
    run = create_draft({"patient_id": "reasoning", "summary": {"diagnoses": [{"name": "Diabetes"}]}}, {
        "diagnoses": {"proposed_diagnoses": [{"name": "Diabetes", "reasoning": "Specific model interpretation"}]},
    })
    finding = run["findings"][0]
    assert finding["assertion"] == "documented"
    assert "Specific model interpretation" in finding["original_text"]


def test_conflict_cannot_be_accepted_unchanged(client):
    run = create_draft({"patient_id": "conflict", "summary": {"diagnoses": [{"name": "Diabetes"}]},
                        "source_documents": {"note": "No diabetes."}}, {})
    start_reviewer(client)
    assert run["findings"][0]["assertion"] == "conflicting"
    assert decision(client, run, run["findings"][0]).status_code == 422


def test_missing_boolean_criterion_is_not_defaulted():
    result = tool_node(AgentState(extracted_params={"calculator_calls": [{
        "tool": "wells_dvt_score", "params": {"active_cancer": False},
    }]}))["calculator_results"][0]
    assert result["status"] == "needs_input"
    assert len(result["missing_fields"]) == 9
    assert "result" not in result


def test_reviewer_evidence_remains_distinct():
    from app.review.evidence import evidence_for
    sources = {"human": {"label": "Clarification", "text": "Diabetes confirmed by reviewer", "kind": "reviewer_supplied"}}
    assert evidence_for("Diabetes", sources)[0]["assertion"] == "reviewer_supplied"
