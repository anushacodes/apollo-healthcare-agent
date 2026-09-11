import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.rag.nodes import (
    _patient_cache_id,
    context_assembler_node,
    eval_node,
    follow_up_node,
    generator_node,
    patient_retriever_node,
    query_router_node,
    research_fetcher_node,
    retrieval_gate_node,
    sufficiency_judge_node,
    web_search_node,
)
from app.agent.rag.state import RAGState
from app.agent.sqlite_cache import get_answer, set_answer

log = logging.getLogger(__name__)


def _route_from_query_router(state: RAGState) -> list[str]:
    """Fan out to whichever retrieval branch(es) the router's route decision calls for."""
    if state.route == "patient_docs":
        return ["patient_retriever"]
    if state.route == "research":
        return ["research_fetcher"]
    return ["patient_retriever", "research_fetcher"]


def _route_after_retrieval(state: RAGState) -> str:
    """Fall back to web search only when patient docs + corpus results came back sparse."""
    if state.route == "patient_docs":
        return "context_assembler"
    combined = len(state.patient_chunks) + len(state.research_chunks)
    return "context_assembler" if combined >= 3 else "web_search"


def _route_after_generation(state: RAGState) -> str:
    """Refusals skip straight to the end — nothing to evaluate or follow up on."""
    return END if state.is_refusal else "eval_agent"


def _build_rag_graph() -> StateGraph:
    wf = StateGraph(RAGState)
    wf.add_node("query_router",      query_router_node)
    wf.add_node("patient_retriever", patient_retriever_node)
    wf.add_node("research_fetcher",  research_fetcher_node)
    wf.add_node("retrieval_gate",    retrieval_gate_node)
    wf.add_node("web_search",        web_search_node)
    wf.add_node("context_assembler", context_assembler_node)
    wf.add_node("sufficiency_judge", sufficiency_judge_node)
    wf.add_node("generator",         generator_node)
    wf.add_node("eval_agent",        eval_node)
    wf.add_node("follow_up_agent",   follow_up_node)

    wf.set_entry_point("query_router")
    wf.add_conditional_edges(
        "query_router", _route_from_query_router, ["patient_retriever", "research_fetcher"]
    )
    wf.add_edge("patient_retriever", "retrieval_gate")
    wf.add_edge("research_fetcher",  "retrieval_gate")
    wf.add_conditional_edges(
        "retrieval_gate", _route_after_retrieval, ["web_search", "context_assembler"]
    )
    wf.add_edge("web_search",        "context_assembler")
    wf.add_edge("context_assembler", "sufficiency_judge")
    wf.add_edge("sufficiency_judge", "generator")
    wf.add_conditional_edges("generator", _route_after_generation, ["eval_agent", END])
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

    initial = RAGState(
        patient_id=patient_id,
        patient_data=patient_data,
        question=question,
        reformulated_query=question,
    )

    # Node returns are partial updates (only the fields that node changed), not
    # the full state — accumulate them ourselves so downstream events here can
    # still read fields set by earlier nodes (e.g. "route" from query_router).
    accumulated: dict[str, Any] = initial.model_dump()
    answer_yielded = False

    async for event in rag_graph.astream(initial):
        for node_name, node_state in event.items():
            # A node with no actual field updates (e.g. retrieval_gate) surfaces as None here.
            node_state = node_state or {}
            new_entries = node_state.get("thinking_log", [])
            for entry in new_entries:
                yield entry

            accumulated["thinking_log"] = accumulated["thinking_log"] + new_entries
            accumulated.update({k: v for k, v in node_state.items() if k != "thinking_log"})

            if node_name == "generator" and not answer_yielded:
                answer_yielded = True
                yield {
                    "type":    "done",
                    "node":    "generator",
                    "message": "Response ready",
                    "data": {
                        "final_response": accumulated.get("raw_answer", ""),
                        "citations":      accumulated.get("citations", []),
                        "eval_scores":    {},
                        "route":          accumulated.get("route", ""),
                        "is_refusal":     accumulated.get("is_refusal", False),
                        "follow_ups":     [],
                    },
                }

            elif node_name == "eval_agent":
                eval_scores = accumulated.get("eval_scores", {})
                final       = accumulated.get("final_response", accumulated.get("raw_answer", ""))
                yield {
                    "type":    "patch_eval",
                    "node":    "eval_agent",
                    "message": "Eval complete",
                    "data":    {"eval_scores": eval_scores, "final_response": final},
                }

            elif node_name == "follow_up_agent":
                follow_ups  = accumulated.get("follow_ups", [])
                result_data = {
                    "final_response": accumulated.get("final_response", ""),
                    "citations":      accumulated.get("citations", []),
                    "eval_scores":    accumulated.get("eval_scores", {}),
                    "route":          accumulated.get("route", ""),
                    "is_refusal":     accumulated.get("is_refusal", False),
                    "follow_ups":     follow_ups,
                }
                if not accumulated.get("is_refusal", True):
                    await asyncio.to_thread(set_answer, cache_patient_id, question, result_data)

                yield {
                    "type":    "patch_followups",
                    "node":    "follow_up_agent",
                    "message": "Follow-ups ready",
                    "data":    {"follow_ups": follow_ups},
                }
