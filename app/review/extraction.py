"""Extraction proposals use the same sessions, version checks and audit trail as analysis."""
import copy
import json
import re

from fastapi import HTTPException
from pydantic import ValidationError

from app.agent.sqlite_cache import _get_conn, hash_payload, hash_text
from app.ingestion.structured import ExtractedField, describe, extract_fields, field_schema
from app.review import store


def create_extraction(patient_id, source_name, text, patient_name=None):
    from app.agent.seed_patient import get_case, list_cases

    source_name = source_name.strip()
    if not source_name:
        raise HTTPException(422, "Enter a document name")
    if patient_name is None:
        for item in list_cases():
            case = get_case(item["key"])
            if case["patient_id"] == patient_id:
                patient_name = case.get("patient", {}).get("name")
                break
    if not text.strip():
        raise HTTPException(422, "The document has no text to extract")
    if len(text) > 100000:
        raise HTTPException(413, "Structured extraction supports up to 100,000 characters per document")
    result = extract_fields(text)
    source_id = f"document/{hash_text(text)}"
    sources = {source_id: {"label": source_name, "text": text, "kind": "document"}}
    findings = []
    for field in result["fields"]:
        kind, data = field["kind"], field["data"]
        assertion = data.get("status", "documented")
        if assertion in ("held", "stopped", "recorded"):
            assertion = "documented"
        if kind == "patient_name" and patient_name:
            def normalize(value):
                return re.sub(r"\b(?:mr|mrs|ms|dr)\b\.?|[^a-z]+", "", value.casefold())
            if normalize(data["value"]) != normalize(patient_name):
                assertion = "conflicting"
        findings.append({"id": f"extracted-{hash_payload([kind, data])[:24]}", "kind": "extraction",
                         "title": kind.replace("_", " ").capitalize(), "original_text": describe(kind, data),
                         "assertion": assertion, "status": "pending", "decision": None,
                         "extracted": {"kind": kind, "data": data}, "field_schema": field_schema(kind),
                         "evidence": [{"source_id": source_id, "start": field["start"], "end": field["end"],
                                       "quote": field["quote"], "assertion": assertion}]})
    # Conflicting values within the same document need an explicit correction or rejection.
    groups = {}
    for finding in findings:
        field = finding["extracted"]
        data = field["data"]
        key = (field["kind"], data.get("name", data.get("test_name", "")).casefold(), data.get("date", ""))
        if field["kind"] in ("diagnosis", "medication", "lab", "patient_name", "date_of_birth", "record_number"):
            groups.setdefault(key, []).append(finding)
    for group in groups.values():
        if len(group) > 1:
            for finding in group:
                finding["assertion"] = "conflicting"
    if any(f["extracted"]["kind"] == "patient_name" and f["assertion"] == "conflicting" for f in findings):
        result["warnings"].append("The document patient name differs from this record. Verify the patient assignment before correcting or rejecting its fields.")
        for finding in findings:
            finding["assertion"] = "conflicting"
    metadata = {key: value for key, value in result.items() if key != "fields"}
    metadata["source_name"] = source_name
    return store.create_run({"patient_id": patient_id}, metadata, sources, findings, [], kind="extraction")


def corrected_field(finding, data):
    try:
        return ExtractedField(kind=finding["extracted"]["kind"], data=data).model_dump()
    except (ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(422, "Complete the structured fields using the listed properties and status choices") from exc


def commit_fields(conn, run, reviewer):
    """Called in the finalization transaction; partial reviews never update the record."""
    count = 0
    for finding in run["findings"]:
        if finding["status"] not in ("accepted", "edited"):
            continue
        field = finding["decision"].get("edited_data") or finding["extracted"]
        evidence = finding["evidence"][0]
        source = run["sources"][evidence["source_id"]]
        record = {**field, "source_name": source["label"], "source_hash": hash_text(source["text"]),
                  "quote": evidence["quote"], "start": evidence["start"], "end": evidence["end"],
                  "run_id": run["id"], "finding_id": finding["id"], "reviewer": reviewer,
                  "decision": finding["decision"], "recorded_at": store.now()}
        key = hash_payload([run["patient_id"], record["source_hash"], field])
        cursor = conn.execute("INSERT OR IGNORE INTO reviewed_document_fields VALUES (?, ?, ?)",
                              (key, run["patient_id"], json.dumps(dict(record, id=key))))
        count += cursor.rowcount
    # Only invalidate inside the same transaction as committing reviewed fields.
    prefix = f"{run['patient_id']}:"
    conn.execute("DELETE FROM rag_answer_cache WHERE patient_id = ? OR substr(patient_id, 1, ?) = ?",
                 (run["patient_id"], len(prefix), prefix))
    return count


def reviewed_fields(patient_id):
    rows = _get_conn().execute("SELECT state FROM reviewed_document_fields WHERE patient_id = ? ORDER BY rowid",
                              (patient_id,)).fetchall()
    return [json.loads(row["state"]) for row in rows]


def with_reviewed_fields(patient):
    result = copy.deepcopy(patient)
    result.setdefault("summary", {}).pop("reviewed_fields", None)
    fields = reviewed_fields(result.get("patient_id", "unknown"))
    if fields:
        result.setdefault("summary", {})["reviewed_fields"] = fields
    return result


def reviewed_context(fields):
    if not fields:
        return ""
    lines = ["REVIEWED DOCUMENT FIELDS (retain recorded dates and statuses; these do not replace current medication lists):"]
    for field in fields:
        lines.append(f"Source: {field['source_name']} | Review: {field['run_id']} | {describe(field['kind'], field['data'])}")
    return "\n".join(lines)


def reviewed_chunks(fields, patient_id, question):
    """Keep relevant approved values visible within the RAG prompt's per-chunk limit."""
    words = set(re.findall(r"[a-z0-9]+", question.casefold())) - {
        "the", "a", "an", "is", "are", "was", "what", "which", "patient", "this", "for", "and", "of", "to",
    }
    ranked = []
    for field in fields:
        content = describe(field["kind"], field["data"])
        tokens = set(re.findall(r"[a-z0-9]+", f"{field['kind']} {content}".casefold()))
        relevance = len(words & tokens)
        if relevance:
            ranked.append((relevance, field, content))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{"chunk_id": f"reviewed-{field['id']}", "patient_id": patient_id,
             "source_doc": f"{field['source_name']} (reviewed)", "doc_type": "reviewed_document_field",
             "text": "REVIEWED DOCUMENT FIELD — retain its recorded date and status; this does not replace current medication lists.\n"
                     f"{content}\nReviewer: {field['reviewer']['name']} | Review: {field['run_id']}",
             "score": 998.0} for _, field, content in ranked[:3]]
