from __future__ import annotations

import operator
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import ClinicalSummary


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    patient_id:          str = ""
    patient_data:        dict = Field(default_factory=dict)
    anonymized_notes:    str = ""
    extracted_params:    dict = Field(default_factory=dict)
    calculator_results:  list[dict] = Field(default_factory=list)
    diagnoses:           dict = Field(default_factory=dict)
    interactions:        dict = Field(default_factory=dict)
    kg_matches:          list[dict] = Field(default_factory=list)
    final_summary:       ClinicalSummary | None = None
    audit_log:           Annotated[list[str], operator.add] = Field(default_factory=list)
    error:               str | None = None
