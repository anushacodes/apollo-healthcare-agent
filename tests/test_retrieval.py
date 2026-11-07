from unittest.mock import MagicMock

from app.agent import sqlite_cache
from app.agent.eval_agent import run_eval
from app.ingestion import embedder
from app.ingestion.chunker import chunk_text


def test_sparse_index_survives_dense_outage_and_replaces_document():
    chunks = chunk_text("Proteinuria with kidney dysfunction. " * 70, "patient", "labs.txt")
    assert embedder.embed_chunks(chunks) == 0
    assert embedder.search_chunks("proteinuria", "patient")
    assert embedder.search_chunks("proteinuria", "other") == []
    replacement = chunk_text("Normal renal function with stable laboratory values. " * 4, "patient", "labs.txt")
    embedder.embed_chunks(replacement)
    assert embedder.search_chunks("proteinuria", "patient") == []
    assert embedder.search_chunks("normal renal", "patient")


def test_dense_ids_do_not_collide_across_patients(monkeypatch):
    client = MagicMock()
    client.get_collections.return_value.collections = [MagicMock(name="apollo_documents")]
    encoder = MagicMock()
    encoder.encode.return_value.tolist.return_value = [[0.0] * 384, [0.0] * 384]
    monkeypatch.setattr(embedder, "_get_client", lambda: client)
    monkeypatch.setattr(embedder, "_get_encoder", lambda: encoder)
    text = "Identical clinical evidence shared across multiple synthetic patient records. " * 2
    chunks = chunk_text(text, "one", "labs") + chunk_text(text, "two", "labs")
    assert embedder.embed_chunks(chunks) == 2
    points = client.upsert.call_args.kwargs["points"]
    assert points[0].id != points[1].id
    assert {p.payload["patient_id"] for p in points} == {"one", "two"}


def test_eval_without_provider_is_explicitly_unverified():
    result = run_eval("question", "answer", [{"text": "evidence"}])
    assert result["skipped"] is True
    assert result["faithfulness"] == 0


def test_answer_cache_is_normalized_and_invalidated_per_patient():
    sqlite_cache.set_answer("one:fingerprint", "  QUESTION? ", {"answer": "cached"})
    sqlite_cache.set_answer("two:fingerprint", "question?", {"answer": "other"})
    assert sqlite_cache.get_answer("one:fingerprint", "question?") == {"answer": "cached"}
    sqlite_cache.mark_document_indexed("one", "labs", "hash", chunk_count=1)
    assert sqlite_cache.get_answer("one:fingerprint", "question?") is None
    assert sqlite_cache.get_answer("two:fingerprint", "question?") == {"answer": "other"}
