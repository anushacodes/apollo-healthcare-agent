import logging

from app.agent.contracts import DiagnosisResult
from app.config import settings
from app.llm_client import call_llm_json

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert clinical diagnostician. Read the patient's clinical notes,
lab results, and history. Propose the most likely differential diagnoses,
each with an ICD-10 code where known, a confidence level ("high", "moderate", "low"),
supporting evidence, and brief clinical reasoning. Name the single most likely primary
diagnosis, note key differentials to rule out, and recommend investigations.

You MUST respond ONLY with a valid JSON object adhering strictly to this schema:
{
  "proposed_diagnoses": [
    {
      "name": "Condition or disease name",
      "icd_code": "ICD-10 code (e.g. M32.14)",
      "confidence": "high",
      "supporting_evidence": ["Specific lab abnormality, physical finding, or history item 1", "..."],
      "reasoning": "Brief clinical reasoning for this diagnosis"
    }
  ],
  "primary_diagnosis": "Single most likely primary diagnosis name",
  "differential_notes": "Important differential diagnoses considered and ruled in/out",
  "recommended_investigations": ["Specific lab, imaging, or procedure 1", "..."]
}
"""


def _call_llm(context: str) -> tuple[DiagnosisResult, str]:
    raw_dict, model_used = call_llm_json(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"=== PATIENT DATA ===\n\n{context}"},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    result = DiagnosisResult.model_validate(raw_dict)
    return result, model_used


def run_diagnosis_agent(context: str) -> dict:
    """
    Propose differential diagnoses from clinical context. Validates against
    DiagnosisResult via Pydantic. Supports Groq and OpenRouter.
    """
    if not settings.has_groq and not settings.has_openrouter:
        raise RuntimeError("Diagnosis agent: Neither GROQ_API_KEY nor OPENROUTER_API_KEY is configured.")
    log.info("[diagnosis_agent] Running via provider %s", settings.active_llm_provider)
    res, model_used = _call_llm(context)
    data = res.model_dump()
    data["_model_used"] = model_used
    return data
