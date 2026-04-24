# TODO: Step 4 — Chunker
# Strategy 1 (sections available): chunk by Docling section, split if > 800 tokens (≈3200 chars), 200-char overlap
# Strategy 2 (fallback): RecursiveCharacterTextSplitter chunk_size=600, chunk_overlap=150
# Chunk dict: {text, source_section, page, doc_id, patient_id, chunk_index, chunk_type}
# chunk_type: "text" | "table" | "figure_caption" | "formula"
# Tables exported as Markdown (LLM-friendly), charts/figures → VLM-generated caption (searchable)
