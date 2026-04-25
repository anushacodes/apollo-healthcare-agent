from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, TypedDict

from groq import Groq
from langgraph.graph import StateGraph, END

from app.config import settings
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import search_chunks_async, embed_chunks_async
from app.agent.research_agent import fetch_pubmed, search_research
from app.agent.eval_agent import run_eval
from app.agent.sqlite_cache import (
    get_answer,
    hash_payload,
    hash_text,
    is_document_indexed,
    mark_document_indexed,
    set_answer,
)

log = logging.getLogger(__name__)

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
    follow_ups:          list[str]


# ── Prompts ───────────────────────────────────────────────────────────────

_FOLLOW_UP_PROMPT = """\
You are an expert clinical AI. Based on the RAG context and the answer just provided,
generate 3 insightful, dynamic follow-up questions the clinician might want to ask next.
Make them highly specific to the patient's condition, recent labs, or the provided research.

Return ONLY valid JSON:
{
  "follow_up_questions": ["Question 1", "Question 2", "Question 3"]
}
"""

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
You are a clinical decision support assistant helping a clinician understand their patient.
Answer the question directly and concisely, like a knowledgeable clinical colleague.

RULES:
1. Answer the clinical question directly. NEVER say "according to the chunks",
   "the context shows", "based on the provided information", "the context chunks",
   or any similar meta-language. Just answer.
2. Lead with the answer. If data is missing, mention it briefly at the END — not the front.
3. Use bullet points for lists of findings; prose for explanations.
4. Cite specific data points inline [1], [2] etc. — but only when referencing a specific
   number, study finding, or guideline. Do not cite general clinical knowledge.
5. If the information is genuinely not available, say so in one sentence at the end.

PATIENT INFORMATION AND RESEARCH:
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


def _patient_cache_id(patient_id: str, patient_data: dict) -> str:
    fingerprint = hash_payload(
        {
            "patient": patient_data.get("patient", {}),
            "summary": patient_data.get("summary", {}),
        }
    )[:12]
    return f"{patient_id}:{fingerprint}"


async def _ensure_patient_documents_embedded(patient_id: str, source_docs: dict[str, str]) -> int:
    chunks_to_embed = []
    new_docs = 0

    for label, text in source_docs.items():
        if not text:
            continue
        content_hash = hash_text(text)
        if is_document_indexed(patient_id, label, content_hash):
            continue

        doc_chunks = chunk_text(text, patient_id, label)
        chunks_to_embed.extend(doc_chunks)
        new_docs += 1

    if chunks_to_embed:
        await embed_chunks_async(chunks_to_embed)

    for label, text in source_docs.items():
        if not text:
            continue
        content_hash = hash_text(text)
        if is_document_indexed(patient_id, label, content_hash):
            continue
        mark_document_indexed(
            patient_id,
            label,
            content_hash,
            chunk_count=sum(1 for chunk in chunks_to_embed if chunk["source_doc"] == label),
        )

    return new_docs


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


async def patient_retriever_node(state: RAGState) -> RAGState:
    if state["route"] == "research":
        return state

    log.info("[rag] patient_retriever starting")
    thinking = _ev("patient_retriever", "thinking",
                   "Searching uploaded patient documents...")

    source_docs = state["patient_data"].get("source_documents", {})
    if source_docs:
        new_docs = await _ensure_patient_documents_embedded(state["patient_id"], source_docs)
    else:
        new_docs = 0

    results = await search_chunks_async(state["reformulated_query"], state["patient_id"], top_k=8)
    sources = list({c.get("source_doc","") for c in results})
    if results:
        message = f"Found {len(results)} chunks across {len(sources)} document(s)"
        if new_docs:
            message += f"; indexed {new_docs} new document(s)"
    else:
        message = (
            f"No relevant chunks in patient documents; indexed {new_docs} new document(s)"
            if new_docs else "No relevant chunks in patient documents"
        )

    result = _ev(
        "patient_retriever",
        "result",
        message,
        {"chunk_count": len(results), "sources": sources, "new_docs_indexed": new_docs},
    )

    return {**state,
            "patient_chunks": results,
            "thinking_log": state["thinking_log"] + [thinking, result]}


async def research_fetcher_node(state: RAGState) -> RAGState:
    if state["route"] == "patient_docs":
        return state

    log.info("[rag] research_fetcher starting")
    diagnoses = [d.get("name","") if isinstance(d, dict) else str(d)
                 for d in state["patient_data"].get("summary",{}).get("diagnoses",[])]
    thinking = _ev("research_fetcher", "thinking",
                   f"Querying PubMed for: {', '.join(diagnoses[:2])}...",
                   {"diagnoses": diagnoses[:3]})

    # fetch_pubmed hits the SQLite cache first — if the background thread already
    # ran it (fired from WebSocket open), this returns instantly with 0 network calls.
    await asyncio.to_thread(fetch_pubmed, state["patient_id"], diagnoses, state["reformulated_query"])
    results = await search_chunks_async(state["reformulated_query"], state["patient_id"], top_k=6, doc_type="pubmed_abstract")

    journals = list({c.get("journal","") for c in results if c.get("journal")})
    result = _ev("research_fetcher", "result",
                 (
                     f"Found {len(results)} relevant research chunk(s)"
                     + (f" ({', '.join(journals[:3])})" if journals else "")
                     if results
                     else "No indexed PubMed chunks yet; background fetch started"
                 ),
                 {"chunk_count": len(results), "journals": journals, "background_prefetch": True})

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


def _build_patient_summary_chunk(patient_data: dict, patient_id: str) -> dict | None:
    """
    Convert the structured patient summary into a synthetic RAG chunk.
    This ensures the generator always has access to the patient's structured
    data (labs, meds, diagnoses, flags) even when document retrieval is sparse.
    """
    s = patient_data.get("summary", {})
    p = patient_data.get("patient", {})
    if not s and not p:
        return None

    lines = []

    # Patient header
    name = p.get("name", "Unknown")
    age  = p.get("age", "?")
    mrn  = p.get("mrn", "")
    lines.append(f"PATIENT RECORD — {name}, Age {age}" + (f" | MRN: {mrn}" if mrn else ""))

    # Narrative
    narrative = s.get("summary_narrative", "")
    if narrative:
        lines.append(f"\nCLINICAL SUMMARY:\n{narrative}")

    # Diagnoses
    diagnoses = s.get("diagnoses", [])
    if diagnoses:
        lines.append("\nDIAGNOSES:")
        for d in diagnoses:
            name_d = d.get("name", str(d)) if isinstance(d, dict) else str(d)
            status = d.get("status", "") if isinstance(d, dict) else ""
            icd    = d.get("icd_code", "") if isinstance(d, dict) else ""
            since  = d.get("date_first_noted", "") if isinstance(d, dict) else ""
            parts  = [f"- {name_d}"]
            if icd:    parts.append(f"[{icd}]")
            if status: parts.append(f"— {status}")
            if since:  parts.append(f"(since {since})")
            lines.append(" ".join(parts))

    # Medications
    meds = s.get("medications", [])
    if meds:
        lines.append("\nCURRENT MEDICATIONS:")
        for m in meds:
            if isinstance(m, dict):
                dose = m.get("dose", "")
                freq = m.get("frequency", "")
                lines.append(f"- {m.get('name', '?')} {dose} {freq}".strip())
            else:
                lines.append(f"- {m}")

    # Recent labs
    labs = s.get("lab_results", [])
    if labs:
        lines.append("\nRECENT LAB RESULTS:")
        for lab in labs:
            if isinstance(lab, dict):
                flag = f" [{lab.get('flag','').upper()}]" if lab.get("flag") and lab["flag"] not in ("normal", "") else ""
                date = f" ({lab.get('date', '')})" if lab.get("date") else ""
                lines.append(f"- {lab.get('test_name','?')}: {lab.get('value','?')} {lab.get('unit','')}{flag}{date}".strip())

    # Clinical flags
    flags = s.get("clinical_flags", [])
    if flags:
        lines.append("\nCLINICAL FLAGS:")
        for f in flags:
            text = f.get("text", str(f)) if isinstance(f, dict) else str(f)
            lines.append(f"- {text}")

    # Recent timeline (last 5 events)
    timeline = s.get("timeline", [])
    if timeline:
        lines.append("\nRECENT TIMELINE:")
        for ev in timeline[-5:]:
            if isinstance(ev, dict):
                lines.append(f"- {ev.get('date','?')}: {ev.get('event','')}")

    # Allergies
    allergies = s.get("allergies", [])
    if allergies:
        lines.append(f"\nALLERGIES: {', '.join(str(a) for a in allergies)}")

    text = "\n".join(lines).strip()
    if not text:
        return None

    return {
        "chunk_id":   "structured_summary",
        "patient_id": patient_id,
        "source_doc": "patient_record",
        "doc_type":   "structured_summary",
        "text":       text,
        "score":      999.0,   # always ranks first
    }


def context_assembler_node(state: RAGState) -> RAGState:
    seen, merged = set(), []

    # Always inject the structured patient record as the first chunk
    # so the generator has direct access to labs, meds, and diagnoses
    # even when document retrieval is sparse.
    if state["route"] != "research":
        summary_chunk = _build_patient_summary_chunk(state["patient_data"], state["patient_id"])
        if summary_chunk:
            seen.add(summary_chunk["text"][:80])
            merged.append(summary_chunk)

    for chunk in state["patient_chunks"] + state["research_chunks"] + state["web_chunks"]:
        key = chunk.get("text", "")[:80]
        if key not in seen:
            seen.add(key)
            merged.append(chunk)

    merged.sort(key=lambda c: c.get("score", 0), reverse=True)
    return {**state, "all_chunks": merged[:14]}


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

    final = state["raw_answer"]
    if faith < 0.70 or hallu:
        final += f"\n\n⚠️ **Eval Agent Warning:** Faithfulness is low ({faith:.0%}).\n"
        if scores.get("unsupported_claims"):
            final += "Unsupported claims:\n" + "\n".join(f"• {c}" for c in scores.get("unsupported_claims",[]))

    result = _ev("eval_agent", "result",
                 f"Faithfulness: {faith:.0%} | {'Hallucination ⚠' if hallu else 'Verified ✓'}",
                 scores)

    return {**state,
            "eval_scores": scores,
            "final_response": final,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def follow_up_node(state: RAGState) -> RAGState:
    log.info("[rag] follow_up starting")
    if state.get("is_refusal", False):
        return {**state, "follow_ups": []}

    thinking = _ev("follow_up_agent", "thinking", "Generating dynamic follow-up questions...")
    try:
        res = _groq_json(
            user=f"Question: {state['question']}\n\nAnswer: {state['raw_answer']}",
            system=_FOLLOW_UP_PROMPT,
        )
        follow_ups = res.get("follow_up_questions", [])
    except Exception as exc:
        log.warning("[rag] Follow-up generation failed: %s", exc)
        follow_ups = []

    result = _ev("follow_up_agent", "result", f"Generated {len(follow_ups)} follow-up questions", {"follow_ups": follow_ups})

    return {**state,
            "follow_ups": follow_ups,
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
    Stream the RAG pipeline. Emits only NEW thinking_log entries per node
    (fixes the duplicate-entry bug where cumulative log was re-emitted).
    Caches final answers so repeated questions are instant.
    """
    cache_patient_id = _patient_cache_id(patient_id, patient_data)
    cached_answer = get_answer(cache_patient_id, question)
    if cached_answer:
        log.info("[rag] SQLite Answer cache hit for patient %s", patient_id)
        await asyncio.sleep(2)
        yield {"type": "done", "node": "cache", "message": "Response ready",
               "data": cached_answer}
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

    yielded_count = 0
    answer_yielded = False  # track whether we've already sent the done event

    async for event in rag_graph.astream(initial):
        for node_name, node_state in event.items():
            tlog = node_state.get("thinking_log", [])
            new_entries = tlog[yielded_count:]
            for entry in new_entries:
                yield entry
            yielded_count = len(tlog)

            # ── Fire "done" immediately after generator completes ──────────
            # The user can start reading while eval + follow-up run in the bg.
            if node_name == "generator" and not answer_yielded:
                answer_yielded = True
                yield {
                    "type":    "done",
                    "node":    "generator",
                    "message": "Response ready",
                    "data": {
                        "final_response": node_state.get("raw_answer", ""),
                        "citations":      node_state.get("citations", []),
                        "eval_scores":    {},       # filled in by patch_eval
                        "route":          node_state.get("route", ""),
                        "is_refusal":     node_state.get("is_refusal", False),
                        "follow_ups":     [],       # filled in by patch_followups
                    },
                }

            # ── Eval scores arrive as a patch ──────────────────────────────
            elif node_name == "eval_agent":
                eval_scores = node_state.get("eval_scores", {})
                # Append any faithfulness warning to the rendered answer
                final = node_state.get("final_response", node_state.get("raw_answer", ""))
                yield {
                    "type":    "patch_eval",
                    "node":    "eval_agent",
                    "message": "Eval complete",
                    "data": {
                        "eval_scores":    eval_scores,
                        "final_response": final,
                    },
                }

            # ── Follow-ups arrive as a patch; cache the full result here ───
            elif node_name == "follow_up_agent":
                follow_ups = node_state.get("follow_ups", [])
                result_data = {
                    "final_response": node_state.get("final_response", ""),
                    "citations":      node_state.get("citations", []),
                    "eval_scores":    node_state.get("eval_scores", {}),
                    "route":          node_state.get("route", ""),
                    "is_refusal":     node_state.get("is_refusal", False),
                    "follow_ups":     follow_ups,
                }
                if not node_state.get("is_refusal", True):
                    set_answer(cache_patient_id, question, result_data)

                yield {
                    "type":    "patch_followups",
                    "node":    "follow_up_agent",
                    "message": "Follow-ups ready",
                    "data":    {"follow_ups": follow_ups},
                }

