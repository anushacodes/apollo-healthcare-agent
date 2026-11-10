import copy
from unittest.mock import Mock

import pytest

from app.agent import diagnostic_review as review
from app.agent.diagnostics import nodes
from app.agent.diagnostics.state import AgentState
from app.config import settings
from app.review.workflow import create_draft

SOURCES = {"record/narrative": {"text": "Fatigue. Hemoglobin low. No fever.", "kind": "document", "label": "Note"}}


def assessment():
    return {"primary_diagnosis": "Anemia", "proposed_diagnoses": [{
        "name": "Anemia", "icd_code": None, "confidence": "low",
        "supporting_evidence": [{"source_id": "record/narrative", "quote": "Hemoglobin low."}],
        "counterevidence": [], "reasoning": "Low hemoglobin supports anemia; cause remains uncertain.",
        "missing_information": ["Iron studies"],
    }], "differential_notes": "Cause not established.", "recommended_investigations": ["Iron studies to assess cause"],
        "disagreements": [], "missing_information": ["Iron studies"]}


def install(monkeypatch, outputs=None):
    outputs = copy.deepcopy(outputs or [assessment(), assessment(), {
        "concerns": ["Cause is unconfirmed"], "disagreements": ["Etiology remains uncertain"],
        "missing_information": ["Iron studies"],
    }, assessment()])
    captured = []

    def call(messages, **kwargs):
        captured.append((copy.deepcopy(messages), kwargs))
        kwargs["telemetry"].update(requests=1, input_tokens=100, output_tokens=30)
        value = outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value, "mock/model"

    monkeypatch.setattr(review, "call_llm_json", call)
    return captured


def test_four_bounded_passes_independent_evidence_and_dissent(monkeypatch):
    calls = install(monkeypatch)
    result = review.run_diagnostic_review(SOURCES)
    metadata = result["_diagnostic_review"]
    assert metadata["status"] == "complete"
    assert len(calls) == metadata["requests"] == 4
    assert metadata["input_tokens"] == 400
    assert metadata["cost_usd"] is None
    assert calls[0][0][1] == calls[1][0][1]
    assert all(c[1]["allow_fallback"] is False and c[1]["timeout"] == 20 for c in calls)
    assert "Etiology remains uncertain" in metadata["disagreements"]
    assert result["proposed_diagnoses"][0]["evidence_refs"][0]["quote"] == "Hemoglobin low."
    assert "supporting_evidence" in metadata["stages"][-1]["output"]["proposed_diagnoses"][0]


@pytest.mark.parametrize("failure_at", range(4))
def test_failure_stops_without_extra_model_calls_or_partial_diagnoses(monkeypatch, failure_at):
    outputs = [assessment(), assessment(), {"concerns": [], "disagreements": [], "missing_information": []}, assessment()]
    outputs[failure_at] = RuntimeError("private patient and secret provider response")
    calls = install(monkeypatch, outputs)
    result = review.run_diagnostic_review(SOURCES)
    assert result["_diagnostic_review"]["status"] == "unavailable"
    assert len(calls) == failure_at + 1
    assert "proposed_diagnoses" not in result
    assert "private patient" not in str(result)


@pytest.mark.parametrize("bad_ref", [
    {"source_id": "unknown", "quote": "Hemoglobin low."},
    {"source_id": "record/narrative", "quote": "invented biopsy result"},
    {"source_id": "record/narrative", "quote": "  "},
])
def test_unverifiable_evidence_is_rejected(monkeypatch, bad_ref):
    output = assessment()
    output["proposed_diagnoses"][0]["supporting_evidence"] = [bad_ref]
    calls = install(monkeypatch, [output])
    result = review.run_diagnostic_review(SOURCES)
    assert result["_diagnostic_review"]["status"] == "unavailable"
    assert len(calls) == 1


def test_reference_alone_and_unranked_primary_are_rejected(monkeypatch):
    install(monkeypatch)
    sources = copy.deepcopy(SOURCES)
    sources["record/narrative"]["kind"] = "reference"
    assert review.run_diagnostic_review(sources)["_diagnostic_review"]["status"] == "unavailable"
    wrong = assessment()
    wrong["primary_diagnosis"] = "Unlisted condition"
    install(monkeypatch, [wrong])
    assert review.run_diagnostic_review(SOURCES)["_diagnostic_review"]["status"] == "unavailable"


def test_oversized_context_never_calls_provider(monkeypatch):
    call = Mock(side_effect=AssertionError("Must not call"))
    monkeypatch.setattr(review, "call_llm_json", call)
    result = review.run_diagnostic_review({"a": {"text": "x" * review.MAX_SOURCE_CHARS}})
    assert result["_diagnostic_review"]["failure_code"] == "context_too_large"
    call.assert_not_called()


def test_mode_cache_isolation_failed_reviews_not_cached_and_model_changes(monkeypatch):
    monkeypatch.setattr(settings, "extended_diagnostics_enabled", True)
    state = AgentState(patient_id="patient", patient_data={"summary": {"summary_narrative": SOURCES["record/narrative"]["text"]}},
                       anonymized_notes="same context", diagnostic_mode="extended")
    calls = install(monkeypatch)
    first = nodes.diagnosis_node(state)
    assert first["diagnoses"]["_diagnostic_review"]["cached"] is False
    assert nodes.diagnosis_node(state)["diagnoses"]["_diagnostic_review"]["cached"] is True
    assert len(calls) == 4
    baseline = Mock(return_value={"primary_diagnosis": "Baseline", "proposed_diagnoses": []})
    monkeypatch.setattr(nodes, "run_diagnosis_agent", baseline)
    state.diagnostic_mode = "standard"
    assert nodes.diagnosis_node(state)["diagnoses"]["primary_diagnosis"] == "Baseline"
    baseline.assert_called_once()
    state.diagnostic_mode = "extended"
    monkeypatch.setattr(settings, "groq_model", "different-model")
    failed = install(monkeypatch, [RuntimeError("failed")])
    assert nodes.diagnosis_node(state)["diagnoses"]["_diagnostic_review"]["status"] == "unavailable"
    assert len(failed) == 1
    retried = install(monkeypatch)
    assert nodes.diagnosis_node(state)["diagnoses"]["_diagnostic_review"]["status"] == "complete"
    assert len(retried) == 4


def test_extended_review_quotes_and_uncertainty_are_pending_review_findings(monkeypatch):
    install(monkeypatch)
    patient = {"patient_id": "synthetic", "summary": {"summary_narrative": SOURCES["record/narrative"]["text"]}}
    run = create_draft(patient, {"diagnoses": review.run_diagnostic_review(SOURCES), "diagnostic_sources": SOURCES})
    dx = next(f for f in run["findings"] if f["title"] == "Anemia")
    assert dx["status"] == "pending"
    assert dx["assertion"] == "ai_suggested"
    assert dx["evidence"][0]["quote"] == "Hemoglobin low."
    assert {f["kind"] for f in run["findings"]} >= {"diagnosis", "diagnostic_review", "investigation"}


async def test_extended_mode_disabled_before_graph_work(case_a):
    from app.agent.diagnostics.graph import run_graph_streaming
    with pytest.raises(ValueError, match="disabled"):
        _ = [event async for event in run_graph_streaming(case_a, "extended")]
