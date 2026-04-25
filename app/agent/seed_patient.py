from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SEED_DIR = Path(__file__).parent.parent.parent / "data" / "seed"


def _read(filename: str) -> str:
    path = _SEED_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_case_a() -> dict[str, Any]:
    """
    Case A — James Hartwell (SLE + Lupus Nephritis)
    Pre-loaded from seed data files. No PII upload required.
    """
    dummy_path = _SEED_DIR / "dummy_patient.json"
    if dummy_path.exists():
        base = json.loads(dummy_path.read_text(encoding="utf-8"))
    else:
        base = {}

    # Attach the raw clinical text documents for ingestion/display
    base["source_documents"] = {
        "clinical_report": _read("james_hartwell_clinical_report.txt"),
        "handwritten_note_1": _read("james_hartwell_handwritten_note_1.txt"),
        "handwritten_note_2": _read("james_hartwell_handwritten_note_2.txt"),
        "labs": _read("james_hartwell_labs.txt"),
        "transcript": _read("james_hartwell_transcript.txt"),
        "xray_report": _read("james_hartwell_xray_report.txt"),
    }
    base["case_label"] = "Case A — James Hartwell (SLE / Lupus Nephritis)"
    return base


def load_case_b() -> dict[str, Any]:
    """
    Case B — Synthetic COPD / Heart Failure patient.
    Derived from local KG knowledge blocks; no real PII.
    """
    return {
        "patient_id": "demo-case-b",
        "case_label": "Case B — Synthetic COPD / Heart Failure",
        "patient": {
            "name": "Robert Chen",
            "age": 71,
            "sex": "male",
            "dob": "1953-06-08",
            "mrn": "RC-DEMO-002",
        },
        "summary": {
            "summary_narrative": (
                "Mr Robert Chen is a 71-year-old retired engineer with a 30-pack-year smoking history. "
                "He presents with a 6-month history of worsening exertional dyspnoea, bilateral ankle oedema, "
                "and a productive cough. Spirometry confirms FEV1/FVC < 0.70 (GOLD Stage III). "
                "Echocardiography shows an EF of 38% consistent with HFrEF. "
                "Admitted for IV diuresis and optimisation of HF therapy."
            ),
            "diagnoses": [
                {"name": "COPD", "icd_code": "J44.1", "status": "active — GOLD III"},
                {"name": "Heart Failure with Reduced EF", "icd_code": "I50.20", "status": "active — decompensated"},
                {"name": "Type 2 Diabetes", "icd_code": "E11.9", "status": "active — suboptimal control"},
                {"name": "Hypertension", "icd_code": "I10", "status": "controlled on medication"},
            ],
            "medications": [
                {"name": "Furosemide", "dose": "80mg IV", "frequency": "Once daily"},
                {"name": "Carvedilol", "dose": "12.5mg", "frequency": "Twice daily"},
                {"name": "Ramipril", "dose": "5mg", "frequency": "Once daily"},
                {"name": "Tiotropium inhaler", "dose": "18mcg", "frequency": "Once daily"},
                {"name": "Metformin", "dose": "500mg", "frequency": "Twice daily (held during admission)"},
                {"name": "Spironolactone", "dose": "25mg", "frequency": "Once daily"},
            ],
            "allergies": ["Aspirin — bronchospasm"],
            "lab_results": [
                {"test_name": "BNP", "value": "1840", "unit": "pg/mL", "flag": "critical_high"},
                {"test_name": "Creatinine", "value": "138", "unit": "µmol/L", "flag": "high"},
                {"test_name": "eGFR", "value": "51", "unit": "mL/min", "flag": "low"},
                {"test_name": "HbA1c", "value": "8.1", "unit": "%", "flag": "high"},
                {"test_name": "FEV1", "value": "42", "unit": "% predicted", "flag": "low"},
                {"test_name": "SpO2", "value": "91", "unit": "%", "flag": "low"},
            ],
            "clinical_flags": [
                {"text": "Aspirin allergy — avoid NSAIDs and aspirin-containing compounds.", "type": "critical"},
                {"text": "Metformin held — monitor renal function before re-starting.", "type": "warn"},
                {"text": "Carvedilol may worsen bronchospasm — monitor closely.", "type": "warn"},
            ],
        },
        "source_documents": {},
        "calculator_hints": {
            # ASCVD inputs — derived from clinical context (71M, COPD/HF, smoker, T2DM)
            "age": 71,
            "sex": "male",
            "race": "white",
            "total_cholesterol": 198.0,
            "hdl_cholesterol": 38.0,
            "systolic_bp": 148.0,
            # Wells DVT — not primary concern for this case
        },
    }


def load_case_c() -> dict[str, Any]:
    """
    Case C — Synthetic Pulmonary Embolism / Post-op patient.
    """
    return {
        "patient_id": "demo-case-c",
        "case_label": "Case C — Pulmonary Embolism (Post-surgical)",
        "patient": {
            "name": "Sarah Okonkwo",
            "age": 44,
            "sex": "female",
            "dob": "1980-11-22",
            "mrn": "SO-DEMO-003",
        },
        "summary": {
            "summary_narrative": (
                "Ms Sarah Okonkwo is a 44-year-old woman, Day 5 post right total knee replacement. "
                "She presents acutely with pleuritic chest pain, dyspnoea, and haemoptysis. "
                "Wells PE score of 7 (high probability). CTPA confirms right lower lobe segmental PE. "
                "No haemodynamic instability. Commenced on therapeutic LMWH. "
                "Background of oral contraceptive use and thrombophilia screen pending."
            ),
            "diagnoses": [
                {"name": "Pulmonary Embolism", "icd_code": "I26.99", "status": "acute — confirmed"},
                {"name": "Post-operative state", "icd_code": "Z48.89", "status": "Day 5 post right TKR"},
                {"name": "Suspected thrombophilia", "icd_code": "D68.9", "status": "under investigation"},
            ],
            "medications": [
                {"name": "Enoxaparin", "dose": "1mg/kg SC", "frequency": "Twice daily"},
                {"name": "Paracetamol", "dose": "1g", "frequency": "Four times daily"},
                {"name": "Oxycodone", "dose": "5mg", "frequency": "PRN (max 4-hourly)"},
            ],
            "allergies": ["Heparin — HIT suspected (prior admission)"],
            "lab_results": [
                {"test_name": "D-dimer", "value": "4.8", "unit": "µg/mL FEU", "flag": "critical_high"},
                {"test_name": "Troponin I", "value": "0.04", "unit": "ng/mL", "flag": "normal"},
                {"test_name": "BNP", "value": "210", "unit": "pg/mL", "flag": "high"},
                {"test_name": "SpO2", "value": "93", "unit": "% on 2L O2", "flag": "low"},
                {"test_name": "INR", "value": "1.1", "unit": "", "flag": "normal"},
            ],
            "clinical_flags": [
                {"text": "Heparin allergy (HIT) — LMWH used cautiously; fondaparinux alternative if HIT confirmed.", "type": "critical"},
                {"text": "OCP — discuss cessation given confirmed PE.", "type": "warn"},
                {"text": "Thrombophilia screen — do not anticoagulate until baseline results drawn.", "type": "info"},
            ],
        },
        "source_documents": {},
        "calculator_hints": {
            # Wells DVT — post-surgical PE patient (Day 5 TKR, confirmed PE, no prior DVT documented)
            "wells_dvt_score": {
                "active_cancer": False,
                "paralysis_or_immobilization": False,
                "bedridden_3_days_or_surgery_12wk": True,
                "localized_tenderness": True,
                "entire_leg_swollen": True,
                "calf_swelling_3cm_greater": True,
                "pitting_oedema": False,
                "collateral_superficial_veins": False,
                "previous_dvt": False,
                "alternative_diagnosis_as_likely": False,
            },
        },
    }


# Registry for the API / frontend to reference by key
CASES: dict[str, Any] = {
    "case_a": load_case_a,
    "case_b": load_case_b,
    "case_c": load_case_c,
}


def get_case(case_key: str) -> dict[str, Any] | None:
    loader = CASES.get(case_key)
    return loader() if loader else None


def list_cases() -> list[dict[str, str]]:
    return [
        {"key": "case_a", "label": "Case A — James Hartwell (SLE / Lupus Nephritis)"},
        {"key": "case_b", "label": "Case B — Robert Chen (COPD / Heart Failure)"},
        {"key": "case_c", "label": "Case C — Sarah Okonkwo (Pulmonary Embolism)"},
    ]
