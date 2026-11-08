# Offline review-policy evaluation

[Back to Apollo](../README.md)

```bash
uv run --frozen python -m app.evaluation
uv run --frozen python -m app.evaluation --output /tmp/apollo-evaluation.json
```

The labeled fixture is [`data/evaluation/review_cases.json`](../data/evaluation/review_cases.json). It contains 10 synthetic cases covering documented, negated, historical, suspected, and conflicting conditions; an unsupported inference; sentence-boundary scope; missing calculator input; insufficient RAG context; and Unicode evidence offsets.

The runner evaluates supplied draft proposals and deterministic policy functions. It does not call an LLM or measure generation quality. It exits nonzero when any case differs from its labels.

| Metric | Meaning |
| --- | --- |
| Assertion accuracy | Agreement with the manually specified assertion label |
| Evidence-linkage accuracy | Whether an exact linked passage exists when expected |
| Exact-span accuracy | Whether slicing the source at the offsets reproduces the quote |
| Missing-input accuracy | Whether the requested calculator fields match the label |
| Refusal accuracy | Whether an insufficient-context case takes the refusal path |
| Unsupported draft rate | Fraction of fixture findings with no exact linked evidence; the set deliberately contains one |

These are small regression checks, not evidence of clinical accuracy, calibrated confidence, representative retrieval performance, or fairness. Exact quotation does not establish entailment. The fixture is intentionally inspectable and does not justify generalization claims.

The pytest suite separately exercises session enforcement, forged identity fields, version conflicts, finalized-state immutability, accepted/edited/rejected output filtering, clarification and recalculation, persistence, and audit-tampering detection. Browser verification uses an isolated database so test reviewer decisions do not enter the user's workspace.
