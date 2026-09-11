import logging
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.diagnostics.nodes import (
    diagnosis_node,
    drug_graph_node,
    orchestrator_node,
    summarizer_node,
    tool_node,
)
from app.agent.diagnostics.state import AgentState

log = logging.getLogger(__name__)


def _build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("drug_graph",   drug_graph_node)
    workflow.add_node("diagnosis",    diagnosis_node)
    workflow.add_node("tool_node",    tool_node)
    workflow.add_node("summarizer",   summarizer_node)

    workflow.set_entry_point("orchestrator")

    # Pipeline sequence:
    # 1. orchestrator plans calculators & KG symptoms
    # 2. tool_node executes calculators immediately (<5ms)
    # 3. drug_graph queries KG & evaluates drug interactions
    # 4. diagnosis synthesizes notes, KG matches, and calculator findings
    # 5. summarizer synthesizes all node outputs into the final clinical summary
    workflow.add_edge("orchestrator", "tool_node")
    workflow.add_edge("tool_node",    "drug_graph")
    workflow.add_edge("drug_graph",   "diagnosis")
    workflow.add_edge("diagnosis",    "summarizer")
    workflow.add_edge("summarizer",   END)

    return workflow.compile()


graph = _build_graph()


async def run_graph_streaming(patient_data: dict) -> AsyncGenerator[dict, None]:
    """Run the full diagnostics graph, yielding a state update after every node."""
    patient_id    = patient_data.get("patient_id", "unknown")
    initial_state: AgentState = {
        "patient_id":         patient_id,
        "patient_data":       patient_data,
        "anonymized_notes":   "",
        "extracted_params":   {},
        "calculator_results": [],
        "diagnoses":          {},
        "interactions":       {},
        "kg_matches":         [],
        "final_summary":      None,
        "audit_log":          [],
        "error":              None,
    }

    async for event in graph.astream(initial_state):
        for node_name, node_state in event.items():
            audit_log    = node_state.get("audit_log", [])
            latest_entry = audit_log[-1] if audit_log else ""

            payload: dict[str, Any] = {
                "node":        node_name,
                "audit_entry": latest_entry,
                "audit_log":   audit_log,
            }

            if node_name == "orchestrator":
                payload["extracted_params"] = node_state.get("extracted_params", {})
            elif node_name == "drug_graph":
                payload["interactions"] = node_state.get("interactions", {})
                payload["kg_matches"]   = node_state.get("kg_matches", [])
            elif node_name == "diagnosis":
                payload["diagnoses"] = node_state.get("diagnoses", {})
            elif node_name == "tool_node":
                payload["calculator_results"] = node_state.get("calculator_results", [])
            elif node_name == "summarizer":
                summary = node_state.get("final_summary")
                payload["final_summary"] = summary.model_dump(mode="json") if summary else None

            yield payload
