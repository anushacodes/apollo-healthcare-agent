#!/usr/bin/env python3
"""
warm_cache.py — Pre-warms the entire Apollo RAG cache before starting the app.

Run this ONCE before launching the server:
    uv run python scripts/warm_cache.py

What it does:
  1. Loads the sentence-transformers model once (it stays in process memory)
  2. Embeds all 3 demo patient source documents into Qdrant + SQLite FTS
  3. Fetches & embeds PubMed papers for all demo case diagnoses
  4. Runs the full RAG pipeline for every suggestion-chip question on every case
  5. Saves all answers to apollo_cache.db

After this runs, the app will:
  - Skip all embedding on first request (SQLite indexed_documents check passes)
  - Skip all PubMed HTTP calls (SQLite pubmed_cache hit)
  - Skip the entire RAG pipeline for known questions (SQLite rag_answer_cache hit)
  - Load the sentence-transformers model once at app startup (not per-request)
"""
from __future__ import annotations

import asyncio
import gc
import logging
import sys
import time
from pathlib import Path

# ── Make sure the project root is on the path ─────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("warm_cache")

# ── Suggestion chip questions (must match ask.js) ─────────────────────────
SUGGESTION_QUESTIONS = [
    "What are the key concerns for this patient?",
    "Summarise the most recent lab abnormalities.",
    "What is the current standard of care for the primary diagnosis?",
    "Are there any drug interaction risks in the current medication list?",
    "What monitoring is recommended for the current treatments?",
    "What are the latest clinical trial options for this diagnosis?",
]

# ── Extra questions worth pre-caching ─────────────────────────────────────
EXTRA_QUESTIONS = [
    "What are the EULAR recommendations for this condition?",
    "What is the prognosis for this diagnosis?",
    "Are there any relevant clinical trials the patient could enroll in?",
    "What are the target lab values to monitor for treatment response?",
    "Explain the mechanism of action of the current medications.",
]

ALL_QUESTIONS = SUGGESTION_QUESTIONS + EXTRA_QUESTIONS


# ── Phase 1: Warm the encoder (load model into memory once) ───────────────
def warm_encoder() -> None:
    log.info("Phase 1 — Loading sentence-transformers model into memory…")
    from app.ingestion.embedder import _get_encoder, _get_client
    encoder = _get_encoder()
    client  = _get_client()
    if encoder is None:
        log.error("  ✗ sentence-transformers unavailable. Is the package installed?")
        sys.exit(1)
    if client is None:
        log.warning("  ⚠ Qdrant unavailable — dense vectors will be skipped, FTS still works.")
    else:
        log.info("  ✓ Qdrant connected")
    log.info("  ✓ Encoder model loaded: %s", encoder.__class__.__name__)
    gc.collect()


# ── Phase 2: Embed patient source documents ───────────────────────────────
def warm_patient_docs() -> None:
    log.info("Phase 2 — Embedding demo patient source documents…")
    from app.agent.seed_patient import CASES
    from app.ingestion.chunker import chunk_text
    from app.ingestion.embedder import embed_chunks
    from app.agent.sqlite_cache import hash_text, is_document_indexed, mark_document_indexed

    for case_key, loader in CASES.items():
        case_data = loader()
        patient_id = case_data.get("patient_id", case_key)
        source_docs = case_data.get("source_documents", {})

        if not source_docs:
            log.info("  [%s] No source documents — skipping", case_key)
            continue

        chunks_to_embed = []
        for label, text in source_docs.items():
            if not text:
                continue
            content_hash = hash_text(text)
            if is_document_indexed(patient_id, label, content_hash):
                log.info("  [%s] ✓ %s already indexed", case_key, label)
                continue
            chunks = chunk_text(text, patient_id, label)
            chunks_to_embed.extend(chunks)
            log.info("  [%s] + queued %d chunks from %s", case_key, len(chunks), label)

        if chunks_to_embed:
            embed_chunks(chunks_to_embed)
            gc.collect()  # free encoder workspace between patients
            # Mark all successfully
            for label, text in source_docs.items():
                if not text:
                    continue
                content_hash = hash_text(text)
                if is_document_indexed(patient_id, label, content_hash):
                    continue
                count = sum(1 for c in chunks_to_embed if c["source_doc"] == label)
                mark_document_indexed(patient_id, label, content_hash, chunk_count=count)
            log.info("  [%s] ✓ Embedded %d chunks", case_key, len(chunks_to_embed))
        else:
            log.info("  [%s] ✓ All documents already indexed", case_key)

    gc.collect()


# ── Phase 3: Pre-fetch PubMed for all demo cases ─────────────────────────
def warm_pubmed() -> None:
    log.info("Phase 3 — Pre-fetching PubMed papers for all demo cases…")
    from app.agent.seed_patient import CASES
    from app.agent.research_agent import fetch_pubmed

    for case_key, loader in CASES.items():
        case_data  = loader()
        patient_id = case_data.get("patient_id", case_key)
        diagnoses  = [
            d.get("name", "") if isinstance(d, dict) else str(d)
            for d in case_data.get("summary", {}).get("diagnoses", [])
        ]
        if not diagnoses:
            log.info("  [%s] No diagnoses — skipping PubMed", case_key)
            continue

        log.info("  [%s] Fetching PubMed for: %s", case_key, diagnoses[:2])
        t0 = time.perf_counter()
        papers = fetch_pubmed(patient_id, diagnoses)
        elapsed = time.perf_counter() - t0
        log.info("  [%s] ✓ %d papers in %.1fs", case_key, len(papers), elapsed)
        gc.collect()  # free abstract embedding workspace before next case


# ── Phase 4: Pre-run RAG pipeline for all questions ───────────────────────
async def warm_rag_answers() -> None:
    log.info("Phase 4 — Pre-generating RAG answers for all suggestion questions…")
    from app.agent.seed_patient import CASES
    from app.agent.sqlite_cache import get_answer
    from app.agent.rag_agent import run_rag_streaming

    for case_key, loader in CASES.items():
        case_data  = loader()
        patient_id = case_data.get("patient_id", case_key)
        log.info("  ── Case: %s (patient_id=%s) ──", case_key, patient_id)

        for question in ALL_QUESTIONS:
            # Skip if already cached
            if get_answer(patient_id, question):
                log.info("    ✓ (cached) %s", question[:60])
                continue

            log.info("    → Running: %s", question[:70])
            t0 = time.perf_counter()
            try:
                final_data = None
                async for event in run_rag_streaming(patient_id, case_data, question):
                    if event.get("type") == "done":
                        final_data = event.get("data", {})
                elapsed = time.perf_counter() - t0
                if final_data:
                    faith = final_data.get("eval_scores", {}).get("faithfulness", "?")
                    log.info(
                        "    ✓ Done in %.1fs | faith=%s | %d citations",
                        elapsed,
                        f"{faith:.0%}" if isinstance(faith, float) else faith,
                        len(final_data.get("citations", [])),
                    )
                else:
                    log.warning("    ⚠ No done event received (%.1fs)", elapsed)
            except Exception as exc:
                log.error("    ✗ Failed for %r: %s", question[:50], exc)

            # Small pause between LLM calls to avoid rate-limit errors
            await asyncio.sleep(0.5)


# ── Phase 5: Print cache stats ────────────────────────────────────────────
def print_stats() -> None:
    from app.agent.sqlite_cache import _get_conn, DB_PATH
    log.info("Cache DB: %s", DB_PATH)
    with _get_conn() as conn:
        for table in ["pubmed_cache", "rag_answer_cache", "indexed_documents", "chunk_cache"]:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                log.info("  %-25s  %d rows", table, n)
            except Exception:
                pass


# ── Entrypoint ─────────────────────────────────────────────────────────────
async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Apollo Cache Warmer")
    parser.add_argument(
        "--answers",
        action="store_true",
        help="Also pre-generate RAG answers (slow, requires live LLM API calls). "
             "Omit for a fast, RAM-safe warmup of embeddings + PubMed only.",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Apollo Cache Warmer")
    if args.answers:
        log.info("Mode: FULL (embeddings + PubMed + RAG answers)")
    else:
        log.info("Mode: FAST (embeddings + PubMed only)")
        log.info("Tip: run with --answers to also pre-cache RAG responses.")
    log.info("=" * 60)

    total_start = time.perf_counter()

    warm_encoder()
    warm_patient_docs()
    warm_pubmed()

    if args.answers:
        await warm_rag_answers()

    log.info("=" * 60)
    print_stats()
    log.info("Done in %.1fs.", time.perf_counter() - total_start)
    log.info("Start the server: uv run uvicorn app.main:app --reload")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
