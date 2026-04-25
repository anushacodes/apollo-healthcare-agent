from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from app.models import ClinicalSummary


class AgentState(TypedDict):
    patient_id:          str
    patient_data:        dict
    anonymized_notes:    str
    extracted_params:    dict
    calculator_results:  list[dict]
    diagnoses:           dict
    interactions:        dict
    kg_matches:          list[dict]
    final_summary:       ClinicalSummary | None
    audit_log:           Annotated[list[str], operator.add]
    error:               str | None
