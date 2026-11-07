"""Offline extraction regression against hand-labeled synthetic English documents."""
import argparse
import json
from pathlib import Path

from app.ingestion.structured import extract_fields

DEFAULT_CASES = Path(__file__).resolve().parents[2] / "data/evaluation/extraction_cases.json"


def evaluate(cases):
    rows = []
    correct = predicted = expected = span_correct = span_total = 0
    for case in cases:
        result = extract_fields(case["text"])
        actual = {json.dumps({"kind": f["kind"], "data": f["data"]}, sort_keys=True) for f in result["fields"]}
        labels = {json.dumps(f, sort_keys=True) for f in case["expected"]}
        correct += len(actual & labels)
        predicted += len(actual)
        expected += len(labels)
        spans = all(case["text"][f["start"]:f["end"]] == f["quote"] for f in result["fields"])
        span_total += len(result["fields"])
        span_correct += sum(case["text"][f["start"]:f["end"]] == f["quote"] for f in result["fields"])
        warning_matches = bool(result["warnings"]) == case.get("expected_warning", False)
        rows.append({"id": case["id"], "passed": actual == labels and spans and warning_matches,
                     "missing": [json.loads(f) for f in sorted(labels - actual)],
                     "unexpected": [json.loads(f) for f in sorted(actual - labels)],
                     "spans_match": spans, "warnings_match": warning_matches})
    return {"scope": "Hand-labeled synthetic English extraction; no clinical or general-document accuracy claim",
            "cases": len(rows), "passed": sum(row["passed"] for row in rows),
            "field_precision": correct / predicted if predicted else None,
            "field_recall": correct / expected if expected else None,
            "exact_spans": {"correct": span_correct, "total": span_total}, "per_case": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args()
    report = evaluate(json.loads(args.cases.read_text()))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] == report["cases"] else 1)


if __name__ == "__main__":
    main()
