import copy
import json

import pytest

from app.diagnostic_benchmark import DEFAULT_CASES, compare


def paired():
    case = {"id": "test", "expected_primary": ["Condition A"]}
    rows = [{"case_id": "test", "mode": mode, "status": "complete", "elapsed_seconds": 1.0,
             "requests": 1, "result": {"primary_diagnosis": "Condition A",
                                       "proposed_diagnoses": [{"name": "Condition A"}]}}
            for mode in ("standard", "extended")]
    return [case], rows


def test_paired_accuracy_missing_adjudication_and_cost_are_explicit():
    cases, rows = paired()
    rows[1].update(unsupported_claims=1, assessed_claims=4, investigation_score=3)
    report = compare(cases, rows)["modes"]
    assert report["standard"]["top1_accuracy"] == 1
    assert report["extended"]["unsupported_claim_rate"] == .25
    assert report["standard"]["unsupported_claim_rate"] is None
    assert report["standard"]["cost_usd"] is None
    assert report["standard"]["input_tokens"] is None


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_bad_pairing_cannot_silently_bias_results(change):
    cases, rows = paired()
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        rows[0]["case_id"] = "unknown"
    with pytest.raises(ValueError):
        compare(cases, rows)


def test_failed_runs_count_against_accuracy_and_abstention():
    cases, rows = paired()
    rows[1].update(status="unavailable", result={})
    assert compare(cases, rows)["modes"]["extended"]["top1_accuracy"] == 0
    cases[0]["expected_primary"] = []
    rows[0]["result"] = {"primary_diagnosis": "unknown", "proposed_diagnoses": []}
    report = compare(cases, rows)["modes"]
    assert report["standard"]["abstention_accuracy"] == 1
    assert report["extended"]["abstention_accuracy"] == 0
    assert report["standard"]["top1_accuracy"] is None


def test_fixture_ids_and_limits():
    cases = json.loads(DEFAULT_CASES.read_text())
    assert len(cases) == 6
    assert len({case["id"] for case in cases}) == 6
    assert all(case["context"].startswith("Synthetic case.") for case in cases)
    labels, rows = paired()
    rows[0].update(unsupported_claims=3, assessed_claims=2)
    with pytest.raises(ValueError):
        compare(labels, rows)
