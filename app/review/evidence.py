"""Conservative exact-text provenance; assertion rules are a baseline, not clinical NLP."""
import json
import re


def assertion_at(text: str, start: int, end: int) -> str:
    # Restrict scope to the current sentence/clause. A later affirmative clause
    # must not inherit a preceding denial ("No diabetes, but hypertension").
    prefix = re.split(r"[.;\n]|\b(?:but|however)\b", text[:start], flags=re.I)[-1]
    suffix = re.split(r"[.;\n]|\b(?:but|however)\b", text[end:], flags=re.I)[0]
    if re.search(r"\b(no|not|denies|without|negative for|ruled out)\b", prefix, re.I) or re.search(
        r"^\s+(?:is |was )?(?:ruled out|not present|excluded)\b", suffix, re.I,
    ):
        return "negated"
    if re.search(r"\b(history of|previous|prior|resolved)\b", prefix, re.I) or re.search(
        r"\b(?:now resolved|previously resolved)\b", suffix, re.I,
    ):
        return "historical"
    if re.search(r"\b(suspected|possible|probable|consider|rule out)\b", prefix, re.I):
        return "suspected"
    return "documented"


def record_sources(patient: dict) -> dict[str, dict]:
    sources = {
        name: {"label": name.replace("_", " "), "text": text, "kind": "document"}
        for name, text in patient.get("source_documents", {}).items() if isinstance(text, str) and text
    }
    summary = patient.get("summary", {})
    for section in ("diagnoses", "medications", "lab_results", "clinical_flags", "reviewed_fields"):
        for i, item in enumerate(summary.get(section, [])):
            source_id = f"record/{section}/{i}"
            sources[source_id] = {
                "label": f"Record · {section.replace('_', ' ')} · {i + 1}",
                "text": json.dumps(item, ensure_ascii=False, indent=2), "kind": "structured",
            }
    if summary.get("summary_narrative"):
        sources["record/narrative"] = {"label": "Record narrative", "text": summary["summary_narrative"],
                                       "kind": "document"}
    return sources


def evidence_for(term: str, sources: dict[str, dict]) -> list[dict]:
    if not term.strip():
        return []
    spans = []
    for source_id, source in sorted(sources.items(), key=lambda item: item[1]["kind"] != "structured"):
        for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", source["text"], re.I):
            assertion = "reviewer_supplied" if source["kind"] == "reviewer_supplied" else assertion_at(
                source["text"], match.start(), match.end(),
            )
            if source["kind"] == "structured":
                try:
                    record = json.loads(source["text"])
                    status = str(record.get("status", "")).lower() if isinstance(record, dict) else ""
                    if any(t in status for t in ("ruled out", "negated")):
                        assertion = "negated"
                    elif any(t in status for t in ("historical", "resolved")):
                        assertion = "historical"
                    elif any(t in status for t in ("suspected", "investigation", "possible")):
                        assertion = "suspected"
                except (ValueError, TypeError):
                    continue
            spans.append({"source_id": source_id, "start": match.start(), "end": match.end(),
                          "quote": match.group(), "assertion": assertion})
    return spans[:12]


def finding_assertion(name: str, patient: dict, evidence: list[dict]) -> str:
    assertions = {e["assertion"] for e in evidence}
    if "documented" in assertions and assertions & {"negated", "historical"}:
        return "conflicting"
    for i, diagnosis in enumerate(patient.get("summary", {}).get("diagnoses", [])):
        if isinstance(diagnosis, dict) and diagnosis.get("name", "").casefold() == name.casefold():
            record_evidence = [e for e in evidence if e["source_id"] == f"record/diagnoses/{i}"]
            if record_evidence:
                return record_evidence[0]["assertion"]
    assertions = {e["assertion"] for e in evidence}
    if assertions == {"negated"}:
        return "negated"
    if assertions == {"historical"}:
        return "historical"
    # A literal mention does not establish a diagnosis: retain inference label.
    return "ai_suggested"
