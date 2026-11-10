# Diagnostic review experiment

The diagnostic experiment compares standard and extended assessments on the same
six synthetic cases. These are inspectable development fixtures, including missing,
negated, and conflicting information. They are not a representative clinical benchmark.
The existing review-policy evaluation remains a separate check.

## Compare saved predictions

```bash
uv run --frozen python -m app.diagnostic_benchmark --predictions /tmp/predictions.json --output /tmp/comparison.json
```

Predictions are a JSON array containing exactly one row per case and mode:

```json
{
  "case_id": "iron-deficiency",
  "mode": "standard",
  "status": "complete",
  "result": {
    "primary_diagnosis": "Iron deficiency anemia",
    "proposed_diagnoses": [{"name": "Iron deficiency anemia"}]
  },
  "elapsed_seconds": 2.5,
  "requests": 1,
  "input_tokens": null,
  "output_tokens": null,
  "cost_usd": null
}
```

Use `status: "unavailable"` with an empty result for failed runs; failures count
against accuracy and abstention instead of disappearing from the denominator.
Primary labels use normalized exact aliases. Top-three recall checks the first three
ranked proposals. Cases with no primary label are scored separately for abstention.
These metrics do not assess the clinical soundness of explanations.

Independent reviewers may add `unsupported_claims` and `assessed_claims` together,
and an `investigation_score` from 1 (inappropriate) to 5 (appropriate and justified).
Blind mode labels during adjudication, use the same rubric for both modes, and
review recommendations against the complete case. The report shows adjudication
coverage; absent labels, token usage, and monetary costs remain null. Source quotation
matching and model agreement must not be counted as clinical validation.

## Staged rollout

1. Establish the saved-prediction benchmark and regression fixtures.
2. Add a bounded backend experiment: two independent assessments, a critic, and a synthesis.
3. Expose an opt-in Analysis control, saved review details, and human-review findings.

Keep standard analysis as the default. Before broader use, run a held-out,
independently adjudicated case set with identical provider/model configurations,
report failures and latency alongside accuracy, and examine unsupported claims and
investigation quality. The small bundled fixture cannot justify a clinical improvement claim.
