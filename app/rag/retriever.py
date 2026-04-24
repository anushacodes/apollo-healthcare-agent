# TODO: Step 6 — Hybrid retrieval with Reciprocal Rank Fusion
# retrieve(patient_id, query, top_k=5):
#   1. Dense: embed query → Qdrant search `patient_{patient_id}`, top 20
#   2. Sparse: BM25 over chunk texts (cached per patient, invalidated on new doc)
#   3. RRF fusion (k=60) → top 5 chunks + source metadata
#
# retrieve_research(patient_id, query, top_k=3):
#   Same but searches `research_{patient_id}` collection
#
# Reranking with Qwen3-VL-Reranker-2B (from notebook) before returning top_k.
