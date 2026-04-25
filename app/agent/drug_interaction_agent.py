from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types
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


def _call_gemini(medications: list[str], diagnoses: list[str], kg_results: dict) -> dict[str, Any]:
    """Gemini — large context window for dense drug/KG data."""
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
MEDICATIONS: {json.dumps(medications)}
DIAGNOSES: {json.dumps(diagnoses)}
KNOWLEDGE GRAPH FINDINGS:
{json.dumps(kg_results, indent=2)}

Analyse for drug interactions and contraindications. Return structured JSON.
"""
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def _call_groq(medications: list[str], diagnoses: list[str], kg_results: dict) -> dict[str, Any]:
    """Groq fallback."""
    client = Groq(api_key=settings.groq_api_key)
    prompt = f"""
MEDICATIONS: {json.dumps(medications)}
DIAGNOSES: {json.dumps(diagnoses)}
KG FINDINGS: {json.dumps(kg_results)}
"""
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
    Full drug interaction pipeline:
    1. Query KG (Neo4j → local JSON fallback) for structural drug/condition data
    2. Run LLM analysis (Gemini → Groq fallback) on combined context
    """
    kg_results = kg_loader.query_drug_interactions(
        drug_names=medications,
        conditions=diagnoses,
    )

    if settings.has_gemini:
        try:
            result = _call_gemini(medications, diagnoses, kg_results)
            result["kg_source"] = kg_results.get("source")
            return result
        except Exception as exc:
            log.warning(f"[drug_agent] Gemini failed: {exc} — falling back to Groq")

    if settings.has_groq:
        try:
            result = _call_groq(medications, diagnoses, kg_results)
            result["kg_source"] = kg_results.get("source")
            return result
        except Exception as exc:
            log.warning(f"[drug_agent] Groq failed: {exc}")

    return {
        "interactions": kg_results.get("interactions", []),
        "contraindications": kg_results.get("contraindications", []),
        "overall_risk": "unknown",
        "summary": "LLM analysis unavailable — KG results only.",
        "kg_source": kg_results.get("source"),
    }
