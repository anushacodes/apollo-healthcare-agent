import json
import logging

from app.agent.contracts import DrugInteractionResult
from app.config import settings
from app.llm_client import get_structured_groq_client

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical pharmacologist. Given a patient's medication list and
diagnoses, identify drug-drug interactions (severity, mechanism, and
clinical significance) and drug-condition contraindications, then give an
overall risk level and a short summary.
"""


def _call_llm(medications: list[str], diagnoses: list[str]) -> DrugInteractionResult:
    client = get_structured_groq_client()
    prompt = (
        f"MEDICATIONS: {json.dumps(medications)}\n"
        f"DIAGNOSES: {json.dumps(diagnoses)}\n"
    )
    return client.chat.completions.create(
        model=settings.groq_model,
        response_model=DrugInteractionResult,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        reasoning_effort="low",
    )


def run_drug_interaction_agent(
    medications: list[str],
    diagnoses: list[str],
    symptoms: list[str],
) -> tuple[dict, bool]:
    """
    Drug interaction pipeline: Groq LLM analysis of the patient's medications
    and diagnoses, validated against `DrugInteractionResult` via tool-calling.
    Not grounded against a real drug database yet — see docs/TASKS.md Epic 2.2
    for the planned RxNorm/OpenFDA-backed grounding.

    Returns (result, succeeded) — callers should not cache a result where
    succeeded is False, since it's a placeholder, not a real analysis.
    """
    if settings.has_groq:
        try:
            return _call_llm(medications, diagnoses).model_dump(), True
        except Exception as exc:
            log.warning("[drug_interaction_agent] LLM call failed, using fallback: %s", exc)
            return DrugInteractionResult(summary="LLM analysis unavailable.").model_dump(), False

    return DrugInteractionResult(summary="LLM analysis unavailable.").model_dump(), False
