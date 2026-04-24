from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, TypedDict

from groq import Groq
from langgraph.graph import StateGraph, END

from app.config import settings
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import search_chunks, embed_chunks
from app.agent.research_agent import fetch_pubmed, search_research
from app.agent.eval_agent import run_eval

log = logging.getLogger(__name__)

# In-memory answer cache: (patient_id, question_lower) → final response
_answer_cache: dict[tuple, dict] = {}

# ── State ─────────────────────────────────────────────────────────────────

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


# ── Prompts ───────────────────────────────────────────────────────────────

_ROUTER_PROMPT = """\
You are a clinical query router. Given a patient question, decide:
1. route: "patient_docs" = question about this specific patient's records only.
   "research" = question about treatment guidelines, clinical evidence, general medical knowledge.
   "both" = needs both patient record AND clinical literature.
2. A short, precise medical search query (no date filters, no operators — just key terms).

Return ONLY valid JSON:
{
  "route": "patient_docs|research|both",
  "reformulated_query": "<key medical terms only>",
  "reasoning": "<one sentence>"
}
"""

_GENERATOR_PROMPT = """\
You are a clinical research assistant. Answer the question using the context chunks below.

RULES:
1. Use information from the CONTEXT CHUNKS.
2. Cite every factual claim: [1], [2], etc.
3. Be concise — use bullet points where appropriate.
4. You MAY use your clinical knowledge to connect and explain information from the chunks,
   but every specific fact (dosing, guidelines, study results) MUST come from a chunk.
5. If chunks contain no relevant information, say so clearly.

CONTEXT CHUNKS:
{chunks}

QUESTION: {question}
"""


# ── Helpers ───────────────────────────────────────────────────────────────

def _groq_json(user: str, system: str = "") -> dict:
    client = Groq(api_key=settings.groq_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        temperature=0.1,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def _groq_text(system: str, user: str, max_tokens: int = 1200) -> str:
    resp = Groq(api_key=settings.groq_api_key).chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _format_chunks(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        source = c.get("source_doc") or c.get("title") or "unknown"
        text   = c.get("text", "")[:900]
        lines.append(f"[{i}] Source: {source}\n{text}")
    return "\n\n---\n\n".join(lines)


def _ev(node: str, etype: str, message: str, data: dict | None = None) -> dict:
    return {"node": node, "type": etype, "message": message, "data": data or {}}


# ── Web search fallback ───────────────────────────────────────────────────

def _web_search_chunks(query: str, patient_id: str, diagnoses: list[str]) -> list[dict]:
    """
    Tavily search (primary) with DuckDuckGo fallback.
    Targets authoritative clinical sources for high-quality context.
    """
    # ── Tavily (preferred) ───────────────────────────────────────────────
    if settings.has_tavily:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=settings.tavily_api_key)
            resp = client.search(
                query=f"{query} clinical guidelines treatment",
                search_depth="advanced",
                include_domains=[
                    "pubmed.ncbi.nlm.nih.gov", "nejm.org", "bmj.com",
                    "thelancet.com", "uptodate.com", "medscape.com",
                    "acr.org", "nih.gov", "cdc.gov", "who.int",
                    "annrheumdis.bmj.com",
                ],
                max_results=6,
            )
            chunks = []
            for i, r in enumerate(resp.get("results", [])):
                content = r.get("content","") or r.get("raw_content","")
                title   = r.get("title","")
                text    = f"{title}\n{content}".strip()
                if len(text) < 40:
                    continue
                chunks.append({
                    "text":       text[:1000],
                    "source_doc": r.get("url", "tavily"),
                    "title":      title,
                    "doc_type":   "web_result",
                    "url":        r.get("url",""),
                    "score":      r.get("score", 0.5 - i * 0.05),
                    "chunk_id":   f"web_{i}",
                    "patient_id": patient_id,
                })
            log.info("[rag] Tavily returned %d chunks", len(chunks))
            return chunks
        except Exception as exc:
            log.warning("[rag] Tavily failed: %s — trying DuckDuckGo", exc)

    # ── DuckDuckGo fallback ──────────────────────────────────────────────
    try:
        from duckduckgo_search import DDGS
        medical_q = f"{query} clinical guidelines site:nih.gov OR site:nejm.org OR site:bmj.com"
        results = list(DDGS().text(medical_q, max_results=5))
        chunks = []
        for i, r in enumerate(results):
            text = f"{r.get('title','')}\n{r.get('body','')}".strip()
            if len(text) < 40:
                continue
            chunks.append({
                "text":       text[:900],
                "source_doc": r.get("href","web"),
                "title":      r.get("title",""),
                "doc_type":   "web_result",
                "url":        r.get("href",""),
                "score":      0.45 - (i * 0.05),
                "chunk_id":   f"ddg_{i}",
                "patient_id": patient_id,
            })
        log.info("[rag] DuckDuckGo returned %d chunks", len(chunks))
        return chunks
    except Exception as exc:
        log.warning("[rag] Web search failed: %s", exc)
        return []


# ── Nodes ─────────────────────────────────────────────────────────────────

def query_router_node(state: RAGState) -> RAGState:
    log.info("[rag] query_router starting")
    thinking = _ev("query_router", "thinking", "Classifying your question and selecting sources...")

    route, reformulated, reasoning = "both", state["question"], ""
    try:
        patient  = state["patient_data"].get("patient", {})
        diagnoses = [d.get("name","") if isinstance(d, dict) else d
                     for d in state["patient_data"].get("summary",{}).get("diagnoses",[])]
        ctx = f"Patient: {patient.get('name','?')}, Age: {patient.get('age','?')}, Diagnoses: {diagnoses[:3]}"
        res = _groq_json(
            user=f"Patient context: {ctx}\n\nQuestion: {state['question']}",
            system=_ROUTER_PROMPT,
        )
        route        = res.get("route", "both")
        reformulated = res.get("reformulated_query", state["question"])
        reasoning    = res.get("reasoning", "")
    except Exception as exc:
        log.warning("[rag] Router failed: %s", exc)

    result = _ev("query_router",
                 "result",
                 f"Routing to: {route} | Query: \"{reformulated}\"",
                 {"route": route, "reformulated_query": reformulated, "reasoning": reasoning})

    return {**state,
            "route": route,
            "reformulated_query": reformulated,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def patient_retriever_node(state: RAGState) -> RAGState:
    if state["route"] == "research":
        return state

    log.info("[rag] patient_retriever starting")
    thinking = _ev("patient_retriever", "thinking",
                   f"Searching uploaded patient documents...")

    source_docs = state["patient_data"].get("source_documents", {})
    if source_docs:
        to_embed = []
        for label, text in source_docs.items():
            if text:
                to_embed.extend(chunk_text(text, state["patient_id"], label))
        if to_embed:
            embed_chunks(to_embed)

    results = search_chunks(state["reformulated_query"], state["patient_id"], top_k=8)
    sources = list({c.get("source_doc","") for c in results})

    result = _ev("patient_retriever", "result",
                 f"Found {len(results)} chunks across {len(sources)} document(s)" if results
                 else "No relevant chunks in patient documents",
                 {"chunk_count": len(results), "sources": sources})

    return {**state,
            "patient_chunks": results,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def research_fetcher_node(state: RAGState) -> RAGState:
    if state["route"] == "patient_docs":
        return state

    log.info("[rag] research_fetcher starting")
    diagnoses = [d.get("name","") if isinstance(d, dict) else str(d)
                 for d in state["patient_data"].get("summary",{}).get("diagnoses",[])]
    thinking = _ev("research_fetcher", "thinking",
                   f"Querying PubMed for: {', '.join(diagnoses[:2])}...",
                   {"diagnoses": diagnoses[:3]})

    # Always re-embed on cache miss; if cache hit, still search (embedding may have happened)
    papers  = fetch_pubmed(state["patient_id"], diagnoses, state["reformulated_query"])
    results = search_research(state["patient_id"], state["reformulated_query"], top_k=6)

    journals = list({c.get("journal","") for c in results if c.get("journal")})
    result = _ev("research_fetcher", "result",
                 f"Retrieved {len(papers)} papers, {len(results)} relevant chunks"
                 + (f" ({', '.join(journals[:3])})" if journals else ""),
                 {"paper_count": len(papers), "chunk_count": len(results), "journals": journals})

    return {**state,
            "research_chunks": results,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def web_search_node(state: RAGState) -> RAGState:
    """
    Falls back to DuckDuckGo if combined chunk count < 3 after PubMed + patient docs.
    Only runs on research/both routes.
    """
    combined = state["patient_chunks"] + state["research_chunks"]
    if len(combined) >= 3 or state["route"] == "patient_docs":
        return state

    log.info("[rag] web_search fallback starting")
    diagnoses = [d.get("name","") if isinstance(d, dict) else str(d)
                 for d in state["patient_data"].get("summary",{}).get("diagnoses",[])]
    source_label = "Tavily (clinical web)" if settings.has_tavily else "DuckDuckGo"
    thinking = _ev("web_search", "thinking",
                   f"PubMed results sparse — searching {source_label} for clinical evidence...")

    chunks = _web_search_chunks(state["reformulated_query"], state["patient_id"], diagnoses)
    result = _ev("web_search", "result",
                 f"Found {len(chunks)} web results from clinical sources" if chunks
                 else "Web search returned no results",
                 {"chunk_count": len(chunks)})

    return {**state,
            "web_chunks": chunks,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def context_assembler_node(state: RAGState) -> RAGState:
    seen, merged = set(), []
    for chunk in state["patient_chunks"] + state["research_chunks"] + state["web_chunks"]:
        key = chunk.get("text","")[:80]
        if key not in seen:
            seen.add(key)
            merged.append(chunk)
    merged.sort(key=lambda c: c.get("score", 0), reverse=True)
    return {**state, "all_chunks": merged[:12]}


def sufficiency_judge_node(state: RAGState) -> RAGState:
    log.info("[rag] sufficiency_judge starting")
    chunks = state["all_chunks"]
    thinking = _ev("sufficiency_judge", "thinking",
                   "Assessing context coverage...")

    # Hard rule: if we have ≥ 2 chunks, treat as sufficient.
    # The generator and eval agent are the real quality gates.
    if len(chunks) >= 2:
        result = _ev("sufficiency_judge", "result",
                     f"Context sufficient — {len(chunks)} chunks available",
                     {"sufficient": True, "confidence": 0.85})
        return {**state,
                "context_sufficient": True,
                "thinking_log": state["thinking_log"] + [thinking, result]}

    result = _ev("sufficiency_judge", "result",
                 "Insufficient context — will note in response",
                 {"sufficient": False, "confidence": 0.0})
    return {**state,
            "context_sufficient": False,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def generator_node(state: RAGState) -> RAGState:
    log.info("[rag] generator starting")
    chunks = state["all_chunks"]

    if not state["context_sufficient"]:
        refusal = (
            "No relevant sources were found for this question. "
            "This may mean the RAG index is still building (PubMed abstracts are being embedded). "
            "Try again in a few seconds, or upload patient documents in the Documents tab."
        )
        return {**state,
                "raw_answer": refusal,
                "is_refusal": True,
                "citations": [],
                "thinking_log": state["thinking_log"] + [
                    _ev("generator", "result", "Returning context-not-found message", {})
                ]}

    thinking = _ev("generator", "thinking",
                   f"Generating grounded response from {len(chunks)} chunks...")

    answer = ""
    try:
        answer = _groq_text(
            system=_GENERATOR_PROMPT.format(
                chunks=_format_chunks(chunks),
                question=state["question"],
            ),
            user=state["question"],
        )
    except Exception as exc:
        log.error("[rag] Generator failed: %s", exc)
        answer = f"Generation error: {exc}"

    citations = []
    for i, c in enumerate(chunks, 1):
        if f"[{i}]" in answer:
            citations.append({
                "ref":        i,
                "source_doc": c.get("source_doc") or c.get("title") or "unknown",
                "doc_type":   c.get("doc_type",""),
                "doi":        c.get("doi",""),
                "url":        c.get("url",""),
                "journal":    c.get("journal",""),
                "year":       c.get("year",""),
                "snippet":    c.get("text","")[:200],
            })

    result = _ev("generator", "result",
                 f"Answer ready — {len(citations)} citation(s)",
                 {"citation_count": len(citations)})

    return {**state,
            "raw_answer": answer,
            "is_refusal": False,
            "citations": citations,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def eval_node(state: RAGState) -> RAGState:
    log.info("[rag] eval starting")

    # Skip eval for refusals — nothing to verify
    if state.get("is_refusal", False):
        result = _ev("eval_agent", "result",
                     "Skipped — no answer to evaluate",
                     {"faithfulness": None, "skipped": True})
        return {**state,
                "eval_scores": {"skipped": True},
                "final_response": state["raw_answer"],
                "thinking_log": state["thinking_log"] + [
                    _ev("eval_agent", "thinking", "Evaluating response..."),
                    result,
                ]}

    thinking = _ev("eval_agent", "thinking",
                   "Checking every claim for faithfulness to sources...")

    scores = run_eval(
        question=state["question"],
        answer=state["raw_answer"],
        chunks=state["all_chunks"],
    )

    faith   = scores.get("faithfulness", 1.0)
    hallu   = scores.get("hallucination_detected", False)
    blocked = scores.get("blocked", False)
    final   = state["raw_answer"] if not blocked else (
        f"⚠️ Response blocked — faithfulness too low ({faith:.0%}).\n\n"
        + ("Unsupported claims:\n" + "\n".join(f"• {c}" for c in scores.get("unsupported_claims",[]))
           if scores.get("unsupported_claims") else "")
    )

    result = _ev("eval_agent", "result",
                 f"Faithfulness: {faith:.0%} | {'Hallucination ⚠' if hallu else 'Verified ✓'}",
                 scores)

    return {**state,
            "eval_scores": scores,
            "final_response": final,
            "thinking_log": state["thinking_log"] + [thinking, result]}


# ── Graph ─────────────────────────────────────────────────────────────────

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

    wf.set_entry_point("query_router")
    wf.add_edge("query_router",      "patient_retriever")
    wf.add_edge("patient_retriever", "research_fetcher")
    wf.add_edge("research_fetcher",  "web_search")
    wf.add_edge("web_search",        "context_assembler")
    wf.add_edge("context_assembler", "sufficiency_judge")
    wf.add_edge("sufficiency_judge", "generator")
    wf.add_edge("generator",         "eval_agent")
    wf.add_edge("eval_agent",        END)
    return wf.compile()


rag_graph = _build_rag_graph()


async def run_rag_streaming(
    patient_id: str,
    patient_data: dict,
    question: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream the RAG pipeline. Emits only NEW thinking_log entries per node
    (fixes the duplicate-entry bug where cumulative log was re-emitted).
    Caches final answers so repeated questions are instant.
    """
    cache_key = (patient_id, question.strip().lower())
    if cache_key in _answer_cache:
        log.info("[rag] Answer cache hit for patient %s", patient_id)
        yield _ev("query_router",  "result", "Answer loaded from cache ⚡", {"cached": True})
        yield {"type": "done", "node": "cache", "message": "Cached response",
               "data": _answer_cache[cache_key]}
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
    }

    yielded_count = 0  # track how many thinking_log entries we've already emitted

    async for event in rag_graph.astream(initial):
        for node_name, node_state in event.items():
            tlog = node_state.get("thinking_log", [])
            # Only yield entries added by THIS node (everything since last yield)
            new_entries = tlog[yielded_count:]
            for entry in new_entries:
                yield entry
            yielded_count = len(tlog)

            if node_name == "eval_agent":
                result_data = {
                    "final_response": node_state.get("final_response", ""),
                    "citations":      node_state.get("citations", []),
                    "eval_scores":    node_state.get("eval_scores", {}),
                    "route":          node_state.get("route", ""),
                    "is_refusal":     node_state.get("is_refusal", False),
                }
                # Cache non-refusal answers
                if not node_state.get("is_refusal", True):
                    _answer_cache[cache_key] = result_data

                yield {"type": "done", "node": "eval_agent",
                       "message": "Response ready", "data": result_data}
