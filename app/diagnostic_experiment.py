"""Explicitly run paid model calls on synthetic fixtures; no patient records loaded."""
import argparse
import json
import time
from pathlib import Path

from app.agent.diagnosis_agent import _call_llm
from app.agent.diagnostic_review import run_diagnostic_review
from app.diagnostic_benchmark import DEFAULT_CASES, compare


def collect(cases: list[dict]) -> list[dict]:
    rows = []
    for case in cases:
        for mode in ("standard", "extended"):
            started = time.monotonic()
            usage = {"requests": 0}
            try:
                if mode == "standard":
                    result, model = _call_llm(case["context"], usage)
                    result = {**result.model_dump(), "_model_used": model}
                    status = "complete"
                else:
                    result = run_diagnostic_review({"record/narrative": {
                        "text": case["context"], "kind": "document", "label": "Synthetic case",
                    }})
                    usage = result["_diagnostic_review"]
                    status = usage["status"]
            except Exception:
                result, status = {}, "unavailable"
            rows.append({"case_id": case["id"], "mode": mode, "status": status, "result": result,
                         "elapsed_seconds": round(time.monotonic() - started, 3),
                         "requests": usage.get("requests", 0),
                         **{key: usage.get(key) for key in ("input_tokens", "output_tokens", "cost_usd")}})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize model calls using configured API keys")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to authorize model calls, or use app.diagnostic_benchmark on saved predictions")
    cases = json.loads(args.cases.read_text())
    rows = collect(cases)
    args.output.write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    print(json.dumps(compare(cases, rows), indent=2))


if __name__ == "__main__":
    main()
