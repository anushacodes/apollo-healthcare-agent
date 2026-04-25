from __future__ import annotations

import json
import logging
from typing import Any

from groq import Groq

from app.config import settings
from app.agent import kg_loader

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical pharmacologist. Given a patient's medication list, diagnoses,
and knowledge graph findings, identify drug-drug interactions and drug-condition
contraindications.

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


def _call_llm(medications: list[str], diagnoses: list[str], kg_results: dict) -> dict[str, Any]:
    client = Groq(api_key=settings.groq_api_key)
    prompt = (
        f"MEDICATIONS: {json.dumps(medications)}\n"
        f"DIAGNOSES: {json.dumps(diagnoses)}\n"
        f"KG FINDINGS: {json.dumps(kg_results)}\n"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def run_drug_interaction_agent(
    medications: list[str],
    diagnoses: list[str],
    symptoms: list[str],
) -> dict[str, Any]:
    """
    Drug interaction pipeline:
    1. Query KG (Neo4j → local JSON fallback) for structural drug/condition data
    2. Run Groq LLM analysis on combined context
    """
    kg_results = kg_loader.query_drug_interactions(
        drug_names=medications,
        conditions=diagnoses,
    )

    if settings.has_groq:
        result = _call_llm(medications, diagnoses, kg_results)
        result["kg_source"] = kg_results.get("source")
        return result

    return {
        "interactions": kg_results.get("interactions", []),
        "contraindications": kg_results.get("contraindications", []),
        "overall_risk": "unknown",
        "summary": "LLM analysis unavailable — KG results only.",
        "kg_source": kg_results.get("source"),
    }
