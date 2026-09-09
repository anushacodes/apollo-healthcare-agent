from __future__ import annotations

import operator
from typing import Annotated

from pydantic import BaseModel, Field


class RAGState(BaseModel):
    patient_id:          str = ""
    patient_data:        dict = Field(default_factory=dict)
    question:            str = ""
    route:               str = "both"
    reformulated_query:  str = ""
    patient_chunks:      list[dict] = Field(default_factory=list)
    research_chunks:     list[dict] = Field(default_factory=list)
    web_chunks:          list[dict] = Field(default_factory=list)
    all_chunks:          list[dict] = Field(default_factory=list)
    context_sufficient:  bool = True
    is_refusal:          bool = False
    raw_answer:          str = ""
    eval_scores:         dict = Field(default_factory=dict)
    final_response:      str = ""
    citations:           list[dict] = Field(default_factory=list)
    error:               str | None = None
    thinking_log:        Annotated[list[dict], operator.add] = Field(default_factory=list)
    follow_ups:          list[str] = Field(default_factory=list)
    prompt_versions:     dict[str, str] = Field(default_factory=dict)
