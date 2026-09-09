from __future__ import annotations

import logging

from app.agent.contracts import DiagnosisResult
from app.config import settings
from app.llm_client import get_structured_groq_client

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert clinical diagnostician. Read the patient's clinical notes,
lab results, and history. Propose the most likely differential diagnoses,
each with an ICD-10 code where known, a confidence level, supporting
evidence, and brief clinical reasoning. Name the single most likely primary
diagnosis, note key differentials to rule out, and recommend investigations.
"""


def _call_llm(context: str) -> DiagnosisResult:
    client = get_structured_groq_client()
    return client.chat.completions.create(
        model=settings.groq_model,
        response_model=DiagnosisResult,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"=== PATIENT DATA ===\n\n{context}"},
        ],
        temperature=0.2,
        max_tokens=4096,
        reasoning_effort="low",
    )


def run_diagnosis_agent(context: str) -> dict:
    """
    Propose differential diagnoses from clinical context. The LLM call is
    validated against `DiagnosisResult` via tool-calling before it's dumped
    back to a dict for the rest of the pipeline. Raises RuntimeError if
    Groq is unavailable.
    """
    if not settings.has_groq:
        raise RuntimeError("Diagnosis agent: GROQ_API_KEY not set.")
    log.info("[diagnosis_agent] Running (%s)", settings.groq_model)
    return _call_llm(context).model_dump()
