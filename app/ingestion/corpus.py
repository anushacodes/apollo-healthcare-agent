import logging
from pathlib import Path

from app.agent.sqlite_cache import hash_text, is_document_indexed, mark_document_indexed
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_chunks_async

log = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).parent.parent.parent / "data" / "corpus"
CORPUS_NAMESPACE = "_curated_corpus"
CORPUS_DOC_TYPE = "curated_corpus"


async def index_corpus() -> int:
    """
    One-time embed of the curated corpus (data/corpus/*.md) into the shared
    namespace used for corpus retrieval. Idempotent — already-indexed files
    are skipped via the same content-hash mechanism used for patient
    document ingestion, so this is safe to call on every startup.
    Returns the number of chunks newly upserted.
    """
    if not CORPUS_DIR.exists():
        log.warning("[corpus] %s does not exist — nothing to index", CORPUS_DIR)
        return 0

    total_upserted = 0
    for path in sorted(CORPUS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue

        text = path.read_text(encoding="utf-8")
        content_hash = hash_text(text)
        if is_document_indexed(CORPUS_NAMESPACE, path.name, content_hash):
            continue

        chunks = chunk_text(text, CORPUS_NAMESPACE, path.name, doc_type=CORPUS_DOC_TYPE)
        if not chunks:
            continue

        upserted = await embed_chunks_async(chunks)
        if upserted == 0:
            # Qdrant/encoder unavailable — don't mark as indexed, so this
            # file is retried on the next startup instead of being skipped
            # forever once the dependency comes back.
            log.warning("[corpus] Skipped %s — embedding unavailable this run", path.name)
            continue

        mark_document_indexed(CORPUS_NAMESPACE, path.name, content_hash, chunk_count=len(chunks))
        total_upserted += upserted
        log.info("[corpus] Indexed %s (%d chunks)", path.name, upserted)

    return total_upserted
