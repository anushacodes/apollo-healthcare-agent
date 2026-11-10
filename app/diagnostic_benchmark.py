"""Compare saved diagnostic predictions on labeled cases without calling a model."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "data/evaluation/diagnostic_cases.json"


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str
    mode: Literal["standard", "extended"]
    status: Literal["complete", "unavailable"]
    result: dict
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    requests: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # Optional independent adjudication; never substitute a model's self-assessment.
    unsupported_claims: int | None = Field(default=None, ge=0)
    assessed_claims: int | None = Field(default=None, ge=1)
    investigation_score: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def annotations(self):
        if (self.unsupported_claims is None) != (self.assessed_claims is None):
            raise ValueError("Supply both unsupported_claims and assessed_claims")
        if self.unsupported_claims is not None and self.unsupported_claims > self.assessed_claims:
            raise ValueError("Unsupported claims cannot exceed assessed claims")
        if self.status == "complete":
            if not isinstance(self.result.get("primary_diagnosis"), str):
                raise ValueError("Completed predictions need a primary_diagnosis string")
            proposed = self.result.get("proposed_diagnoses")
            if not isinstance(proposed, list) or any(
                not isinstance(d, dict) or not isinstance(d.get("name"), str) for d in proposed
            ):
                raise ValueError("Completed predictions need named proposed_diagnoses")
        return self


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def compare(cases: list[dict], predictions: list[dict]) -> dict:
    """Require paired, complete coverage; failed runs count as incorrect, not omitted."""
    ids = [case["id"] for case in cases]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Case IDs must be nonempty and unique")
    rows = [Measurement.model_validate(row) for row in predictions]
    keys = Counter((row.case_id, row.mode) for row in rows)
    expected = {(case_id, mode) for case_id in ids for mode in ("standard", "extended")}
    if set(keys) != expected or any(count != 1 for count in keys.values()):
        raise ValueError("Provide exactly one standard and one extended prediction for every case")
    labels = {case["id"]: case for case in cases}
    reports = {}
    for mode in ("standard", "extended"):
        selected = [row for row in rows if row.mode == mode]
        top1 = top3 = diagnostic = abstention = abstention_correct = 0
        per_case = []
        for row in selected:
            case = labels[row.case_id]
            primary = normalize(row.result.get("primary_diagnosis", ""))
            ranked = [normalize(d["name"]) for d in row.result.get("proposed_diagnoses", [])][:3]
            aliases = {normalize(name) for name in case["expected_primary"]}
            if aliases:
                diagnostic += 1
                correct = row.status == "complete" and primary in aliases
                top1 += correct
                top3 += row.status == "complete" and bool(aliases.intersection(ranked))
            else:
                abstention += 1
                correct = row.status == "complete" and primary in {"unknown", "insufficient information"} and not ranked
                abstention_correct += correct
            per_case.append({"id": row.case_id, "status": row.status, "primary_matches_label": correct})
        annotated = [row for row in selected if row.assessed_claims is not None]
        scores = [row.investigation_score for row in selected if row.investigation_score is not None]
        latencies = sorted(row.elapsed_seconds for row in selected)

        def total_if_known(field):
            values = [getattr(row, field) for row in selected]
            return sum(values) if all(value is not None for value in values) else None

        reports[mode] = {
            "cases": len(selected), "completed": sum(row.status == "complete" for row in selected),
            "top1_accuracy": top1 / diagnostic if diagnostic else None,
            "top3_recall": top3 / diagnostic if diagnostic else None,
            "diagnostic_cases": diagnostic,
            "abstention_accuracy": abstention_correct / abstention if abstention else None,
            "abstention_cases": abstention,
            "unsupported_claim_rate": (sum(row.unsupported_claims for row in annotated) /
                                       sum(row.assessed_claims for row in annotated)) if annotated else None,
            "adjudicated_cases": len(annotated),
            "mean_investigation_score": sum(scores) / len(scores) if scores else None,
            "investigation_scored_cases": len(scores),
            "mean_seconds": sum(latencies) / len(latencies),
            "p95_seconds": latencies[math.ceil(len(latencies) * .95) - 1],
            "requests": sum(row.requests for row in selected),
            "input_tokens": total_if_known("input_tokens"), "output_tokens": total_if_known("output_tokens"),
            "cost_usd": total_if_known("cost_usd"), "per_case": per_case,
        }
    return {"scope": "Synthetic diagnostic experiment; no clinical validation claim", "modes": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(json.loads(args.cases.read_text()), json.loads(args.predictions.read_text()))
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
