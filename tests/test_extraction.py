import copy
import json

import pytest
from pydantic import ValidationError

from app.agent.seed_patient import get_case
from app.agent.summarizer import build_context
from app.ingestion.evaluate_extraction import DEFAULT_CASES, evaluate
from app.ingestion.structured import ExtractedField, extract_fields
from app.review.extraction import with_reviewed_fields
from app.review.store import audit_history


def draft(client, patient_id="extraction-patient", text="Diagnosis: Hypertension\nMedication: Ramipril 5mg daily"):
    response = client.post(f"/api/review/patients/{patient_id}/extract", json={
        "source_name": "Synthetic clinic letter", "text": text,
    })
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, run, finding, action="accepted", **extra):
    return client.post(f"/api/review/runs/{run['id']}/findings/{finding['id']}/decision", json={
        "version": run["version"], "action": action, "reason": "Checked against source document", **extra,
    })


def fields(client, patient_id="extraction-patient"):
    return client.get(f"/api/review/patients/{patient_id}/fields").json()["fields"]


def test_labeled_extraction_cases_and_metric_detects_wrong_labels():
    cases = json.loads(DEFAULT_CASES.read_text())
    report = evaluate(cases)
    assert report["passed"] == report["cases"] == 10
    assert report["field_precision"] == report["field_recall"] == 1
    assert report["exact_spans"] == {"correct": 23, "total": 23}
    incorrect = copy.deepcopy(cases)
    incorrect[0]["expected"][0]["data"]["value"] = "1990-01-01"
    assert evaluate(incorrect)["passed"] == 9


def test_existing_case_a_lab_extraction_preserves_results_and_offsets():
    patient = get_case("case_a")
    text = patient["source_documents"]["labs"]
    result = extract_fields(text)
    labs = {field["data"]["test_name"]: field["data"] for field in result["fields"] if field["kind"] == "lab"}
    assert labs["Creatinine"]["value"] == "142"
    assert labs["Creatinine"]["unit"] == "µmol/L"
    assert labs["Creatinine"]["flag"] == "high"
    assert labs["Creatinine"]["date"] == "2023-11-20"
    assert labs["Complement C3"]["value"] == "0.65"
    assert labs["Complement C3"]["flag"] == "low"
    assert labs["INR"]["flag"] == "not_recorded"  # A tick is not a normal-range claim.
    for field in result["fields"]:
        assert text[field["start"]:field["end"]] == field["quote"]


def test_only_finalized_corrected_fields_enter_patient_record(client):
    run = draft(client)
    assert fields(client) == []
    assert decide(client, run, run["findings"][0]).status_code == 401
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    assert client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": 1}).status_code == 409
    medication = next(f for f in run["findings"] if f["extracted"]["kind"] == "medication")
    corrected = {**medication["extracted"]["data"], "dose": "2.5mg"}
    run = decide(client, run, medication, "edited", edited_data=corrected).json()
    assert fields(client) == []
    original = next(f for f in run["findings"] if f["id"] == medication["id"])
    assert original["extracted"]["data"]["dose"] == "5mg"
    diagnosis = next(f for f in run["findings"] if f["extracted"]["kind"] == "diagnosis")
    run = decide(client, run, diagnosis, "rejected").json()
    assert fields(client) == []
    final = client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]})
    assert final.status_code == 200
    saved = fields(client)
    assert len(saved) == 1
    assert saved[0]["data"]["dose"] == "2.5mg"
    assert saved[0]["quote"] == "Medication: Ramipril 5mg daily"
    assert saved[0]["reviewer"]["name"] == "Taylor Reviewer"
    final_fields = client.get(f"/api/review/runs/{run['id']}/final").json()["findings"]
    assert final_fields[0]["extracted"]["data"]["dose"] == "2.5mg"
    assert audit_history(run["id"])["chain_valid"]
    assert decide(client, final.json(), medication).status_code == 409
    assert fields(client, "another-patient") == []
    # Closing/reopening a connection retains the committed fields.
    from app.agent import sqlite_cache
    sqlite_cache._local.conn.close()
    del sqlite_cache._local.conn
    assert fields(client) == saved


def test_structured_edits_are_validated_and_versions_enforced(client):
    run = draft(client)
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    finding = run["findings"][0]
    assert decide(client, run, finding, "edited", edited_text="Free text").status_code == 422
    assert decide(client, run, finding, "edited", edited_data={"name": "", "status": "active"}).status_code == 422
    assert decide(client, run, finding, "edited", edited_data={"name": "Hypertension", "status": "documented", "injected": "value"}).status_code == 422
    assert decide(client, run, finding, edited_data=finding["extracted"]["data"]).status_code == 422
    updated = decide(client, run, finding).json()
    assert updated["version"] == 2
    assert decide(client, run, finding).status_code == 409


def test_conflicting_fields_require_explicit_correction_or_rejection(client):
    run = draft(client, text="Diagnosis: Hypertension\nDiagnosis: No hypertension")
    assert all(f["assertion"] == "conflicting" for f in run["findings"])
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    assert decide(client, run, run["findings"][0]).status_code == 422
    assert fields(client) == []


def test_patient_name_mismatch_is_visible_and_cannot_be_accepted(client):
    patient = get_case("case_a")
    run = draft(client, patient["patient_id"], text="Patient: Different Person")
    assert run["findings"][0]["assertion"] == "conflicting"
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    assert decide(client, run, run["findings"][0]).status_code == 422


def test_saved_runs_are_separated_and_duplicate_imports_are_idempotent(client):
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    for _ in range(2):
        run = draft(client, text="Diagnosis: Hypertension")
        run = decide(client, run, run["findings"][0]).json()
        assert client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]}).status_code == 200
    assert len(fields(client)) == 1
    assert client.get("/api/review/patients/extraction-patient/runs").json()["runs"] == []
    assert len(client.get("/api/review/patients/extraction-patient/runs?kind=extraction").json()["runs"]) == 2


def test_reviewed_fields_reach_record_and_context_without_replacing_current_medications(client):
    patient = get_case("case_a")
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    run = draft(client, patient["patient_id"], text="Discharge medications:\n- Prednisolone 60mg daily")
    run = decide(client, run, run["findings"][0]).json()
    client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]})
    record = client.get("/api/agent/cases/case_a").json()
    assert record["summary"]["medications"] == patient["summary"]["medications"]
    assert record["summary"]["reviewed_fields"][0]["data"]["status"] == "historical"
    assert "historical" in build_context(record)
    from app.agent.rag.nodes import _build_patient_summary_chunk
    assert "REVIEWED DOCUMENT FIELDS" in _build_patient_summary_chunk(record, patient["patient_id"])["text"]
    from app.agent.rag.nodes import _format_chunks, context_assembler_node
    from app.agent.rag.state import RAGState
    context = context_assembler_node(RAGState(patient_id=patient["patient_id"], patient_data=record,
                                            question="What does the reviewed prednisolone prescription say?"))
    prompt = _format_chunks(context["all_chunks"])
    assert "historical" in prompt and "60mg" in prompt
    assert any(chunk["doc_type"] == "reviewed_document_field" for chunk in context["all_chunks"])
    forged = {"patient_id": "someone-else", "summary": {"reviewed_fields": [{"data": "forged"}]}}
    assert "reviewed_fields" not in with_reviewed_fields(forged)["summary"]


def test_upload_returns_extraction_draft_without_committing(client):
    response = client.post("/api/rag/ingest/extraction-patient", files={
        "file": ("synthetic.txt", b"Diagnosis: Hypertension", "text/plain"),
    })
    assert response.status_code == 200, response.text
    run = response.json()["review_run"]
    assert run["kind"] == "extraction"
    assert run["findings"][0]["extracted"]["data"]["name"] == "Hypertension"
    assert fields(client) == []


def test_empty_unsupported_and_cross_origin_requests(client):
    for text in ("", "   "):
        response = client.post("/api/review/patients/p/extract", json={"source_name": "Test", "text": text})
        assert response.status_code == 422
    assert draft(client, text="Unstructured prose without explicit fields")["findings"] == []
    response = client.post("/api/review/patients/p/extract", headers={"Origin": "https://untrusted.invalid"},
                           json={"source_name": "Test", "text": "Diagnosis: Hypertension"})
    assert response.status_code == 403
    assert client.post("/api/review/patients/p/extract", json={"source_name": " ", "text": "Diagnosis: Hypertension"}).status_code == 422


def test_extraction_field_rejects_unknown_types():
    with pytest.raises(ValidationError):
        ExtractedField(kind="diagnosis", data={"name": 123, "status": "documented"})
    with pytest.raises(ValidationError):
        ExtractedField(kind="invented", data={"value": "something"})
    with pytest.raises(ValidationError):
        ExtractedField(kind="date_of_birth", data={"value": "1966-02-30"})


def test_failed_finalization_rolls_back_fields_and_review(client, monkeypatch):
    from app.review import store
    client.post("/api/review/session", json={"name": "Taylor Reviewer"})
    run = draft(client, text="Diagnosis: Hypertension")
    run = decide(client, run, run["findings"][0]).json()

    def failed_audit(*args):
        raise RuntimeError("Synthetic storage failure")

    monkeypatch.setattr(store, "_append_event", failed_audit)
    with pytest.raises(RuntimeError, match="Synthetic storage failure"):
        client.post(f"/api/review/runs/{run['id']}/finalize", json={"version": run["version"]})
    assert fields(client) == []
    assert store.get_run(run["id"])["status"] == "draft"
    assert store.audit_history(run["id"])["chain_valid"]
