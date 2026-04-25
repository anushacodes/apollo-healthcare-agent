from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

# Enums
class LabFlag(str, Enum):
    high = "high"
    low = "low"
    normal = "normal"
    critical_high = "critical_high"
    critical_low = "critical_low"

class DiagnosisStatus(str, Enum):
    active = "active"
    resolving = "resolving"
    resolved = "resolved"
    suspected = "suspected"
    ruled_out = "ruled_out"
    improving = "improving"

class TimelineCategory(str, Enum):
    visit = "visit"
    lab = "lab"
    procedure = "procedure"
    diagnosis = "diagnosis"
    medication = "medication"
    imaging = "imaging"
    other = "other"

class DocumentType(str, Enum):
    handwritten_note = "handwritten_note"
    clinical_letter = "clinical_letter"
    lab_report = "lab_report"
    radiology_report = "radiology_report"
    audio_transcript = "audio_transcript"
    discharge_summary = "discharge_summary"
    other = "other"

# Clinical sub-models
class Diagnosis(BaseModel):
    name: str
    icd_code: Optional[str] = None
    date_first_noted: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None

class Medication(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    indication: Optional[str] = None

class LabResult(BaseModel):
    test_name: str
    value: str
    unit: Optional[str] = None
    date: Optional[str] = None
    flag: LabFlag = LabFlag.normal
    reference_range: Optional[str] = None

class ClinicalFlag(BaseModel):
    text: str
    type: str = "warn"

class TimelineEvent(BaseModel):
    date: str
    event: str
    category: TimelineCategory = TimelineCategory.visit

class SourceDocument(BaseModel):
    name: str
    type: DocumentType = DocumentType.other
    label: str
    icon: str = "📄"
    description: Optional[str] = None

# Structured Summarization Agent output
class ClinicalSummary(BaseModel):
    chief_complaint: str = Field(description="Primary reason for the current clinical encounter, in 1-2 sentences.")
    history_of_present_illness: str = Field(description="Concise HPI: onset, duration, character, associated symptoms, relevant past history, and recent trajectory.")
    clinical_assessment: str = Field(description="Clinical interpretation: active problems, disease severity, treatment response, and risk factors.")
    current_medications: list[str] = Field(default_factory=list, description="Each entry formatted as 'Drug name — dose, frequency'.")
    patient_facing_summary: Optional[str] = Field(default=None, description="Plain-English summary written directly for the patient.")
    key_concerns: list[str] = Field(default_factory=list, description="Bulleted list of the most urgent clinical concerns.")
    follow_up_actions: list[str] = Field(default_factory=list, description="Concrete next steps: tests, referrals, appointments.")
    generated_at: Optional[datetime] = None
    model_used: Optional[str] = None
    patient_id: Optional[str] = None

# Full patient record
class PatientSummary(BaseModel):
    patient_id: str
    generated_at: Optional[datetime] = None
    summary_narrative: str = ""
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    clinical_flags: list[ClinicalFlag] = Field(default_factory=list)
    clinical_summary: Optional[ClinicalSummary] = None

    model_config = ConfigDict(from_attributes=True)

# Patient top-level model
class Patient(BaseModel):
    patient_id: str
    name: str
    dob: Optional[str] = None
    mrn: Optional[str] = None
    age: Optional[int] = None

# API request / response envelopes
class SummarizeRequest(BaseModel):
    patient_id: str
    document_ids: list[str] = Field(default_factory=list)
    force_regenerate: bool = False

class SummarizeResponse(BaseModel):
    patient_id: str
    summary: ClinicalSummary
    cached: bool = False
    elapsed_ms: Optional[float] = None

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
