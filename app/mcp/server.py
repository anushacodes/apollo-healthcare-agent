from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from app.ingestion.corpus import CORPUS_DOC_TYPE, CORPUS_NAMESPACE
from app.ingestion.embedder import search_chunks_async

log = logging.getLogger(__name__)

mcp = FastMCP(name="apollo-corpus")


@mcp.tool
async def search_clinical_guidelines(query: str, top_k: int = 6) -> list[dict[str, Any]]:
    """
    Search Apollo's curated clinical guideline corpus for chunks relevant to
    a clinical question. Returns the matching chunks (text, source document,
    relevance score) — not live medical advice, just retrieval over a fixed
    set of reference documents.
    """
    results = await search_chunks_async(query, CORPUS_NAMESPACE, top_k=top_k, doc_type=CORPUS_DOC_TYPE)
    log.info("[mcp] search_clinical_guidelines(%r) -> %d chunks", query, len(results))
    return results
