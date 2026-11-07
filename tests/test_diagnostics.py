import pytest

from app.agent.diagnostics.graph import run_graph_streaming
from app.agent.summarizer import build_context


@pytest.mark.parametrize("case_key", ["case_a", "case_b", "case_c"])
async def test_diagnostics_completes_without_live_providers(case_key):
    from app.agent.seed_patient import get_case
    events = [event async for event in run_graph_streaming(get_case(case_key))]
    assert [event["node"] for event in events] == [
        "orchestrator", "tool_node", "drug_graph", "diagnosis", "summarizer",
    ]
    assert len(events[-1]["audit_log"]) == 5
    summary = events[-1]["final_summary"]
    assert summary["model_used"] == "heuristic/fallback"
    assert summary["patient_facing_summary"]


def test_summary_context_includes_upstream_findings(case_a):
    case_a["calculator_results"] = [{"tool": "example", "result": 7}]
    case_a["agent_diagnoses"] = {"primary_diagnosis": "example finding"}
    case_a["drug_interactions"] = {"overall_risk": "moderate"}
    context = build_context(case_a)
    assert '"result": 7' in context
    assert "example finding" in context
    assert '"overall_risk": "moderate"' in context
