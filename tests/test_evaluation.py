import copy
import json
from pathlib import Path

from app.evaluation import evaluate


def test_labeled_review_policy_benchmark():
    cases = json.loads(Path("data/evaluation/review_cases.json").read_text())
    report = evaluate(cases)
    assert report["cases"] == 10
    assert report["passed"] == 10
    assert report["exact_span_accuracy"]["total"] > 0
    assert report["unsupported_draft_rate"] > 0  # Unsupported fixture is deliberately present.
    changed = copy.deepcopy(cases)
    changed[0]["expected"]["Diabetes"]["assertion"] = "historical"
    assert evaluate(changed)["passed"] == 9
