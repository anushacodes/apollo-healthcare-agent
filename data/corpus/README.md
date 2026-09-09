# Curated Corpus

A small, hand-written reference corpus used to demonstrate real retrieval
(chunking, embedding, hybrid dense+sparse search) without depending on a live
external API. Replaces the old live PubMed fetch (see docs/TASKS.md Epic 3).

## What this is — and isn't

Each document here is **original text written for this project**, not a
verbatim copy of any official guideline or publication. The content reflects
well-established, non-controversial clinical knowledge and is organized to
mirror how real clinical guidance is structured (overview, diagnostic
criteria, management, monitoring), which is what makes chunking and semantic
retrieval over it meaningful. It is a demo/showcase corpus, not a substitute
for licensed clinical decision support content or real medical literature.

## Indexing

Indexed once via `app/ingestion/corpus.py::index_corpus()`, which chunks each
file with the existing chunker and embeds it through the existing
`embed_chunks_async` pipeline, tagged with `doc_type="curated_corpus"` under a
shared namespace (not tied to any one patient). Re-running indexing is
idempotent — already-indexed files are skipped via the same content-hash
mechanism used for patient document ingestion.
