from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_chunks, search_chunks

log = logging.getLogger(__name__)

_PUBMED_BASE    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_MAX_RESULTS    = 8      # abstracts fetched per query
_CACHE_TTL_SEC  = 3600   # 1-hour cache per (patient_id, query)
_RATE_LIMIT_SEC = 0.34   # ~3 req/s (PubMed free tier)

# In-memory cache: {cache_key: (timestamp, results)}
_cache: dict[str, tuple[float, list[dict]]] = {}


def _cache_key(patient_id: str, query: str) -> str:
    return f"{patient_id}::{query.lower().strip()}"


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

    key = _cache_key(patient_id, query)
    now = time.time()
    if key in _cache:
        ts, cached = _cache[key]
        if now - ts < _CACHE_TTL_SEC:
            log.info("[research] Cache hit for patient %s", patient_id)
            return cached

    log.info("[research] Fetching PubMed: %s", query[:120])
    pmids   = _search_pmids(query)
    papers  = _fetch_abstracts(pmids)

    if papers:
        # Embed abstracts into Qdrant for hybrid retrieval
        chunks = []
        for paper in papers:
            chunks.extend(chunk_text(
                text=f"{paper['title']}\n\n{paper['abstract']}",
                patient_id=patient_id,
                source_doc=f"pubmed:{paper['pmid']}",
                doc_type="pubmed_abstract",
            ))
            # Attach full paper metadata to each chunk
            for c in chunks[-2:]:
                c["pmid"]    = paper["pmid"]
                c["doi"]     = paper["doi"]
                c["title"]   = paper["title"]
                c["journal"] = paper["journal"]
                c["year"]    = paper["year"]
                c["url"]     = paper["url"]

        embed_chunks(chunks)
        log.info("[research] Embedded %d chunks from %d papers", len(chunks), len(papers))

    _cache[key] = (now, papers)
    return papers


def search_research(
    patient_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search previously embedded PubMed abstracts for a patient."""
    return search_chunks(query, patient_id, top_k=top_k, doc_type="pubmed_abstract")
