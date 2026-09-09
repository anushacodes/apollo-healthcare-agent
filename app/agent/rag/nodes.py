from __future__ import annotations

import asyncio
import json
import logging

from app.agent.eval_agent import run_eval
from app.agent.rag.prompts import _FOLLOW_UP_PROMPT, _GENERATOR_PROMPT, _ROUTER_PROMPT
from app.agent.rag.state import RAGState
from app.agent.sqlite_cache import (
    hash_payload,
    hash_text,
    is_document_indexed,
    mark_document_indexed,
)
from app.config import settings
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_chunks_async, search_chunks_async
from app.llm_client import get_groq_client
from app.mcp.client import call_search_clinical_guidelines

log = logging.getLogger(__name__)


# ── LLM helpers ──────────────────────────────────────────────────────────────

def _groq_json(user: str, system: str = "") -> dict:
    client = get_groq_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        temperature=0.1,
        max_tokens=2048,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def _groq_text(system: str, user: str, max_tokens: int = 2048) -> str:
    resp = get_groq_client().chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
        reasoning_effort="low",
    )
    return resp.choices[0].message.content.strip()


# ── Formatting helpers ────────────────────────────────────────────────────────

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


# ── Document embedding ────────────────────────────────────────────────────────

async def _ensure_patient_documents_embedded(patient_id: str, source_docs: dict[str, str]) -> int:
    chunks_to_embed = []
    new_docs = 0

    for label, text in source_docs.items():
        if not text:
            continue
        content_hash = hash_text(text)
        already_indexed = await asyncio.to_thread(is_document_indexed, patient_id, label, content_hash)
        if already_indexed:
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
        still_unindexed = not await asyncio.to_thread(is_document_indexed, patient_id, label, content_hash)
        if still_unindexed:
            await asyncio.to_thread(
                mark_document_indexed,
                patient_id,
                label,
                content_hash,
                chunk_count=sum(1 for chunk in chunks_to_embed if chunk["source_doc"] == label),
            )

    return new_docs


# ── Web search ────────────────────────────────────────────────────────────────

def _web_search_chunks(query: str, patient_id: str, diagnoses: list[str]) -> list[dict]:
    """Tavily (primary) with DuckDuckGo fallback. Targets authoritative clinical sources."""
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
                content = r.get("content", "") or r.get("raw_content", "")
                title   = r.get("title", "")
                text    = f"{title}\n{content}".strip()
                if len(text) < 40:
                    continue
                chunks.append({
                    "text":       text[:1000],
                    "source_doc": r.get("url", "tavily"),
                    "title":      title,
                    "doc_type":   "web_result",
                    "url":        r.get("url", ""),
                    "score":      r.get("score", 0.5 - i * 0.05),
                    "chunk_id":   f"web_{i}",
                    "patient_id": patient_id,
                })
            log.info("[rag] Tavily returned %d chunks", len(chunks))
            return chunks
        except Exception as exc:
            log.warning("[rag] Tavily failed: %s — trying DuckDuckGo", exc)

    try:
        from duckduckgo_search import DDGS
        medical_q = f"{query} clinical guidelines site:nih.gov OR site:nejm.org OR site:bmj.com"
        results = list(DDGS().text(medical_q, max_results=5))
        chunks = []
        for i, r in enumerate(results):
            text = f"{r.get('title', '')}\n{r.get('body', '')}".strip()
            if len(text) < 40:
                continue
            chunks.append({
                "text":       text[:900],
                "source_doc": r.get("href", "web"),
                "title":      r.get("title", ""),
                "doc_type":   "web_result",
                "url":        r.get("href", ""),
                "score":      0.45 - (i * 0.05),
                "chunk_id":   f"ddg_{i}",
                "patient_id": patient_id,
            })
        log.info("[rag] DuckDuckGo returned %d chunks", len(chunks))
        return chunks
    except Exception as exc:
        log.warning("[rag] Web search failed: %s", exc)
        return []


# ── Patient summary chunk ─────────────────────────────────────────────────────

def _build_patient_summary_chunk(patient_data: dict, patient_id: str) -> dict | None:
    """
    Convert the structured patient summary into a synthetic RAG chunk.
    Ensures the generator always has labs, meds, diagnoses, and flags
    even when document retrieval is sparse.
    """
    s = patient_data.get("summary", {})
    p = patient_data.get("patient", {})
    if not s and not p:
        return None

    lines = []
    name = p.get("name", "Unknown")
    age  = p.get("age", "?")
    mrn  = p.get("mrn", "")
    lines.append(f"PATIENT RECORD — {name}, Age {age}" + (f" | MRN: {mrn}" if mrn else ""))

    narrative = s.get("summary_narrative", "")
    if narrative:
        lines.append(f"\nCLINICAL SUMMARY:\n{narrative}")

    diagnoses = s.get("diagnoses", [])
    if diagnoses:
        lines.append("\nDIAGNOSES:")
        for d in diagnoses:
            name_d = d.get("name", str(d)) if isinstance(d, dict) else str(d)
            status = d.get("status", "") if isinstance(d, dict) else ""
            icd    = d.get("icd_code", "") if isinstance(d, dict) else ""
            since  = d.get("date_first_noted", "") if isinstance(d, dict) else ""
            parts  = [f"- {name_d}"]
            if icd:
                parts.append(f"[{icd}]")
            if status:
                parts.append(f"— {status}")
            if since:
                parts.append(f"(since {since})")
            lines.append(" ".join(parts))

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

    labs = s.get("lab_results", [])
    if labs:
        lines.append("\nRECENT LAB RESULTS:")
        for lab in labs:
            if isinstance(lab, dict):
                flag = f" [{lab.get('flag', '').upper()}]" if lab.get("flag") and lab["flag"] not in ("normal", "") else ""
                date = f" ({lab.get('date', '')})" if lab.get("date") else ""
                lines.append(f"- {lab.get('test_name', '?')}: {lab.get('value', '?')} {lab.get('unit', '')}{flag}{date}".strip())

    flags = s.get("clinical_flags", [])
    if flags:
        lines.append("\nCLINICAL FLAGS:")
        for f in flags:
            text = f.get("text", str(f)) if isinstance(f, dict) else str(f)
            lines.append(f"- {text}")

    timeline = s.get("timeline", [])
    if timeline:
        lines.append("\nRECENT TIMELINE:")
        for ev in timeline[-5:]:
            if isinstance(ev, dict):
                lines.append(f"- {ev.get('date', '?')}: {ev.get('event', '')}")

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
        "score":      999.0,
    }


# ── Nodes ─────────────────────────────────────────────────────────────────────

def query_router_node(state: RAGState) -> RAGState:
    log.info("[rag] query_router starting")
    thinking = _ev("query_router", "thinking", "Classifying your question and selecting sources...")

    route, reformulated, reasoning = "both", state["question"], ""
    try:
        patient   = state["patient_data"].get("patient", {})
        diagnoses = [d.get("name", "") if isinstance(d, dict) else d
                     for d in state["patient_data"].get("summary", {}).get("diagnoses", [])]
        ctx = f"Patient: {patient.get('name', '?')}, Age: {patient.get('age', '?')}, Diagnoses: {diagnoses[:3]}"
        res = _groq_json(
            user=f"Patient context: {ctx}\n\nQuestion: {state['question']}",
            system=_ROUTER_PROMPT,
        )
        route        = res.get("route", "both")
        reformulated = res.get("reformulated_query", state["question"])
        reasoning    = res.get("reasoning", "")
    except Exception as exc:
        log.warning("[rag] Router failed: %s", exc)

    result = _ev("query_router", "result",
                 f"Routing to: {route} | Query: \"{reformulated}\"",
                 {"route": route, "reformulated_query": reformulated, "reasoning": reasoning})

    return {**state,
            "route": route,
            "reformulated_query": reformulated,
            "thinking_log": state["thinking_log"] + [thinking, result]}


async def patient_retriever_node(state: RAGState) -> RAGState:
    log.info("[rag] patient_retriever starting")
    thinking = _ev("patient_retriever", "thinking", "Searching uploaded patient documents...")

    source_docs = state["patient_data"].get("source_documents", {})
    new_docs = await _ensure_patient_documents_embedded(state["patient_id"], source_docs) if source_docs else 0

    results = await search_chunks_async(state["reformulated_query"], state["patient_id"], top_k=8)
    sources = list({c.get("source_doc", "") for c in results})

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
        "patient_retriever", "result", message,
        {"chunk_count": len(results), "sources": sources, "new_docs_indexed": new_docs},
    )

    return {**state,
            "patient_chunks": results,
            "thinking_log": state["thinking_log"] + [thinking, result]}


async def research_fetcher_node(state: RAGState) -> RAGState:
    log.info("[rag] research_fetcher starting")
    thinking = _ev("research_fetcher", "thinking", "Searching curated clinical guideline corpus...")

    results = await call_search_clinical_guidelines(state["reformulated_query"], top_k=6)

    sources = list({c.get("source_doc", "") for c in results if c.get("source_doc")})
    result = _ev("research_fetcher", "result",
                 (
                     f"Found {len(results)} relevant guideline chunk(s)"
                     + (f" ({', '.join(sources[:3])})" if sources else "")
                     if results
                     else "No relevant guideline chunks found"
                 ),
                 {"chunk_count": len(results), "sources": sources})

    return {**state,
            "research_chunks": results,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def retrieval_gate_node(state: RAGState) -> RAGState:
    """
    Fan-in point after patient_retriever/research_fetcher. Does no work itself —
    exists so the graph has a single place to route from once whichever
    retrieval branches ran have both completed.
    """
    return state


def web_search_node(state: RAGState) -> RAGState:
    """Web search fallback — only reached via graph routing when combined chunk count is sparse."""
    log.info("[rag] web_search fallback starting")
    diagnoses = [d.get("name", "") if isinstance(d, dict) else str(d)
                 for d in state["patient_data"].get("summary", {}).get("diagnoses", [])]
    source_label = "Tavily (clinical web)" if settings.has_tavily else "DuckDuckGo"
    thinking = _ev("web_search", "thinking",
                   f"Corpus results sparse — searching {source_label} for clinical evidence...")

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
    chunks  = state["all_chunks"]
    thinking = _ev("sufficiency_judge", "thinking", "Assessing context coverage...")

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
            "Try rephrasing, or upload patient documents in the Documents tab."
        )
        return {**state,
                "raw_answer": refusal,
                "is_refusal": True,
                "citations":  [],
                "thinking_log": state["thinking_log"] + [
                    _ev("generator", "result", "Returning context-not-found message", {})
                ]}

    thinking = _ev("generator", "thinking", f"Generating grounded response from {len(chunks)} chunks...")

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
                "doc_type":   c.get("doc_type", ""),
                "doi":        c.get("doi", ""),
                "url":        c.get("url", ""),
                "journal":    c.get("journal", ""),
                "year":       c.get("year", ""),
                "snippet":    c.get("text", "")[:200],
            })

    result = _ev("generator", "result",
                 f"Answer ready — {len(citations)} citation(s)",
                 {"citation_count": len(citations)})

    return {**state,
            "raw_answer": answer,
            "is_refusal": False,
            "citations":  citations,
            "thinking_log": state["thinking_log"] + [thinking, result]}


def eval_node(state: RAGState) -> RAGState:
    log.info("[rag] eval starting")

    thinking = _ev("eval_agent", "thinking", "Checking every claim for faithfulness to sources...")

    scores  = run_eval(question=state["question"], answer=state["raw_answer"], chunks=state["all_chunks"])
    faith   = scores.get("faithfulness", 1.0)
    hallu   = scores.get("hallucination_detected", False)

    final = state["raw_answer"]
    if faith < 0.70 or hallu:
        final += f"\n\n⚠️ **Eval Agent Warning:** Faithfulness is low ({faith:.0%}).\n"
        if scores.get("unsupported_claims"):
            final += "Unsupported claims:\n" + "\n".join(f"• {c}" for c in scores.get("unsupported_claims", []))

    result = _ev("eval_agent", "result",
                 f"Faithfulness: {faith:.0%} | {'Hallucination ⚠' if hallu else 'Verified ✓'}",
                 scores)

    return {**state,
            "eval_scores":    scores,
            "final_response": final,
            "thinking_log":   state["thinking_log"] + [thinking, result]}


def follow_up_node(state: RAGState) -> RAGState:
    log.info("[rag] follow_up starting")
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

    result = _ev("follow_up_agent", "result",
                 f"Generated {len(follow_ups)} follow-up questions",
                 {"follow_ups": follow_ups})

    return {**state,
            "follow_ups":   follow_ups,
            "thinking_log": state["thinking_log"] + [thinking, result]}
