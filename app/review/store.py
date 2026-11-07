import copy
import json
import secrets
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

from app.agent.sqlite_cache import _get_conn, hash_payload, hash_text


def now() -> str:
    return datetime.now(UTC).isoformat()


def _append_event(conn, run: dict, event: str, reviewer: dict | None, details: dict) -> None:
    row = conn.execute("SELECT hash FROM review_events WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
                       (run["id"],)).fetchone()
    previous = row["hash"] if row else "GENESIS"
    payload = {"run_id": run["id"], "version": run["version"], "event": event, "at": now(),
               "reviewer": reviewer, "details": details, "state_hash": hash_payload(run)}
    digest = hash_payload({"previous_hash": previous, "payload": payload})
    conn.execute("INSERT INTO review_events(run_id, payload, previous_hash, hash) VALUES (?, ?, ?, ?)",
                 (run["id"], json.dumps(payload), previous, digest))


def create_run(patient, snapshot, sources, findings, clarifications, *, kind="analysis") -> dict:
    run = {"id": str(uuid.uuid4()), "patient_id": patient.get("patient_id", "unknown"),
           "created_at": now(), "kind": kind, "version": 1, "status": "needs_clarification" if clarifications else "draft",
           "patient_data": patient, "original_analysis": copy.deepcopy(snapshot), "analysis": snapshot,
           "sources": sources, "findings": findings, "clarifications": clarifications}
    with _get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO review_runs VALUES (?, ?, ?, ?, ?)",
                     (run["id"], run["patient_id"], run["created_at"], 1, json.dumps(run)))
        _append_event(conn, run, "draft_created", None, {"finding_count": len(findings)})
    return public_run(run)


def _load(conn, run_id: str) -> dict:
    row = conn.execute("SELECT state FROM review_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Review run not found")
    return json.loads(row["state"])


def public_run(run: dict) -> dict:
    return {key: value for key, value in run.items() if key not in ("patient_data", "original_analysis")}


def get_run(run_id: str, *, internal: bool = False) -> dict:
    run = _load(_get_conn(), run_id)
    return run if internal else public_run(run)


def list_runs(patient_id: str, kind: str = "analysis") -> list[dict]:
    rows = _get_conn().execute(
        "SELECT state FROM review_runs WHERE patient_id = ? AND COALESCE(json_extract(state, '$.kind'), 'analysis') = ? ORDER BY created_at DESC LIMIT 50", (patient_id, kind),
    ).fetchall()
    return [{key: run[key] for key in ("id", "created_at", "status", "version")}
            for run in (json.loads(row["state"]) for row in rows)]


def mutate(run_id: str, version: int, reviewer: dict, event: str, change) -> dict:
    with _get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        run = _load(conn, run_id)
        if run["version"] != version:
            raise HTTPException(409, "This review changed. Reload it before saving.")
        if run["status"] == "finalized":
            raise HTTPException(409, "Finalized reviews cannot be changed. Run a new analysis.")
        details = change(run)
        run["version"] += 1
        if run["status"] != "finalized":
            run["status"] = "needs_clarification" if (
                any(q["status"] == "pending" for q in run["clarifications"]) or
                any(f["status"] == "clarification_requested" for f in run["findings"])
            ) else "draft"
        conn.execute("UPDATE review_runs SET state = ?, version = ? WHERE id = ?",
                     (json.dumps(run), run["version"], run_id))
        _append_event(conn, run, event, reviewer, details)
    return public_run(run)


def decide(run_id, finding_id, request, reviewer):
    def change(run):
        finding = next((f for f in run["findings"] if f["id"] == finding_id), None)
        if not finding:
            raise HTTPException(404, "Finding not found")
        if any(q["status"] == "pending" and q.get("finding_id") == finding_id for q in run["clarifications"]):
            raise HTTPException(409, "Resolve the clarification before reviewing this finding")
        if request.action == "accepted" and (not finding["evidence"] or finding["assertion"] == "conflicting"):
            raise HTTPException(422, "Evidence is missing or conflicting. Edit with a reason, reject, or request clarification.")
        is_extraction = finding.get("kind") == "extraction"
        edited_data = None
        edited_text = request.edited_text
        if is_extraction:
            from app.ingestion.structured import describe
            from app.review.extraction import corrected_field

            if request.edited_text is not None:
                raise HTTPException(422, "Use structured fields to correct an extraction")
            if request.action == "edited":
                if request.edited_data is None:
                    raise HTTPException(422, "Enter the corrected structured fields")
                edited_data = corrected_field(finding, request.edited_data)
                edited_text = describe(edited_data["kind"], edited_data["data"])
        elif request.edited_data is not None:
            raise HTTPException(422, "Structured corrections apply only to extractions")
        if request.action != "edited" and request.edited_data is not None:
            raise HTTPException(422, "Only an edit may change extracted fields")
        if request.action == "edited" and not (edited_text or "").strip():
            raise HTTPException(422, "Enter the corrected finding")
        if request.action != "edited" and request.edited_text is not None:
            raise HTTPException(422, "Only an edit may change the finding text")
        previous = copy.deepcopy(finding)
        finding["status"] = request.action
        finding["decision"] = {"action": request.action, "reason": request.reason,
                               "edited_text": edited_text.strip() if edited_text else None,
                               "reviewer": reviewer, "at": now()}
        if edited_data is not None:
            finding["decision"]["edited_data"] = edited_data
        if request.action == "clarification_requested":
            run["clarifications"].append({"id": str(uuid.uuid4()), "kind": "finding",
                                          "finding_id": finding_id, "question": request.reason, "status": "pending"})
        return {"before": previous, "after": finding}
    return mutate(run_id, request.version, reviewer, "finding_decision", change)


def finalize(run_id, version, reviewer):
    def change(run):
        if not run["findings"]:
            raise HTTPException(409, "There are no findings to finalize")
        if any(q["status"] == "pending" for q in run["clarifications"]):
            raise HTTPException(409, "Resolve or skip pending clarifications first")
        if any(f["status"] not in ("accepted", "edited", "rejected") for f in run["findings"]):
            raise HTTPException(409, "Review every finding before finalizing")
        run["status"] = "finalized"
        run["finalized_by"] = reviewer
        run["finalized_at"] = now()
        if run.get("kind") == "extraction":
            from app.review.extraction import commit_fields

            run["committed_fields"] = commit_fields(_get_conn(), run, reviewer)
        return {"accepted": sum(f["status"] in ("accepted", "edited") for f in run["findings"])}
    return mutate(run_id, version, reviewer, "review_finalized", change)


def final_output(run_id):
    run = get_run(run_id)
    if run["status"] != "finalized":
        raise HTTPException(409, "This analysis has not been finalized by a reviewer")
    findings = [dict(f, text=(f["decision"].get("edited_text") or f["original_text"]),
                     **({"extracted": f["decision"].get("edited_data") or f["extracted"]} if f.get("kind") == "extraction" else {}))
                for f in run["findings"] if f["status"] in ("accepted", "edited")]
    return {"run_id": run_id, "patient_id": run["patient_id"], "status": "finalized",
            "reviewer": run["finalized_by"], "at": run["finalized_at"], "findings": findings}


def audit_history(run_id):
    get_run(run_id)
    rows = _get_conn().execute("SELECT * FROM review_events WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
    previous = "GENESIS"
    events = []
    valid = True
    for row in rows:
        payload = json.loads(row["payload"])
        valid &= row["previous_hash"] == previous and row["hash"] == hash_payload(
            {"previous_hash": previous, "payload": payload},
        )
        events.append(dict(payload, hash=row["hash"], previous_hash=row["previous_hash"]))
        previous = row["hash"]
    current = get_run(run_id, internal=True)
    valid &= bool(events) and events[-1]["state_hash"] == hash_payload(current)
    return {"events": events, "chain_valid": valid}


def new_reviewer(name: str) -> tuple[str, dict]:
    token = secrets.token_urlsafe(32)
    reviewer = {"id": str(uuid.uuid4()), "name": name}
    with _get_conn() as conn:
        conn.execute("INSERT INTO reviewer_sessions VALUES (?, ?, ?, ?)",
                     (hash_text(token), reviewer["id"], name, time.time() + 7 * 86400))
    return token, reviewer


def get_reviewer(token: str | None) -> dict | None:
    if not token:
        return None
    row = _get_conn().execute("SELECT * FROM reviewer_sessions WHERE token_hash = ? AND expires_at > ?",
                              (hash_text(token), time.time())).fetchone()
    return {"id": row["reviewer_id"], "name": row["name"]} if row else None
