from __future__ import annotations

import json
import logging
from typing import Any

from groq import Groq

from app.config import settings

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert clinical diagnostician. Read the patient's clinical notes,
lab results, and history. Propose the most likely differential diagnoses.

Return ONLY valid JSON:
{
  "proposed_diagnoses": [
    {
      "name": "<condition name>",
      "icd_code": "<ICD-10 code if known>",
      "confidence": "high|moderate|low",
      "supporting_evidence": ["<evidence 1>", "..."],
      "reasoning": "<brief clinical reasoning>"
    }
  ],
  "primary_diagnosis": "<most likely diagnosis>",
  "differential_notes": "<key differentials to rule out>",
  "recommended_investigations": ["<test 1>", "..."]
}
"""


def _call_llm(context: str) -> dict[str, Any]:
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"=== PATIENT DATA ===\n\n{context}"},
        ],
        temperature=0.2,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def run_diagnosis_agent(context: str) -> dict[str, Any]:
    """
    Propose differential diagnoses from clinical context.
    Raises RuntimeError if Groq is unavailable.
    """
    if not settings.has_groq:
        raise RuntimeError("Diagnosis agent: GROQ_API_KEY not set.")
    log.info("[diagnosis_agent] Running (%s)", settings.groq_model)
    return _call_llm(context)
