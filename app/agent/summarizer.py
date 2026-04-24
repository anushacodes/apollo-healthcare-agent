from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from groq import Groq
import google.generativeai as genai

from app.config import settings
from app.models import ClinicalSummary

log = logging.getLogger(__name__)

# Prompts
_SYSTEM_PROMPT = """\
You are a senior clinical documentation specialist. Your task is to read
aggregated patient information and produce a structured clinical summary.

RULES:
1. Respond ONLY with valid JSON — no markdown fences, no extra text.
2. Follow the schema exactly; do not add or omit fields.
3. chief_complaint: 1-2 sentences on the primary presenting complaint.
4. history_of_present_illness: concise HPI covering onset, duration,
   associated symptoms, relevant background, and recent trajectory.
5. clinical_assessment: interpretation of active problems, disease
   severity, treatment response, and key risk factors.
6. current_medications: list of strings, each formatted as
   "Drug name — dose, frequency".
7. patient_facing_summary: plain English for the patient, no jargon.
8. key_concerns: up to 5 urgent clinical concerns as short strings.
9. follow_up_actions: concrete next steps (tests, referrals, appointments).

JSON schema:
{
  "chief_complaint":               "<string>",
  "history_of_present_illness":   "<string>",
  "clinical_assessment":          "<string>",
  "current_medications":          ["<string>", ...],
  "patient_facing_summary":       "<string or null>",
  "key_concerns":                 ["<string>", ...],
  "follow_up_actions":            ["<string>", ...]
}
"""

_USER_TEMPLATE = """\
=== PATIENT CONTEXT ===

{context}

=== TASK ===
Generate the structured clinical summary JSON described in the system prompt.
"""

# Context builder
def build_context(patient_data: dict) -> str:
    lines: list[str] = []
    p = patient_data.get("patient", {})
    s = patient_data.get("summary", patient_data)

    lines.append(f"PATIENT: {p.get('name', 'Unknown')}  |  Age: {p.get('age', '?')}  |  MRN: {p.get('mrn', '?')}\n")

    if narrative := s.get("summary_narrative", ""):
        lines.append(f"BACKGROUND NARRATIVE:\n{narrative}\n")

    if diagnoses := s.get("diagnoses", []):
        lines.append("ACTIVE DIAGNOSES:")
        for dx in diagnoses:
            name = dx.get("name", "?") if isinstance(dx, dict) else str(dx)
            icd = dx.get("icd_code", "") if isinstance(dx, dict) else ""
            status = dx.get("status", "") if isinstance(dx, dict) else ""
            lines.append(f"  • {name}  [{icd}]  — {status}")
        lines.append("")

    if meds := s.get("medications", []):
        lines.append("CURRENT MEDICATIONS:")
        for m in meds:
            name = m.get("name", "?") if isinstance(m, dict) else str(m)
            dose = m.get("dose", "") if isinstance(m, dict) else ""
            freq = m.get("frequency", "") if isinstance(m, dict) else ""
            lines.append(f"  • {name}  —  {dose}  {freq}".strip())
        lines.append("")

    if allergies := s.get("allergies", []):
        lines.append(f"ALLERGIES: {'; '.join(allergies)}\n")

    if labs := s.get("lab_results", []):
        lines.append("LATEST LABS:")
        for lab in labs:
            name = lab.get("test_name", "?") if isinstance(lab, dict) else str(lab)
            val = lab.get("value", "?") if isinstance(lab, dict) else "?"
            unit = lab.get("unit", "") if isinstance(lab, dict) else ""
            flag = lab.get("flag", "") if isinstance(lab, dict) else ""
            lines.append(f"  • {name}: {val} {unit}  [{flag}]")
        lines.append("")

    if flags := s.get("clinical_flags", []):
        lines.append("CLINICAL FLAGS:")
        for f in flags:
            text = f.get("text", f) if isinstance(f, dict) else str(f)
            lines.append(f"  ⚠ {text}")
        lines.append("")

    return "\n".join(lines)

# LLM calls
def _call_groq(context: str) -> dict[str, Any]:
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": _USER_TEMPLATE.format(context=context)},
        ],
        temperature=0.1,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)

def _call_gemini(context: str) -> dict[str, Any]:
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=_SYSTEM_PROMPT,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    response = model.generate_content(_USER_TEMPLATE.format(context=context))
    return json.loads(response.text)

# Public API
def run_summarizer(patient_data: dict) -> ClinicalSummary:
    t0 = time.perf_counter()
    patient_id = patient_data.get("patient_id", "unknown")
    context = build_context(patient_data)

    if settings.has_groq:
        try:
            log.info(f"[summarizer] Trying Groq ({settings.groq_model}) for {patient_id}")
            raw = _call_groq(context)
            return _validate(raw, patient_id, f"groq/{settings.groq_model}", t0)
        except Exception as exc:
            log.warning(f"[summarizer] Groq failed: {exc} — falling back to Gemini")

    if settings.has_gemini:
        try:
            log.info(f"[summarizer] Trying Gemini ({settings.gemini_model}) for {patient_id}")
            raw = _call_gemini(context)
            return _validate(raw, patient_id, f"gemini/{settings.gemini_model}", t0)
        except Exception as exc:
            log.warning(f"[summarizer] Gemini failed: {exc}")

    raise RuntimeError("All LLM providers failed or are unavailable.")

def _validate(raw: dict[str, Any], patient_id: str, model_used: str, t0: float) -> ClinicalSummary:
    elapsed = (time.perf_counter() - t0) * 1000
    log.info(f"[summarizer] Summary generated in {elapsed:.0f}ms via {model_used}")

    return ClinicalSummary(
        chief_complaint=raw.get("chief_complaint", ""),
        history_of_present_illness=raw.get("history_of_present_illness", ""),
        clinical_assessment=raw.get("clinical_assessment", ""),
        current_medications=raw.get("current_medications", []),
        patient_facing_summary=raw.get("patient_facing_summary"),
        key_concerns=raw.get("key_concerns", []),
        follow_up_actions=raw.get("follow_up_actions", []),
        generated_at=datetime.now(timezone.utc),
        model_used=model_used,
        patient_id=patient_id,
    )
