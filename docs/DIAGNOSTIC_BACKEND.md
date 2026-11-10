# Bounded diagnostic review backend

Standard analysis is the default. Extended review runs four sequential passes:
two independent assessments that see the same source catalog, a critic that sees
both assessments, and a synthesis that sees the assessments and critique. The first
two passes use different instructions, potentially the same underlying model; they
are not independent clinical experts or independent sources of truth.

Each pass allows one provider request with a 20-second SDK timeout and 3,072 output
tokens. Provider fallback and SDK retries are disabled for these four calls. Failure
stops the review with an unavailable status; it does not spend a fifth call recovering.
The rest of the analysis pipeline makes its usual calls. The per-request SDK timeout
is not a hard deadline for the entire analysis.

Outputs use bounded schemas. Each candidate needs at least one exact quotation from
a supplied patient/calculator source; a condition reference alone is insufficient.
The server verifies the source ID and quote. This establishes provenance, not clinical
entailment. Negation and interpretation still require human review. Uncertainty and
critic concerns remain available even when the synthesizer omits them. Intermediate
outputs never become the final differential after a failed pass.

Successful extended results use caches keyed by patient, complete supplied sources,
mode, prompt/schema version, provider, and configured models. Failed reviews are not
cached. Cached results are labeled as reused; their saved latency and usage refer to
the original computation. Calculator clarification regenerates the selected mode and
requires fresh review of affected diagnoses, uncertainty, and investigations.

## Synthetic live experiment

```bash
uv run --frozen python -m app.diagnostic_experiment --live --output /tmp/diagnostic-predictions.json
uv run --frozen python -m app.diagnostic_benchmark --predictions /tmp/diagnostic-predictions.json
```

`--live` explicitly enables provider calls with configured keys. This command reads
only the supplied fixture file, bypasses the application cache, and never loads saved
patient records. Both modes receive the case context without the reference label.
The benchmark labels are used only after generation. It saves failures and any
available provider token counts; absent usage and monetary costs remain null. Failed
provider attempts can have unknown charges, so partial token usage is not reported
as a complete total. The [benchmark guide](DIAGNOSTIC_EXPERIMENT.md) describes independent
adjudication and the limits of the synthetic labels.
