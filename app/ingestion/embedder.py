# TODO: Step 4 — Embedder
# Uses Qwen3-VL-Embedding-2B (from notebook) for multimodal embeddings.
# Falls back to a local sentence-transformers model if GPU unavailable.
# Embedding cache: SHA-256 hash → SQLite embedding_cache table (avoids duplicate API/model calls).
# Upserts to Qdrant collection named `patient_{patient_id}` (cosine, 1536 dims).
# Batch upserts in groups of 100.
# Point payload: {text, doc_id, patient_id, source_section, page, chunk_index, chunk_type}
