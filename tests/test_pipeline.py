from unittest.mock import AsyncMock

import pytest

from app.agent.contracts import FollowUpQuestions, RouterDecision
from app.agent.rag import nodes
from app.agent.rag.graph import run_rag_streaming
from app.agent.sqlite_cache import get_answer
from app.ingestion.chunker import chunk_text


def test_chunker_is_stable_and_patient_scoped(case_a):
    text = case_a["source_documents"]["labs"]
    chunks = chunk_text(text, "first", "labs")
    assert chunks
    assert chunks == chunk_text(text, "first", "labs")
    assert {c["chunk_id"] for c in chunks}.isdisjoint(
        c["chunk_id"] for c in chunk_text(text, "second", "labs")
    )


@pytest.fixture
def rag_services(monkeypatch):
    chunks = [{"text": f"Clinical evidence {i}", "source_doc": f"guideline-{i}"} for i in range(3)]
    monkeypatch.setattr(nodes, "_ensure_patient_documents_embedded", AsyncMock(return_value=0))
    monkeypatch.setattr(nodes, "search_chunks_async", AsyncMock(return_value=chunks))
    monkeypatch.setattr(nodes, "call_search_clinical_guidelines", AsyncMock(return_value=chunks))
    monkeypatch.setattr(nodes, "_web_search_chunks", lambda *a: chunks)
    monkeypatch.setattr(nodes, "_groq_text", lambda **kw: "Grounded answer [1].")
    monkeypatch.setattr(nodes, "run_eval", lambda **kw: {
        "faithfulness": 0.95, "hallucination_detected": False, "skipped": False,
    })
    return chunks


def route_to(monkeypatch, route):
    def structured(model, **kwargs):
        if model is RouterDecision:
            return RouterDecision(route=route, reformulated_query="clinical evidence")
        return FollowUpQuestions(follow_up_questions=["What next?"])
    monkeypatch.setattr(nodes, "_groq_structured", structured)


@pytest.mark.parametrize("route,expected,absent", [
    ("patient_docs", "patient_retriever", "research_fetcher"),
    ("research", "research_fetcher", "patient_retriever"),
    ("both", "research_fetcher", "web_search"),
])
async def test_rag_routes_streams_and_caches(monkeypatch, rag_services, case_a, route, expected, absent):
    route_to(monkeypatch, route)
    events = [e async for e in run_rag_streaming("demo", case_a, "Question?")]
    names = [e["node"] for e in events]
    assert expected in names
    assert absent not in names
    assert names.count("generator") == 3  # thinking, result, answer
    assert [e["type"] for e in events if e["type"].startswith("patch_")] == [
        "patch_eval", "patch_followups",
    ]
    cached = [e async for e in run_rag_streaming("demo", case_a, "Question?")]
    assert len(cached) == 1
    assert cached[0]["node"] == "cache"
    assert cached[0]["data"]["follow_ups"] == ["What next?"]
    assert cached[0]["data"]["eval_scores"]["faithfulness"] == 0.95


async def test_sparse_research_uses_web_fallback(monkeypatch, rag_services):
    route_to(monkeypatch, "research")
    monkeypatch.setattr(nodes, "call_search_clinical_guidelines", AsyncMock(return_value=[]))
    events = [e async for e in run_rag_streaming("demo", {}, "Question?")]
    assert any(e["node"] == "web_search" for e in events)
    assert any(e["type"] == "done" for e in events)


async def test_insufficient_context_refuses_without_eval(monkeypatch, rag_services):
    route_to(monkeypatch, "patient_docs")
    monkeypatch.setattr(nodes, "search_chunks_async", AsyncMock(return_value=[]))
    events = [e async for e in run_rag_streaming("demo", {}, "Question?")]
    answer = next(e for e in events if e["type"] == "done")
    assert answer["data"]["is_refusal"] is True
    assert not any(e["node"] == "eval_agent" for e in events)


@pytest.mark.parametrize("scores", [
    {"faithfulness": 0.2, "hallucination_detected": True},
    {"faithfulness": 0, "skipped": True},
])
async def test_unverified_answer_not_cached(monkeypatch, rag_services, scores):
    route_to(monkeypatch, "research")
    monkeypatch.setattr(nodes, "run_eval", lambda **kw: scores)
    events = [e async for e in run_rag_streaming("demo", {}, "Question?")]
    patch = next(e for e in events if e["type"] == "patch_eval")
    assert patch["data"]["final_response"] != "Grounded answer [1]."
    assert get_answer(nodes._patient_cache_id("demo", {}), "Question?") is None


async def test_generation_failure_does_not_become_answer(monkeypatch, rag_services):
    route_to(monkeypatch, "research")
    def fail(**kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(nodes, "_groq_text", fail)
    with pytest.raises(RuntimeError, match="Answer generation failed"):
        _ = [e async for e in run_rag_streaming("demo", {}, "Question?")]
