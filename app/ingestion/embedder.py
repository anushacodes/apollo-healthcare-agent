from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams,
    PointStruct, Filter, FieldCondition, MatchValue,
)

from app.config import settings

log = logging.getLogger(__name__)

# Embedding dims for BAAI/bge-small-en-v1.5 (free, local, no GPU needed)
_EMBED_DIM   = 384
_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_COLLECTION  = "apollo_documents"

_client: QdrantClient | None = None
_encoder = None  # lazy-loaded SentenceTransformer


def _get_client() -> QdrantClient | None:
    global _client
    if _client is not None:
        return _client
    try:
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_url.lower().startswith("https") else None,
            timeout=5,
        )
        _client.get_collections()   # connectivity check
        log.info("[embedder] Qdrant connected at %s", settings.qdrant_url)
    except Exception as exc:
        log.warning("[embedder] Qdrant unavailable (%s) — embedding skipped", exc)
        _client = None
    return _client


def _get_encoder():
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(_EMBED_MODEL)
        log.info("[embedder] Loaded model %s", _EMBED_MODEL)
    except Exception as exc:
        log.warning("[embedder] sentence-transformers unavailable: %s", exc)
        _encoder = None
    return _encoder


def _ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if _COLLECTION not in existing:
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=VectorParams(size=_EMBED_DIM, distance=Distance.COSINE),
        )
        log.info("[embedder] Created Qdrant collection '%s'", _COLLECTION)


def _chunk_id(text: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, text))


def embed_chunks(chunks: list[dict[str, Any]]) -> int:
    """
    Embed chunk dicts and upsert into Qdrant using small micro-batches.
    Encodes 16 chunks at a time so peak RAM stays ~150MB (bge-small) instead
    of exploding to 1-2 GB when processing 200+ chunks in one shot.
    Also mirrors each micro-batch into SQLite FTS5 immediately.
    Returns the number of chunks successfully upserted.
    """
    from app.agent.sqlite_cache import upsert_chunk_records  # avoid circular at module level

    client = _get_client()
    encoder = _get_encoder()
    if client is None or encoder is None:
        log.warning("[embedder] Skipping embed — Qdrant or encoder unavailable")
        return 0

    _ensure_collection(client)

    ENCODE_BATCH = 16   # keeps peak RAM flat; each batch GC'd before next
    UPSERT_BATCH = 50
    upserted = 0

    for i in range(0, len(chunks), ENCODE_BATCH):
        batch = chunks[i: i + ENCODE_BATCH]
        texts = [c["text"] for c in batch]
        try:
            vectors = encoder.encode(texts, batch_size=ENCODE_BATCH, show_progress_bar=False).tolist()
        except Exception as exc:
            log.error("[embedder] Encoding batch %d failed: %s", i // ENCODE_BATCH, exc)
            continue

        points = [
            PointStruct(
                id=_chunk_id(c["text"]),
                vector=vec,
                payload={
                    "chunk_id":    c["chunk_id"],
                    "patient_id":  c["patient_id"],
                    "source_doc":  c["source_doc"],
                    "doc_type":    c["doc_type"],
                    "page":        c.get("page", 1),
                    "chunk_index": c.get("chunk_index", 0),
                    "text":        c["text"],
                },
            )
            for c, vec in zip(batch, vectors)
        ]

        for j in range(0, len(points), UPSERT_BATCH):
            try:
                client.upsert(collection_name=_COLLECTION, points=points[j: j + UPSERT_BATCH])
                upserted += len(points[j: j + UPSERT_BATCH])
            except Exception as exc:
                log.error("[embedder] Upsert failed at i=%d j=%d: %s", i, j, exc)

        # Mirror to SQLite FTS before next batch (keeps memory flat)
        upsert_chunk_records(batch)
        del vectors, points  # free memory before next iteration

    log.info("[embedder] Upserted %d/%d chunks for patient %s",
             upserted, len(chunks), chunks[0]["patient_id"] if chunks else "?")
    return upserted


async def embed_chunks_async(chunks: list[dict[str, Any]]) -> int:
    """Non-blocking wrapper — runs embed_chunks in a thread pool."""
    return await asyncio.to_thread(embed_chunks, chunks)


def search_chunks(
    query: str,
    patient_id: str,
    top_k: int = 8,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Hybrid search: dense vectors (Qdrant) + sparse BM25 (SQLite FTS5), fused with RRF.
    SQLite FTS5 replaces the expensive in-memory rank_bm25 rebuild — it's persisted,
    Porter-stemmed, and returns BM25 scores with zero network calls.
    """
    from app.agent.sqlite_cache import search_chunk_records  # avoid circular at module level

    client = _get_client()
    encoder = _get_encoder()

    rrf_k = 60
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    # ── 1. Dense path (Qdrant) ─────────────────────────────────────────────
    if client is not None and encoder is not None:
        try:
            vec = encoder.encode([query], show_progress_bar=False)[0].tolist()
            must = [FieldCondition(key="patient_id", match=MatchValue(value=patient_id))]
            if doc_type:
                must.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))
            dense_results = client.query_points(
                collection_name=_COLLECTION,
                query=vec,
                query_filter=Filter(must=must),
                limit=60,
                with_payload=True,
            ).points
            for rank, p in enumerate(dense_results):
                cid = p.payload["chunk_id"]
                chunk_map[cid] = p.payload
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
        except Exception as exc:
            log.error("[embedder] Dense search failed: %s", exc)

    # ── 2. Sparse path (SQLite FTS5 BM25 — instant, no network, no rebuild) ─
    try:
        fts_rows = search_chunk_records(query, patient_id, doc_type=doc_type, limit=60)
        for rank, row in enumerate(fts_rows):
            cid = row["chunk_id"]
            if cid not in chunk_map:
                chunk_map[cid] = row
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
    except Exception as exc:
        log.error("[embedder] FTS sparse search failed: %s", exc)

    if not scores:
        return []

    # ── 3. Reciprocal Rank Fusion merge ────────────────────────────────────
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"score": score, **chunk_map[cid]} for cid, score in fused]


async def search_chunks_async(
    query: str,
    patient_id: str,
    top_k: int = 8,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    """Non-blocking wrapper — runs search_chunks in a thread pool."""
    return await asyncio.to_thread(search_chunks, query, patient_id, top_k, doc_type)


def delete_patient_chunks(patient_id: str) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(
            collection_name=_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="patient_id", match=MatchValue(value=patient_id))]
            ),
        )
        log.info("[embedder] Deleted all chunks for patient %s", patient_id)
    except Exception as exc:
        log.warning("[embedder] Delete failed for %s: %s", patient_id, exc)
