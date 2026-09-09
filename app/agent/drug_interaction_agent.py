from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.llm_client import get_groq_client

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical pharmacologist. Given a patient's medication list and diagnoses,
identify drug-drug interactions and drug-condition contraindications.

Return ONLY valid JSON:
{
  "interactions": [
    {
      "drugs": ["<drug_a>", "<drug_b>"],
      "severity": "major|moderate|minor",
      "mechanism": "<brief explanation>",
      "clinical_significance": "<what the clinician should do>"
    }
  ],
  "contraindications": [
    {
      "drug": "<drug_name>",
      "condition": "<condition_name>",
      "risk": "<brief explanation>"
    }
  ],
  "overall_risk": "high|moderate|low",
  "summary": "<1-2 sentence clinical summary of interaction risk>"
}
"""


def _call_llm(medications: list[str], diagnoses: list[str]) -> dict[str, Any]:
    client = get_groq_client()
    prompt = (
        f"MEDICATIONS: {json.dumps(medications)}\n"
        f"DIAGNOSES: {json.dumps(diagnoses)}\n"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def run_drug_interaction_agent(
    medications: list[str],
    diagnoses: list[str],
    symptoms: list[str],
) -> dict[str, Any]:
    """
    Drug interaction pipeline: Groq LLM analysis of the patient's medications
    and diagnoses. Not grounded against a real drug database yet — see
    docs/TASKS.md Epic 2.2 for the planned RxNorm/OpenFDA-backed grounding.
    """
    if settings.has_groq:
        return _call_llm(medications, diagnoses)

    return {
        "interactions": [],
        "contraindications": [],
        "overall_risk": "unknown",
        "summary": "LLM analysis unavailable.",
    }
