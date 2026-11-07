import copy
import json

from fastapi import HTTPException

from app.agent.diagnostics.nodes import diagnosis_node, summarizer_node
from app.agent.diagnostics.state import AgentState
from app.agent.summarizer import build_context
from app.review.calculators import execute_call, validate_values
from app.review.store import get_run, mutate, now
from app.review.workflow import build_findings


def resolve_finding(run_id, clarification_id, request, reviewer):
    def change(run):
        question = next((q for q in run["clarifications"] if q["id"] == clarification_id), None)
        if not question or question["kind"] != "finding":
            raise HTTPException(404, "Finding clarification not found")
        if question["status"] != "pending":
            raise HTTPException(409, "Clarification already resolved")
        response = request.response.strip()
        if len(response) < 3:
            raise HTTPException(422, "Enter a clarification response")
        source_id = f"clarification/{clarification_id}"
        run["sources"][source_id] = {"label": f"Clarification from {reviewer['name']}",
                                     "text": response, "kind": "reviewer_supplied"}
        finding = next(f for f in run["findings"] if f["id"] == question["finding_id"])
        finding["evidence"].append({"source_id": source_id, "start": 0, "end": len(response),
                                     "quote": response, "assertion": "reviewer_supplied"})
        finding["status"] = "pending"
        finding["decision"] = None
        question.update(status="answered", response=response, reviewer=reviewer, answered_at=now())
        return {"clarification": question, "finding": finding}
    return mutate(run_id, request.version, reviewer, "clarification_answered", change)


def resolve_calculator(run_id, clarification_id, request, reviewer):
    # Calculate and regenerate affected downstream drafts outside the write lock.
    prepared = get_run(run_id, internal=True)
    if prepared["version"] != request.version or prepared["status"] == "finalized":
        raise HTTPException(409, "Reload this review before changing it")
    question = next((q for q in prepared["clarifications"] if q["id"] == clarification_id), None)
    if not question or question["kind"] != "calculator":
        raise HTTPException(404, "Calculator clarification not found")
    if question["status"] != "pending":
        raise HTTPException(409, "Clarification already resolved")
    if len(request.reason.strip()) < 3:
        raise HTTPException(422, "A reason is required")
    if request.action == "skip" and request.values:
        raise HTTPException(422, "Skipped calculators must not include input values")
    if request.action == "answer":
        if set(request.values) != {f["name"] for f in question["fields"]}:
            raise HTTPException(422, "Answer every requested field; existing inputs cannot be changed here")
        try:
            params = validate_values(question["tool"], {**question["inputs"], **request.values})
            result = execute_call(question["tool"], params)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result.get("error") or "error" in result.get("result", {}) or result.get("status") != "complete":
            raise HTTPException(422, result.get("error") or "Calculator inputs could not be used")
    else:
        result = {"tool": question["tool"], "status": "skipped", "reason": request.reason.strip()}
    snapshot = copy.deepcopy(prepared["analysis"])
    snapshot["calculator_results"] = [r for r in snapshot.get("calculator_results", [])
                                       if r["tool"] != question["tool"]] + [result]
    patient = prepared["patient_data"]
    context = build_context(patient)
    source_id = f"clarification/{clarification_id}"
    supplied = json.dumps({"action": request.action, "values": request.values, "reason": request.reason.strip()},
                          ensure_ascii=False, indent=2)
    if request.action == "answer":
        context += "\nREVIEWER-SUPPLIED CALCULATOR INPUTS:\n" + supplied
    state = AgentState(patient_id=prepared["patient_id"], patient_data=patient, anonymized_notes=context,
                       calculator_results=snapshot["calculator_results"],
                       interactions=snapshot.get("interactions", {}), kg_matches=snapshot.get("kg_matches", []))
    diagnosis = diagnosis_node(state)
    state.diagnoses = diagnosis["diagnoses"]
    summary = summarizer_node(state)
    snapshot["diagnoses"] = state.diagnoses
    snapshot["final_summary"] = summary["final_summary"].model_dump(mode="json") if summary["final_summary"] else None
    sources = copy.deepcopy(prepared["sources"])
    sources[source_id] = {"label": f"Calculator clarification from {reviewer['name']}",
                          "text": supplied, "kind": "reviewer_supplied"}
    findings = build_findings(patient, snapshot, sources)
    # Preserve unrelated medication/concern decisions; changed dependent drafts need fresh review.
    old = {f["id"]: f for f in prepared["findings"]}
    for finding in findings:
        if finding["kind"] in ("medication", "concern") and finding["id"] in old:
            finding.update(status=old[finding["id"]]["status"], decision=old[finding["id"]]["decision"])
        if finding["kind"] == "calculator" and finding["id"] == f"calculator-{question['tool']}":
            finding["evidence"].append({"source_id": source_id, "start": 0, "end": len(supplied),
                                         "quote": supplied, "assertion": "reviewer_supplied"})

    def change(run):
        original_findings = run["findings"]
        for pending in run["clarifications"]:
            if pending["kind"] == "finding" and pending["status"] == "pending" and not any(
                f["id"] == pending["finding_id"] for f in findings
            ):
                previous = next(f for f in original_findings if f["id"] == pending["finding_id"])
                findings.append(previous)
        run.update(analysis=snapshot, findings=findings, sources=sources)
        stored = next(q for q in run["clarifications"] if q["id"] == clarification_id)
        stored.update(status="answered" if request.action == "answer" else "skipped", values=request.values,
                      reason=request.reason.strip(), reviewer=reviewer, answered_at=now())
        # Existing finding clarification requests still apply to the fresh draft.
        for pending in run["clarifications"]:
            if pending["kind"] == "finding" and pending["status"] == "pending":
                for finding in run["findings"]:
                    if finding["id"] == pending["finding_id"]:
                        finding["status"] = "clarification_requested"
        return {"clarification": stored, "previous_findings": original_findings, "new_findings": findings,
                "calculator_result": result}
    return mutate(run_id, request.version, reviewer, "calculator_resumed", change)
