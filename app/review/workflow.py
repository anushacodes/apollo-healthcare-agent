import asyncio
import json
import uuid

from app.agent.diagnostics.graph import run_graph_streaming
from app.agent.sqlite_cache import hash_text
from app.review.evidence import evidence_for, finding_assertion, record_sources


def build_findings(patient: dict, snapshot: dict, sources: dict) -> list[dict]:
    findings = []

    def add(key, kind, title, text, evidence, assertion="ai_suggested"):
        findings.append({"id": key, "kind": kind, "title": title, "original_text": text,
                         "assertion": assertion, "evidence": evidence, "status": "pending",
                         "decision": None})

    # Preserve historical/negated documented facts independently of the model's differential.
    proposed = snapshot.get("diagnoses", {}).get("proposed_diagnoses", [])
    documented = patient.get("summary", {}).get("diagnoses", [])
    proposed_by_name = {d.get("name", "").casefold(): d for d in proposed if isinstance(d, dict)}
    seen = set()
    for i, dx in enumerate([*documented, *proposed]):
        if not isinstance(dx, dict) or not dx.get("name"):
            continue
        name = dx["name"]
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        evidence = evidence_for(name, sources)
        assertion = finding_assertion(name, patient, evidence)
        interpretation = proposed_by_name.get(name.casefold(), {}).get("reasoning")
        text = f"{name} · {dx.get('status', 'AI suggested')} · {dx.get('icd_code') or 'No code recorded'}"
        if interpretation:
            text += f"\nDraft interpretation: {interpretation}"
        add(f"diagnosis-{hash_text(name.casefold())[:16]}", "diagnosis", name, text, evidence, assertion)
    interactions = snapshot.get("interactions", {})
    if "interactions" in snapshot and (interactions.get("error") or interactions.get("overall_risk") == "unknown"):
        add("medication-unavailable", "medication", "Medication review unavailable",
            "Automated medication analysis could not complete. Review the medications manually or rerun with an available model provider.",
            [], "unavailable")
    for i, item in enumerate(interactions.get("interactions", [])):
        drugs = item.get("drugs", [])
        evidence = [e for name in drugs for e in evidence_for(name, sources)]
        add(f"medication-{i}", "medication", " + ".join(drugs),
            item.get("clinical_significance") or item.get("mechanism") or "Review medication interaction",
            evidence)
    for result in snapshot.get("calculator_results", []):
        if result.get("result") and not result["result"].get("error"):
            text = json.dumps(result, ensure_ascii=False, indent=2)
            source_id = f"calculator/{result['tool']}/{hash_text(text)[:16]}"
            sources[source_id] = {"label": "Calculator inputs and result", "text": text, "kind": "computed"}
            add(f"calculator-{result['tool']}", "calculator", result["result"].get("tool", result["tool"]),
                "\n".join(f"{key.replace('_', ' ').capitalize()}: {value}" for key, value in result["result"].items() if key != "tool"),
                [{"source_id": source_id, "start": 0, "end": len(text), "quote": text,
                  "assertion": "computed"}], "computed")
    summary = snapshot.get("final_summary") or {}
    if summary.get("patient_facing_summary"):
        # Context, not independent verification that each summary claim is entailed.
        evidence = [e for finding in findings for e in finding["evidence"]][:12]
        add("summary", "summary", "Patient summary", summary["patient_facing_summary"], evidence)
    for i, flag in enumerate(patient.get("summary", {}).get("clinical_flags", [])):
        text = flag.get("text", "") if isinstance(flag, dict) else str(flag)
        if text:
            source_id = f"record/clinical_flags/{i}"
            source = sources[source_id]["text"]
            add(f"concern-{i}", "concern", "Recorded concern", text,
                [{"source_id": source_id, "start": 0, "end": len(source), "quote": source,
                  "assertion": "documented"}], "documented")
    return findings


def create_draft(patient: dict, snapshot: dict) -> dict:
    from app.review.store import create_run

    sources = record_sources(patient)
    findings = build_findings(patient, snapshot, sources)
    clarifications = [
        {"id": str(uuid.uuid4()), "kind": "calculator", "tool": result["tool"],
         "question": f"Complete the missing inputs for {result['tool'].replace('_', ' ')} or skip this calculator.",
         "fields": result["missing_fields"], "inputs": result.get("inputs", {}), "status": "pending"}
        for result in snapshot.get("calculator_results", []) if result.get("status") == "needs_input"
    ]
    return create_run(patient, snapshot, sources, findings, clarifications)


async def run_reviewable_analysis(patient_data: dict):
    from app.review.extraction import with_reviewed_fields

    patient_data = await asyncio.to_thread(with_reviewed_fields, patient_data)
    snapshot = {}
    async for event in run_graph_streaming(patient_data):
        snapshot.update({key: value for key, value in event.items() if key not in ("node", "audit_entry")})
        yield event
    run = await asyncio.to_thread(create_draft, patient_data, snapshot)
    yield {"node": "__review__", "review_run": run, "audit_entry": "Draft saved for human review."}
