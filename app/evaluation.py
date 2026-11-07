"""Offline labeled review-policy benchmark; does not measure LLM or clinical accuracy."""
import argparse
import json
from pathlib import Path

from app.agent.rag.nodes import generator_node, sufficiency_judge_node
from app.agent.rag.state import RAGState
from app.review.calculators import execute_call
from app.review.evidence import record_sources
from app.review.workflow import build_findings


def evaluate(cases: list[dict]) -> dict:
    rows = []
    assertions = evidence_checks = span_checks = missing_checks = refusal_checks = 0
    correct_assertions = correct_evidence = correct_spans = correct_missing = correct_refusal = 0
    unsupported = total = 0
    for case in cases:
        sources = record_sources(case["patient"])
        findings = build_findings(case["patient"], {"diagnoses": {"proposed_diagnoses": case["proposals"]}}, sources)
        by_name = {f["title"]: f for f in findings}
        errors = []
        for name, expected in case["expected"].items():
            actual = by_name.get(name, {})
            assertions += 1
            if actual.get("assertion") == expected["assertion"]:
                correct_assertions += 1
            else:
                errors.append(f"{name}: assertion differs from label")
            evidence_checks += 1
            if bool(actual.get("evidence")) == expected["has_evidence"]:
                correct_evidence += 1
            else:
                errors.append(f"{name}: evidence availability differs from label")
        for finding in findings:
            total += 1
            unsupported += not bool(finding["evidence"])
            for evidence in finding["evidence"]:
                span_checks += 1
                text = sources[evidence["source_id"]]["text"]
                if text[evidence["start"]:evidence["end"]] == evidence["quote"]:
                    correct_spans += 1
                else:
                    errors.append("Source span does not match its quote")
        if "calculator" in case:
            missing_checks += 1
            result = execute_call(case["calculator"]["tool"], case["calculator"]["params"])
            if sorted(f["name"] for f in result.get("missing_fields", [])) == sorted(case["expected_missing"]):
                correct_missing += 1
            else:
                errors.append("Missing inputs differ from label")
        if "expected_refusal" in case:
            refusal_checks += 1
            state = RAGState(all_chunks=case["chunks"])
            state.context_sufficient = sufficiency_judge_node(state)["context_sufficient"]
            # Only evaluate expected refusals: this branch must never call a provider.
            actual_refusal = not state.context_sufficient and generator_node(state)["is_refusal"]
            if actual_refusal == case["expected_refusal"]:
                correct_refusal += 1
            else:
                errors.append("Refusal differs from label")
        rows.append({"id": case["id"], "passed": not errors, "errors": errors})
    def metric(correct, count):
        return {"correct": correct, "total": count, "rate": round(correct / count, 4) if count else None}
    return {"scope": "Synthetic review-policy regression; no clinical validation or LLM quality claim",
            "cases": len(cases), "passed": sum(row["passed"] for row in rows),
            "assertion_accuracy": metric(correct_assertions, assertions),
            "evidence_linkage_accuracy": metric(correct_evidence, evidence_checks),
            "exact_span_accuracy": metric(correct_spans, span_checks),
            "missing_input_accuracy": metric(correct_missing, missing_checks),
            "refusal_accuracy": metric(correct_refusal, refusal_checks),
            "unsupported_draft_rate": round(unsupported / total, 4) if total else 0,
            "per_case": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("data/evaluation/review_cases.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.cases.read_text()))
    output = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(output + "\n")
    print(output)
    raise SystemExit(0 if report["passed"] == report["cases"] else 1)


if __name__ == "__main__":
    main()
