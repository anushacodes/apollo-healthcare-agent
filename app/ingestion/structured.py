"""Conservative English extraction from explicit labels, lists and Markdown lab tables.

No model or medical inference is used. Every proposal retains a verbatim source span.
Unrecognized prose stays in the document for manual review.
"""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.sqlite_cache import hash_payload

SCHEMAS = {
    "patient_name": {"value": "Patient name"},
    "date_of_birth": {"value": "Date of birth"},
    "record_number": {"value": "Record number"},
    "document_date": {"value": "Document date"},
    "diagnosis": {"name": "Diagnosis", "status": "Status", "date": "Recorded date"},
    "medication": {"name": "Medication", "dose": "Dose", "frequency": "Frequency",
                   "status": "Status", "date": "Recorded date", "notes": "Notes"},
    "lab": {"test_name": "Test", "value": "Result", "unit": "Unit", "reference_range": "Reference range",
            "flag": "Recorded flag", "date": "Sample or report date"},
    "allergy": {"substance": "Substance or statement", "reaction": "Reaction", "status": "Status"},
    "follow_up": {"text": "Recorded action", "date": "Recorded date"},
}
CHOICES = {
    "diagnosis": {"status": ["documented", "suspected", "historical", "negated", "ruled_out"]},
    "medication": {"status": ["recorded", "held", "stopped", "historical"]},
    "lab": {"flag": ["not_recorded", "normal", "high", "low", "critical_high", "critical_low"]},
    "allergy": {"status": ["documented", "negated"]},
}
REQUIRED = {
    "diagnosis": {"name", "status"}, "medication": {"name", "status"},
    "lab": {"test_name", "value", "flag"}, "allergy": {"substance", "status"}, "follow_up": {"text"},
}


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str
    data: dict[str, str]

    @model_validator(mode="after")
    def validate_field(self):
        schema = SCHEMAS.get(self.kind)
        if schema is None or set(self.data) - schema.keys():
            raise ValueError("Unknown extraction field or property")
        self.data = {key: value.strip() for key, value in self.data.items()}
        if any(not self.data.get(key) for key in REQUIRED.get(self.kind, {"value"})):
            raise ValueError("Complete every required field")
        if any(len(value) > 2000 for value in self.data.values()):
            raise ValueError("Field values must be at most 2000 characters")
        for key, choices in CHOICES.get(self.kind, {}).items():
            if self.data.get(key) not in choices:
                raise ValueError(f"Choose a valid {key}")
        return self


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100000)
    source_name: str = Field(min_length=1, max_length=200)


def field_schema(kind):
    return [{"name": key, "label": label, "required": key in REQUIRED.get(kind, {"value"}),
             "choices": CHOICES.get(kind, {}).get(key, [])} for key, label in SCHEMAS[kind].items()]


def describe(kind, data):
    return "\n".join(f"{SCHEMAS[kind][key]}: {value.replace('_', ' ') if key in ('status', 'flag') else value}"
                     for key, value in data.items() if value)


def _date(raw):
    raw = raw.strip().split("    ")[0].strip()
    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            pass
    # Numeric day/month dates are ambiguous unless one component exceeds twelve.
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if match:
        a, b, _ = map(int, match.groups())
        pattern = "%d/%m/%Y" if a > 12 else "%m/%d/%Y" if b > 12 else None
        if pattern:
            try:
                return datetime.strptime(raw, pattern).date().isoformat()
            except ValueError:
                pass
    return ""


def _diagnosis(value):
    patterns = [(r"^(?:no evidence of|negative for|no)\s+", "negated"),
                (r"^(.+?)\s+(?:has been )?ruled out\.?$", "ruled_out"),
                (r"^(?:history of|past history of|previous)\s+", "historical"),
                (r"^(?:suspected|possible|rule out|query)\s+", "suspected")]
    for pattern, status in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return {"name": (match.group(1) if match.lastindex else value[match.end():]).strip(" ."),
                    "status": status}
    return {"name": value.strip(" ."), "status": "documented"}


def _medication(value, historical=False):
    # Require an explicit dose. Do not infer a drug from an arbitrary prose sentence.
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9 /+'’()\-]*?)\s+(\d+(?:\.\d+)?\s*(?:mcg|µg|mg|g|mL|ml|units?))\b(.*)", value)
    if not match:
        return None
    name, dose, tail = match.groups()
    status = "historical" if historical else "recorded"
    if re.search(r"\b(?:held|withheld)\b", tail, re.I):
        status = "held"
    if re.search(r"\b(?:stopped|discontinued)\b", tail, re.I):
        status = "stopped"
    frequency = re.search(r"\b(?:once daily|twice daily|three times daily|four times daily|daily|weekly|nightly|as needed|every \d+ hours?|BD|BID|TID|QID|OD|PRN)\b", tail, re.I)
    return {"name": name.strip(), "dose": dose, "frequency": frequency.group() if frequency else "",
            "status": status, "notes": tail.strip()}


def extract_fields(text: str) -> dict:
    proposals, warnings, seen = [], [], set()
    lines = list(re.finditer(r"[^\n]+", text))
    document_date = sample_date = ""

    def add(kind, data, line):
        field = ExtractedField(kind=kind, data=data)
        key = hash_payload(field.model_dump())
        if key not in seen:
            seen.add(key)
            proposals.append({**field.model_dump(), "start": line.start(), "end": line.end(),
                              "quote": line.group()})

    # Only explicitly labeled dates are attached to results; no dates inferred from prose.
    date_pattern = r"\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]+ \d{4}|[A-Za-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4}"
    for line in lines:
        for label, raw in re.findall(rf"\b(Report Date|Document Date|Date|Sample collected|Collection Date):\s*({date_pattern})", line.group(), re.I):
            parsed = _date(raw)
            if not parsed:
                warnings.append(f"Ambiguous or invalid {label.lower()}: {raw}. Confirm the date manually.")
            elif label.lower() in ("sample collected", "collection date"):
                sample_date = parsed
            elif not document_date:
                document_date = parsed
                add("document_date", {"value": parsed}, line)

    section, historical_meds = "", False
    flag_map = {"H": "high", "L": "low", "HH": "critical_high", "LL": "critical_low", "N": "normal"}
    for line in lines:
        raw = line.group()
        value = raw.strip().replace("**", "")
        heading = re.sub(r"^\[SECTION:\s*|\]$|^#+\s*|:$", "", value, flags=re.I).strip().lower()
        if heading in ("diagnoses", "diagnosis", "active diagnoses", "past medical history", "current medications",
                       "medications", "discharge medications", "medication history", "allergies", "plan", "follow-up", "follow up"):
            section = heading
            historical_meds = heading in ("discharge medications", "medication history")
            continue
        if value.startswith("[SECTION:") or value.startswith("---") or (value.endswith(":") and not re.match(r"^(?:diagnosis|medication|allergy|follow.up):", value, re.I)):
            section = ""
        for label, kind in ((r"Patient(?: name)?|Name", "patient_name"), (r"Date of Birth|DOB", "date_of_birth"),
                            (r"MRN|Medical record number", "record_number")):
            match = re.search(rf"(?:^|\s{{2,}})({label}):\s*(.+?)(?=\s{{2,}}[A-Za-z]|$)", raw, re.I)
            if match:
                result = match.group(2).strip()
                if kind == "date_of_birth":
                    result = _date(result)
                    if not result:
                        warnings.append("Date of birth needs manual confirmation; no date was inferred.")
                if result:
                    add(kind, {"value": result}, line)
        if value.startswith("|"):
            cells = [cell.strip().strip("*") for cell in value.strip("|").split("|")]
            if len(cells) >= 5 and cells[0].lower() not in ("test", "parameter", "analyte", "indicator") and not re.fullmatch(r"[- :]+", cells[0]) and cells[1]:
                add("lab", {"test_name": cells[0], "value": cells[1], "unit": "" if cells[2] == "—" else cells[2],
                            "reference_range": cells[3], "flag": flag_map.get(cells[4].upper(), "not_recorded"),
                            "date": sample_date or document_date}, line)
            continue
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)", value)
        item = bullet.group(1) if bullet else value
        diagnosis = re.match(r"^(?:Diagnosis|Diagnoses):\s*(.+)", item, re.I)
        if diagnosis or (bullet and section in ("diagnoses", "diagnosis", "active diagnoses", "past medical history")):
            for part in (diagnosis.group(1) if diagnosis else item).split(";"):
                if part.strip():
                    data = _diagnosis(part.strip())
                    if section == "past medical history" and data["status"] == "documented":
                        data["status"] = "historical"
                    add("diagnosis", {**data, "date": document_date}, line)
        medication = re.match(r"^Medication:\s*(.+)", item, re.I)
        if medication or (bullet and section in ("medications", "current medications", "discharge medications", "medication history")):
            data = _medication(medication.group(1) if medication else item, historical_meds)
            if data:
                add("medication", {**data, "date": document_date}, line)
            else:
                warnings.append("A medication line could not be parsed safely; inspect the original document.")
        allergy = re.match(r"^Allerg(?:y|ies):\s*(.+)", item, re.I)
        if allergy or (bullet and section == "allergies"):
            statement = allergy.group(1) if allergy else item
            negated = bool(re.match(r"(?:no known|none\b|NKDA\b)", statement, re.I))
            parts = re.split(r"\s+[—–-]\s+|:\s*", statement, maxsplit=1)
            add("allergy", {"substance": parts[0], "reaction": parts[1] if len(parts) > 1 else "",
                            "status": "negated" if negated else "documented"}, line)
        follow_up = re.match(r"^(?:Follow[- ]up|Next outpatient review|Plan):\s*(.+)", item, re.I)
        if follow_up or (bullet and section in ("plan", "follow-up", "follow up")):
            add("follow_up", {"text": follow_up.group(1) if follow_up else item, "date": document_date}, line)
    return {"extractor": "english-rules-v1", "fields": proposals,
            "warnings": list(dict.fromkeys(warnings)),
            "scope": "Explicit English labels, medication lists and five-column lab tables. Unrecognized prose is not extracted."}
