from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from langgraph.graph import END, StateGraph

from app.agent.rag.state import RAGState
from app.agent.rag.nodes import (
    _patient_cache_id,
    context_assembler_node,
    eval_node,
    follow_up_node,
    generator_node,
    patient_retriever_node,
    query_router_node,
    research_fetcher_node,
    sufficiency_judge_node,
    web_search_node,
)
from app.agent.sqlite_cache import get_answer, set_answer

log = logging.getLogger(__name__)


def _build_rag_graph() -> StateGraph:
    wf = StateGraph(RAGState)
    wf.add_node("query_router",      query_router_node)
    wf.add_node("patient_retriever", patient_retriever_node)
    wf.add_node("research_fetcher",  research_fetcher_node)
    wf.add_node("web_search",        web_search_node)
    wf.add_node("context_assembler", context_assembler_node)
    wf.add_node("sufficiency_judge", sufficiency_judge_node)
    wf.add_node("generator",         generator_node)
    wf.add_node("eval_agent",        eval_node)
    wf.add_node("follow_up_agent",   follow_up_node)

    wf.set_entry_point("query_router")
    wf.add_edge("query_router",      "patient_retriever")
    wf.add_edge("patient_retriever", "research_fetcher")
    wf.add_edge("research_fetcher",  "web_search")
    wf.add_edge("web_search",        "context_assembler")
    wf.add_edge("context_assembler", "sufficiency_judge")
    wf.add_edge("sufficiency_judge", "generator")
    wf.add_edge("generator",         "eval_agent")
    wf.add_edge("eval_agent",        "follow_up_agent")
    wf.add_edge("follow_up_agent",   END)
    return wf.compile()


rag_graph = _build_rag_graph()


async def run_rag_streaming(
    patient_id: str,
    patient_data: dict,
    question: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream the RAG pipeline. Emits thinking_log entries per node.
    Fires 'done' immediately after generator so the user reads while
    eval + follow-ups run. Caches final answers for instant repeated queries.
    """
    cache_patient_id = _patient_cache_id(patient_id, patient_data)
    cached_answer    = await asyncio.to_thread(get_answer, cache_patient_id, question)
    if cached_answer:
        log.info("[rag] cache hit for patient %s", patient_id)
        await asyncio.sleep(2)
        yield {"type": "done", "node": "cache", "message": "Response ready", "data": cached_answer}
        return

    initial: RAGState = {
        "patient_id":         patient_id,
        "patient_data":       patient_data,
        "question":           question,
        "route":              "both",
        "reformulated_query": question,
        "patient_chunks":     [],
        "research_chunks":    [],
        "web_chunks":         [],
        "all_chunks":         [],
        "context_sufficient": True,
        "is_refusal":         False,
        "raw_answer":         "",
        "eval_scores":        {},
        "final_response":     "",
        "citations":          [],
        "error":              None,
        "thinking_log":       [],
        "follow_ups":         [],
    }

    yielded_count  = 0
    answer_yielded = False

    async for event in rag_graph.astream(initial):
        for node_name, node_state in event.items():
            tlog       = node_state.get("thinking_log", [])
            new_entries = tlog[yielded_count:]
            for entry in new_entries:
                yield entry
            yielded_count = len(tlog)

            if node_name == "generator" and not answer_yielded:
                answer_yielded = True
                yield {
                    "type":    "done",
                    "node":    "generator",
                    "message": "Response ready",
                    "data": {
                        "final_response": node_state.get("raw_answer", ""),
                        "citations":      node_state.get("citations", []),
                        "eval_scores":    {},
                        "route":          node_state.get("route", ""),
                        "is_refusal":     node_state.get("is_refusal", False),
                        "follow_ups":     [],
                    },
                }

            elif node_name == "eval_agent":
                eval_scores = node_state.get("eval_scores", {})
                final       = node_state.get("final_response", node_state.get("raw_answer", ""))
                yield {
                    "type":    "patch_eval",
                    "node":    "eval_agent",
                    "message": "Eval complete",
                    "data":    {"eval_scores": eval_scores, "final_response": final},
                }

            elif node_name == "follow_up_agent":
                follow_ups  = node_state.get("follow_ups", [])
                result_data = {
                    "final_response": node_state.get("final_response", ""),
                    "citations":      node_state.get("citations", []),
                    "eval_scores":    node_state.get("eval_scores", {}),
                    "route":          node_state.get("route", ""),
                    "is_refusal":     node_state.get("is_refusal", False),
                    "follow_ups":     follow_ups,
                }
                if not node_state.get("is_refusal", True):
                    await asyncio.to_thread(set_answer, cache_patient_id, question, result_data)

                yield {
                    "type":    "patch_followups",
                    "node":    "follow_up_agent",
                    "message": "Follow-ups ready",
                    "data":    {"follow_ups": follow_ups},
                }
