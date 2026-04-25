from __future__ import annotations

from typing import TypedDict


class RAGState(TypedDict):
    patient_id:          str
    patient_data:        dict
    question:            str
    route:               str
    reformulated_query:  str
    patient_chunks:      list[dict]
    research_chunks:     list[dict]
    web_chunks:          list[dict]
    all_chunks:          list[dict]
    context_sufficient:  bool
    is_refusal:          bool
    raw_answer:          str
    eval_scores:         dict
    final_response:      str
    citations:           list[dict]
    error:               str | None
    thinking_log:        list[dict]
    follow_ups:          list[str]
