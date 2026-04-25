from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_chunks, search_chunks
from app.agent.sqlite_cache import (
    get_pubmed,
    hash_text,
    is_document_indexed,
    mark_document_indexed,
    set_pubmed,
)

log = logging.getLogger(__name__)

_PUBMED_BASE    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_MAX_RESULTS    = 8      # abstracts fetched per query
_RATE_LIMIT_SEC = 0.34   # ~3 req/s (PubMed free tier)
_INFLIGHT_PREFETCHES: set[str] = set()
_PREFETCH_LOCK = threading.Lock()


def _build_query(diagnoses: list[str], free_text: str = "") -> str:
    """
    Build a PubMed query from diagnoses + optional free-text question.
    Adds date filter (last 3 years) and preferred study types.
    """
    if not diagnoses and not free_text:
        return ""

    terms = []
    for dx in diagnoses[:3]:    # top 3 diagnoses
        clean = dx.strip().lower()
        terms.append(f'"{clean}"[Title/Abstract]')

    if free_text:
        # Extract key medical terms from the question (simple heuristic)
        stop = {"what", "is", "the", "for", "a", "an", "of", "in", "and", "or",
                "how", "does", "should", "which", "when", "are", "this", "with"}
        words = [w.lower() for w in free_text.split() if w.lower() not in stop and len(w) > 3]
        if words:
            terms.append(f'"{" ".join(words[:4])}"[Title/Abstract]')

    base = " OR ".join(terms) if terms else ""
    quality = '("randomized controlled trial"[pt] OR "systematic review"[pt] OR "meta-analysis"[pt] OR "clinical guideline"[pt])'
    date_filter = '"2022/01/01"[PDAT]:  "3000"[PDAT]'
    return f"({base}) AND {quality} AND ({date_filter})"


def _search_pmids(query: str) -> list[str]:
    """Call esearch → return list of PMIDs."""
    try:
        time.sleep(_RATE_LIMIT_SEC)
        r = httpx.get(
            f"{_PUBMED_BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": _MAX_RESULTS,
                    "sort": "relevance", "retmode": "json"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as exc:
        log.warning("[research] esearch failed: %s", exc)
        return []


def _fetch_abstracts(pmids: list[str]) -> list[dict[str, Any]]:
    """Call efetch → parse XML → return abstract dicts."""
    if not pmids:
        return []
    try:
        time.sleep(_RATE_LIMIT_SEC)
        r = httpx.get(
            f"{_PUBMED_BASE}/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids),
                    "rettype": "abstract", "retmode": "xml"},
            timeout=15,
        )
        r.raise_for_status()
    except Exception as exc:
        log.warning("[research] efetch failed: %s", exc)
        return []

    papers: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            title_el = article.find(".//ArticleTitle")
            abstract_el = article.find(".//AbstractText")
            journal_el = article.find(".//ISOAbbreviation")
            year_el = article.find(".//PubDate/Year")
            doi_el = article.find(".//ArticleId[@IdType='doi']")

            pmid     = pmid_el.text if pmid_el is not None else ""
            title    = title_el.text or "" if title_el is not None else ""
            abstract = abstract_el.text or "" if abstract_el is not None else ""
            journal  = journal_el.text or "" if journal_el is not None else ""
            year     = year_el.text or "" if year_el is not None else ""
            doi      = doi_el.text or "" if doi_el is not None else ""

            if not abstract:
                continue

            papers.append({
                "pmid": pmid, "title": title, "abstract": abstract,
                "journal": journal, "year": year, "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })
    except ET.ParseError as exc:
        log.error("[research] XML parse error: %s", exc)

    return papers


def fetch_pubmed(
    patient_id: str,
    diagnoses: list[str],
    question: str = "",
) -> list[dict[str, Any]]:
    """
    Fetch PubMed abstracts relevant to the patient's diagnoses.
    Results are embedded into Qdrant and cached for 1 hour.
    Returns list of paper metadata dicts.
    """
    query = _build_query(diagnoses, question)
    if not query:
        return []

    # 1. Check persistent SQLite cache first
    cached = get_pubmed(patient_id, query)
    if cached is not None:
        log.info("[research] SQLite cache hit for patient %s", patient_id)
        _ensure_papers_embedded(patient_id, cached)
        return cached

    log.info("[research] Fetching PubMed: %s", query[:120])
    pmids   = _search_pmids(query)
    papers  = _fetch_abstracts(pmids)

    if papers:
        _ensure_papers_embedded(patient_id, papers)

    # 2. Save fetched papers to persistent cache
    set_pubmed(patient_id, query, papers)
    return papers


def search_research(
    patient_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search previously embedded PubMed abstracts for a patient."""
    return search_chunks(query, patient_id, top_k=top_k, doc_type="pubmed_abstract")


def _ensure_papers_embedded(patient_id: str, papers: list[dict[str, Any]]) -> int:
    chunks_to_embed: list[dict[str, Any]] = []
    chunk_counts: dict[str, int] = {}
    papers_indexed = 0

    for paper in papers:
        source_doc = f"pubmed:{paper['pmid']}"
        content_hash = hash_text(f"{paper.get('title', '')}\n{paper.get('abstract', '')}")
        if is_document_indexed(patient_id, source_doc, content_hash):
            papers_indexed += 1
            continue

        paper_chunks = chunk_text(
            text=f"{paper['title']}\n\n{paper['abstract']}",
            patient_id=patient_id,
            source_doc=source_doc,
            doc_type="pubmed_abstract",
        )
        for chunk in paper_chunks:
            chunk["pmid"] = paper["pmid"]
            chunk["doi"] = paper["doi"]
            chunk["title"] = paper["title"]
            chunk["journal"] = paper["journal"]
            chunk["year"] = paper["year"]
            chunk["url"] = paper["url"]
        chunks_to_embed.extend(paper_chunks)
        chunk_counts[source_doc] = len(paper_chunks)

    if chunks_to_embed:
        embed_chunks(chunks_to_embed)

    for paper in papers:
        source_doc = f"pubmed:{paper['pmid']}"
        content_hash = hash_text(f"{paper.get('title', '')}\n{paper.get('abstract', '')}")
        if source_doc not in chunk_counts and is_document_indexed(patient_id, source_doc, content_hash):
            continue
        mark_document_indexed(
            patient_id,
            source_doc,
            content_hash,
            chunk_count=chunk_counts.get(source_doc, 0),
        )

    if chunks_to_embed:
        log.info("[research] Embedded %d chunks from %d paper(s)", len(chunks_to_embed), len(papers))

    return papers_indexed + len(papers)


def prefetch_pubmed_background(patient_id: str, diagnoses: list[str], question: str = "") -> None:
    cache_key = f"{patient_id}:{_build_query(diagnoses, question)}"
    if not diagnoses or not cache_key.strip():
        return

    with _PREFETCH_LOCK:
        if cache_key in _INFLIGHT_PREFETCHES:
            return
        _INFLIGHT_PREFETCHES.add(cache_key)

    def _runner() -> None:
        try:
            fetch_pubmed(patient_id, diagnoses, question)
        except Exception as exc:
            log.warning("[research] background prefetch failed: %s", exc)
        finally:
            with _PREFETCH_LOCK:
                _INFLIGHT_PREFETCHES.discard(cache_key)

    thread = threading.Thread(target=_runner, name=f"pubmed-prefetch-{patient_id}", daemon=True)
    thread.start()
