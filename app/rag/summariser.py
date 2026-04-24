# TODO: Step 6 — Structured PatientSummary generation
# LLM provider priority: Groq (primary) → Gemini (fallback on rate limit) → Ollama small (last resort)
# Uses instructor library for structured extraction against PatientSummary Pydantic model.
# Caches result in summary_cache (keyed by patient_id + sha256 of sorted doc_ids).
# Traces the LLM call with LangFuse.
# Scrolls ALL chunks from Qdrant (not just top-k) to build the full patient context.
