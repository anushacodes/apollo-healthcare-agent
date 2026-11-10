from app import diagnostic_experiment as experiment
from app.agent.contracts import DiagnosisResult
from app.diagnostic_benchmark import compare
from tests.test_diagnostic_review import install


def test_experiment_collects_both_modes_without_patient_store_or_label_leak(monkeypatch):
    calls = install(monkeypatch)
    captured = []

    def standard(context, usage):
        captured.append(context)
        usage.update(requests=1, input_tokens=10, output_tokens=5)
        return DiagnosisResult(primary_diagnosis="Anemia", proposed_diagnoses=[{"name": "Anemia"}]), "mock/model"

    monkeypatch.setattr(experiment, "_call_llm", standard)
    cases = [{"id": "case", "context": "Fatigue. Hemoglobin low. No fever.", "expected_primary": ["Anemia"]}]
    rows = experiment.collect(cases)
    assert len(rows) == 2
    assert captured == [cases[0]["context"]]
    assert "expected_primary" not in str(calls)
    report = compare(cases, rows)["modes"]
    assert report["standard"]["top1_accuracy"] == report["extended"]["top1_accuracy"] == 1
    assert report["extended"]["requests"] == 4
