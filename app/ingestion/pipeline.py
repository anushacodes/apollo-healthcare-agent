# TODO: Step 4 — Ingestion orchestration pipeline
# async run_ingestion_pipeline(document_id: str):
#   1. Load doc record from DB
#   2. Parse (parser.py) — wrapped in run_in_executor
#   3. Set status → 'processing'
#   4. If needs_ocr_fallback → run LightOnOCR-2-1B (also in executor)
#   5. Chunk (chunker.py)
#   6. Embed (embedder.py)
#   7. Set status → 'done'
#   8. Invalidate summary_cache for this patient
#   9. asyncio.create_task(run_research_agent(...))  [skipped in DEV_MODE]
#   On exception: set status → 'error', log full traceback
