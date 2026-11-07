import asyncio
import time

from fastapi import APIRouter, HTTPException, Path

from app.agent.seed_patient import get_case
from app.review.extraction import with_reviewed_fields
from app.agent.summarizer import run_summarizer
from app.models import ClinicalSummary, SummarizeRequest, SummarizeResponse

router = APIRouter(prefix="/api/patients", tags=["summarize"])


@router.post("/{patient_id}/summarize", response_model=SummarizeResponse)
async def summarize_patient(
    patient_id: str = Path(..., description="Patient ID or demo case key (e.g. 'case_a')"),
    body: SummarizeRequest = None,
) -> SummarizeResponse:
    t0 = time.perf_counter()

    if body and body.patient_id != patient_id:
        raise HTTPException(status_code=400, detail="patient_id in path and body do not match.")

    patient_data = _resolve_patient(patient_id, body)

    try:
        summary: ClinicalSummary = await asyncio.to_thread(
            run_summarizer, patient_data, skip_cache=bool(body and body.force_regenerate),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Summarization failed: {exc}") from exc

    return SummarizeResponse(
        patient_id=patient_id,
        summary=summary,
        cached=False,
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


def _resolve_patient(patient_id: str, body: SummarizeRequest | None) -> dict:
    # Try demo seed cases first (case_a, case_b, case_c)
    case = get_case(patient_id)
    if case:
        return with_reviewed_fields(case)

    # Future: load from database by patient_id
    raise HTTPException(
        status_code=404, 
        detail=f"Patient {patient_id} not found. Summarization currently supports demo case keys only."
    )
