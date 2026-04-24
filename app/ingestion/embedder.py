from __future__ import annotations

import hashlib
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
        _client = QdrantClient(url=settings.qdrant_url, timeout=5)
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
    """Generate a stable UUID from chunk text (Qdrant requires UUID or uint)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, text[:200]))


def embed_chunks(chunks: list[dict[str, Any]]) -> int:
    """
    Embed a list of chunk dicts and upsert into Qdrant.
    Returns the number of chunks successfully upserted.
    """
    client = _get_client()
    encoder = _get_encoder()
    if client is None or encoder is None:
        log.warning("[embedder] Skipping embed — Qdrant or encoder unavailable")
        return 0

    _ensure_collection(client)

    texts = [c["text"] for c in chunks]
    try:
        vectors = encoder.encode(texts, batch_size=32, show_progress_bar=False).tolist()
    except Exception as exc:
        log.error("[embedder] Encoding failed: %s", exc)
        return 0

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
        for c, vec in zip(chunks, vectors)
    ]

    BATCH = 100
    upserted = 0
    for i in range(0, len(points), BATCH):
        try:
            client.upsert(collection_name=_COLLECTION, points=points[i:i + BATCH])
            upserted += len(points[i:i + BATCH])
        except Exception as exc:
            log.error("[embedder] Upsert batch %d failed: %s", i // BATCH, exc)

    log.info("[embedder] Upserted %d/%d chunks for patient %s",
             upserted, len(chunks), chunks[0]["patient_id"] if chunks else "?")
    return upserted


def search_chunks(
    query: str,
    patient_id: str,
    top_k: int = 8,
    doc_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Dense vector search in Qdrant filtered by patient_id.
    Returns list of chunk payloads with a `score` field added.
    """
    client = _get_client()
    encoder = _get_encoder()
    if client is None or encoder is None:
        return []

    try:
        vec = encoder.encode([query], show_progress_bar=False)[0].tolist()
    except Exception as exc:
        log.error("[embedder] Query encoding failed: %s", exc)
        return []

    must = [FieldCondition(key="patient_id", match=MatchValue(value=patient_id))]
    if doc_type:
        must.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))

    try:
        results = client.query_points(
            collection_name=_COLLECTION,
            query=vec,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )
        return [{"score": r.score, **r.payload} for r in results.points]
    except Exception as exc:
        log.error("[embedder] Search failed: %s", exc)
        return []


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
