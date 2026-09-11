import json
import logging

from app.agent.contracts import DrugInteractionResult
from app.config import settings
from app.llm_client import call_llm_json, get_structured_groq_client

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical pharmacologist. Given a patient's medication list and
diagnoses, identify drug-drug interactions (severity, mechanism, and
clinical significance) and drug-condition contraindications, then give an
overall risk level and a short summary.

Respond with valid JSON matching this schema:
{
  "interactions": [
    {
      "drugs": ["drug 1", "drug 2"],
      "severity": "major|moderate|minor",
      "mechanism": "mechanism of interaction",
      "clinical_significance": "clinical impact"
    }
  ],
  "contraindications": [
    {
      "drug": "drug name",
      "condition": "contraindicated condition",
      "risk": "risk description"
    }
  ],
  "overall_risk": "high|moderate|low",
  "summary": "concise clinical summary of drug risks"
}
"""


def _call_llm(medications: list[str], diagnoses: list[str]) -> DrugInteractionResult:
    prompt = (
        f"MEDICATIONS: {json.dumps(medications)}\n"
        f"DIAGNOSES: {json.dumps(diagnoses)}\n"
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    if settings.active_llm_provider == "openrouter" and settings.has_openrouter:
        try:
            raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
            return DrugInteractionResult.model_validate(raw_dict)
        except Exception as exc:
            log.warning("[drug_interaction_agent] OpenRouter call failed: %s", exc)

    if settings.has_groq:
        try:
            client = get_structured_groq_client()
            return client.chat.completions.create(
                model=settings.groq_model,
                response_model=DrugInteractionResult,
                messages=messages,
                temperature=0.1,
                max_tokens=4096,
                reasoning_effort="low",
            )
        except Exception as exc:
            log.warning("[drug_interaction_agent] Groq tool call failed, trying JSON: %s", exc)
            raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
            return DrugInteractionResult.model_validate(raw_dict)

    if settings.has_openrouter:
        raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
        return DrugInteractionResult.model_validate(raw_dict)

    raise RuntimeError("Neither Groq nor OpenRouter is configured for drug interaction agent.")


def run_drug_interaction_agent(
    medications: list[str],
    diagnoses: list[str],
    symptoms: list[str],
) -> tuple[dict, bool]:
    """
    Drug interaction pipeline: LLM analysis of the patient's medications
    and diagnoses, validated against `DrugInteractionResult`.
    Returns (result, succeeded).
    """
    if settings.has_groq or settings.has_openrouter:
        try:
            return _call_llm(medications, diagnoses).model_dump(), True
        except Exception as exc:
            log.warning("[drug_interaction_agent] LLM call failed, using fallback: %s", exc)
            return DrugInteractionResult(summary="LLM analysis unavailable.").model_dump(), False

    return DrugInteractionResult(summary="LLM analysis unavailable.").model_dump(), False
