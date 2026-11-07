from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from app.config import settings
from app.ingestion.structured import ExtractionRequest
from app.review import store
from app.review.clarification import resolve_calculator, resolve_finding
from app.review.extraction import create_extraction, reviewed_fields
from app.review.models import (
    ClarificationRequest,
    DecisionRequest,
    FindingClarificationRequest,
    ReviewerRequest,
    VersionRequest,
)

router = APIRouter(prefix="/api/review", tags=["review"])
COOKIE = "apollo_reviewer"


def same_origin(request: Request):
    origin = request.headers.get("origin")
    allowed = {*settings.allowed_origins, str(request.base_url).rstrip("/")}
    if origin and origin not in allowed:
        raise HTTPException(403, "Review changes must come from an allowed workspace origin")


def reviewer(request: Request, apollo_reviewer: str | None = Cookie(default=None)) -> dict:
    same_origin(request)
    identity = store.get_reviewer(apollo_reviewer)
    if not identity:
        raise HTTPException(401, "Start a reviewer session before making a decision")
    return identity


@router.get("/session")
def session(apollo_reviewer: str | None = Cookie(default=None)):
    return {"reviewer": store.get_reviewer(apollo_reviewer)}


@router.post("/session", dependencies=[Depends(same_origin)])
def start_session(body: ReviewerRequest, response: Response, request: Request):
    token, identity = store.new_reviewer(body.name)
    response.set_cookie(COOKIE, token, max_age=7 * 86400, path="/api/review", httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
    return {"reviewer": identity}


@router.get("/patients/{patient_id}/runs")
def runs(patient_id: str, kind: Literal["analysis", "extraction"] = "analysis"):
    return {"runs": store.list_runs(patient_id, kind)}


@router.post("/patients/{patient_id}/extract", dependencies=[Depends(same_origin)])
def extract(patient_id: str, body: ExtractionRequest):
    return create_extraction(patient_id, body.source_name, body.text)


@router.get("/patients/{patient_id}/fields")
def fields(patient_id: str):
    return {"fields": reviewed_fields(patient_id)}


@router.get("/runs/{run_id}")
def run(run_id: str):
    return store.get_run(run_id)


@router.get("/runs/{run_id}/sources/{source_id:path}")
def source(run_id: str, source_id: str):
    result = store.get_run(run_id)["sources"].get(source_id)
    if not result:
        raise HTTPException(404, "Evidence source not found")
    return result


@router.post("/runs/{run_id}/findings/{finding_id}/decision")
def decision(run_id: str, finding_id: str, body: DecisionRequest, identity: dict = Depends(reviewer)):
    return store.decide(run_id, finding_id, body, identity)


@router.post("/runs/{run_id}/clarifications/{clarification_id}")
def clarify(run_id: str, clarification_id: str, body: ClarificationRequest, identity: dict = Depends(reviewer)):
    return resolve_calculator(run_id, clarification_id, body, identity)


@router.post("/runs/{run_id}/clarifications/{clarification_id}/response")
def respond(run_id: str, clarification_id: str, body: FindingClarificationRequest,
            identity: dict = Depends(reviewer)):
    return resolve_finding(run_id, clarification_id, body, identity)


@router.post("/runs/{run_id}/finalize")
def finalize(run_id: str, body: VersionRequest, identity: dict = Depends(reviewer)):
    return store.finalize(run_id, body.version, identity)


@router.get("/runs/{run_id}/final")
def final(run_id: str):
    return store.final_output(run_id)


@router.get("/runs/{run_id}/audit")
def audit(run_id: str):
    return store.audit_history(run_id)
