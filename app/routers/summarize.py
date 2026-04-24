from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Path

from app.agent.summarizer import run_summarizer
from app.models import ClinicalSummary, SummarizeRequest, SummarizeResponse

router = APIRouter(prefix="/api/patients", tags=["summarize"])

@router.post("/{patient_id}/summarize", response_model=SummarizeResponse)
async def summarize_patient(
    patient_id: str = Path(..., description="Patient ID (use 'demo-jh-001' for demo)"),
    body: SummarizeRequest = None,
) -> SummarizeResponse:
    t0 = time.perf_counter()

    if body and body.patient_id != patient_id:
        raise HTTPException(
            status_code=400,
            detail="patient_id in path and body do not match.",
        )

    resolved_patient = _resolve_patient(patient_id, body)

    try:
        summary: ClinicalSummary = run_summarizer(resolved_patient)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Summarization failed: {exc}") from exc

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return SummarizeResponse(
        patient_id=patient_id,
        summary=summary,
        cached=False,
        elapsed_ms=round(elapsed_ms, 1),
    )

def _resolve_patient(patient_id: str, body: SummarizeRequest | None) -> dict:
    return {
        "patient_id": patient_id,
        "patient": {"name": "Unknown", "age": None, "dob": None, "mrn": patient_id},
        "summary": {
            "summary_narrative": "",
            "diagnoses": [],
            "medications": [],
            "allergies": [],
            "lab_results": [],
            "clinical_flags": [],
            "timeline": [],
        },
        "source_documents": [],
    }
