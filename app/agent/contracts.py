"""
Pydantic contracts for LLM-produced structured output. Used with the
instructor-wrapped Groq client (`app.llm_client.get_structured_groq_client`)
so agent outputs are validated at the LLM boundary instead of accessed as
untyped dicts via `.get(...)` with silent fallbacks.
"""


from typing import Any
from pydantic import BaseModel, Field, model_validator


class CalculatorCall(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


class OrchestratorPlan(BaseModel):
    calculator_calls: list[CalculatorCall] = Field(default_factory=list)
    symptoms_for_kg:  list[str] = Field(default_factory=list)
    routing_notes:    str = ""


class ProposedDiagnosis(BaseModel):
    name: str = Field(default="unknown")
    icd_code: str | None = None
    confidence: str = "moderate"
    supporting_evidence: list[str] = Field(default_factory=list)
    reasoning: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any):
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "diagnosis" in d and not d.get("name"):
            d["name"] = d["diagnosis"]
        if "condition" in d and not d.get("name"):
            d["name"] = d["condition"]
        if "icd10_code" in d and not d.get("icd_code"):
            d["icd_code"] = d["icd10_code"]
        if "icd_10" in d and not d.get("icd_code"):
            d["icd_code"] = d["icd_10"]
        ev = d.get("supporting_evidence")
        if isinstance(ev, str):
            d["supporting_evidence"] = [s.strip() for s in ev.split(",") if s.strip()]
        elif not isinstance(ev, list):
            d["supporting_evidence"] = [str(ev)] if ev else []
        return d


class DiagnosisResult(BaseModel):
    proposed_diagnoses:         list[ProposedDiagnosis] = Field(default_factory=list)
    primary_diagnosis:          str = "unknown"
    differential_notes:         str = ""
    recommended_investigations: list[str] = Field(default_factory=list)


class DrugInteraction(BaseModel):
    drugs: list[str] = Field(default_factory=list)
    severity: str = "minor"
    mechanism: str = ""
    clinical_significance: str = ""


class Contraindication(BaseModel):
    drug: str
    condition: str
    risk: str = ""


class DrugInteractionResult(BaseModel):
    interactions:      list[DrugInteraction] = Field(default_factory=list)
    contraindications: list[Contraindication] = Field(default_factory=list)
    overall_risk:       str = "unknown"
    summary:            str = ""


class RouterDecision(BaseModel):
    route: str = "both"
    reformulated_query: str = ""
    reasoning: str = ""


class FollowUpQuestions(BaseModel):
    follow_up_questions: list[str] = Field(default_factory=list)


class EvalScores(BaseModel):
    faithfulness:           float = 1.0
    context_relevance:      float = 1.0
    answer_completeness:    float = 1.0
    hallucination_detected: bool = False
    total_claims:           int = 0
    supported_claims:       int = 0
    unsupported_claims:     list[str] = Field(default_factory=list)
    evaluation_notes:       str = ""
    blocked:                bool = False
    block_reason:           str | None = None
