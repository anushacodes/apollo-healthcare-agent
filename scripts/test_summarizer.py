#!/usr/bin/env python3
"""
scripts/test_summarizer.py
--------------------------
End-to-end smoke test for the Summarization Agent.

Tests three scenarios in order:
  1. Stub mode  (force_stub=True) — no API calls, instant
  2. Live mode  (uses real Groq → Gemini chain from .env keys)
  3. Validates the ClinicalSummary Pydantic schema on both results

Run from the medcontext/ root:
    python scripts/test_summarizer.py

Flags:
    --stub-only   Skip the live API call (useful in CI / offline)
    --live-only   Skip the stub test and go straight to live
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ── make app importable ───────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.summarizer import build_context, run_summarizer
from app.models import ClinicalSummary

# ── James Hartwell demo patient (inline, mirrors demo-data.js) ──
DEMO_PATIENT = {
    "patient_id": "demo-jh-001",
    "patient": {"name": "James Hartwell", "dob": "1966-03-14", "mrn": "JH-001", "age": 58},
    "summary": {
        "summary_narrative": (
            "Mr James Hartwell is a 58-year-old man with SLE complicated by Class III lupus "
            "nephritis, pericarditis, AIHA, and antiphospholipid syndrome. Admitted Oct 2023 "
            "with creatinine 198, Hb 9.2, and pericardial effusion. Treated with IV "
            "methylprednisolone and commenced MMF. November 2023 review shows improvement."
        ),
        "diagnoses": [
            {"name": "SLE",                             "icd_code": "M32.9",  "status": "active"},
            {"name": "Lupus Nephritis Class III",       "icd_code": "M32.14", "status": "active — partial response"},
            {"name": "Lupus Pericarditis / Serositis",  "icd_code": "M32.12", "status": "resolving"},
            {"name": "Antiphospholipid Syndrome (APS)", "icd_code": "D68.61", "status": "active"},
            {"name": "Autoimmune Haemolytic Anaemia",   "icd_code": "D59.1",  "status": "improving"},
        ],
        "medications": [
            {"name": "Prednisolone",          "dose": "60mg tapering",      "frequency": "Once daily"},
            {"name": "Mycophenolate mofetil", "dose": "1.5g",               "frequency": "Twice daily"},
            {"name": "Hydroxychloroquine",    "dose": "200mg",               "frequency": "Twice daily"},
            {"name": "Warfarin",              "dose": "INR target 2.5–3.5", "frequency": "Once daily"},
        ],
        "allergies": ["Penicillin — anaphylaxis", "Sulfonamides — rash"],
        "lab_results": [
            {"test_name": "Creatinine",   "value": "142",  "unit": "µmol/L",    "flag": "high"},
            {"test_name": "eGFR",         "value": "49",   "unit": "mL/min",    "flag": "low"},
            {"test_name": "Haemoglobin",  "value": "11.4", "unit": "g/dL",      "flag": "low"},
            {"test_name": "anti-dsDNA",   "value": "248",  "unit": "IU/mL",     "flag": "high"},
            {"test_name": "CRP",          "value": "18",   "unit": "mg/L",      "flag": "high"},
        ],
        "clinical_flags": [
            {"text": "Borderline fasting glucose — possible steroid-induced diabetes.", "type": "warn"},
            {"text": "New persistent headaches — neuropsychiatric lupus must be excluded.", "type": "warn"},
        ],
    },
}

SEP = "=" * 64


def print_summary(result: ClinicalSummary, label: str) -> None:
    print(f"\n{SEP}")
    print(f"  {label}")
    print(SEP)
    print(f"  Model: {result.model_used}")
    print(f"  Generated at: {result.generated_at}")
    print(f"\n  CHIEF COMPLAINT\n  {result.chief_complaint}")
    print(f"\n  HPI\n  {result.history_of_present_illness[:300]}…")
    print(f"\n  CLINICAL ASSESSMENT\n  {result.clinical_assessment[:300]}…")
    print(f"\n  MEDICATIONS ({len(result.current_medications)})")
    for m in result.current_medications:
        print(f"    • {m}")
    if result.key_concerns:
        print(f"\n  KEY CONCERNS ({len(result.key_concerns)})")
        for c in result.key_concerns:
            print(f"    ⚠ {c}")
    if result.follow_up_actions:
        print(f"\n  FOLLOW-UP ACTIONS ({len(result.follow_up_actions)})")
        for f in result.follow_up_actions:
            print(f"    → {f}")
    if result.patient_facing_summary:
        print(f"\n  PATIENT-FACING SUMMARY\n  {result.patient_facing_summary[:250]}…")


def test_context_builder() -> None:
    print(f"\n{SEP}\n  Context builder\n{SEP}")
    ctx = build_context(DEMO_PATIENT)
    print(ctx[:800])
    print("…")
    assert "James Hartwell" in ctx
    assert "ACTIVE DIAGNOSES" in ctx
    assert "CURRENT MEDICATIONS" in ctx
    print("  ✓ Context builder passed")


def test_stub(live_only: bool = False) -> None:
    if live_only:
        return
    print(f"\n{SEP}\n  Stub mode (force_stub=True)\n{SEP}")
    t0 = time.perf_counter()
    result = run_summarizer(DEMO_PATIENT, force_stub=True)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Elapsed: {elapsed:.0f}ms")
    assert isinstance(result, ClinicalSummary)
    assert result.chief_complaint
    assert isinstance(result.current_medications, list)
    print_summary(result, "STUB RESULT")
    print("\n  ✓ Stub test passed")


def test_live(stub_only: bool = False) -> None:
    if stub_only:
        print("\n  [skipped] Live test (--stub-only flag set)")
        return
    print(f"\n{SEP}\n  Live mode (Groq → Gemini chain)\n{SEP}")

    from app.config import settings
    if not settings.has_groq and not settings.has_gemini:
        print("  [skipped] No GROQ_API_KEY or GEMINI_API_KEY in .env")
        return

    print(f"  Groq available:   {settings.has_groq}  ({settings.groq_model})")
    print(f"  Gemini available: {settings.has_gemini}  ({settings.gemini_model})")

    t0 = time.perf_counter()
    result = run_summarizer(DEMO_PATIENT, force_stub=False)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Elapsed: {elapsed:.0f}ms")

    assert isinstance(result, ClinicalSummary)
    assert result.chief_complaint
    assert result.history_of_present_illness
    assert result.clinical_assessment
    assert isinstance(result.current_medications, list)
    print_summary(result, "LIVE RESULT")
    print(f"\n  ✓ Live test passed  [{result.model_used}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarizer smoke test")
    parser.add_argument("--stub-only", action="store_true", help="Skip live API call")
    parser.add_argument("--live-only", action="store_true", help="Skip stub test")
    args = parser.parse_args()

    print(f"\n{'=' * 64}")
    print("  Apollo Summarization Agent — Smoke Test")
    print(f"{'=' * 64}")

    test_context_builder()
    test_stub(live_only=args.live_only)
    test_live(stub_only=args.stub_only)

    print(f"\n{SEP}")
    print("  All tests passed ✓")
    print(SEP)


if __name__ == "__main__":
    main()
