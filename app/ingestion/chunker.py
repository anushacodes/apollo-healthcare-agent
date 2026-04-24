from __future__ import annotations

import re
import uuid
from typing import Any


_MAX_CHUNK_CHARS = 1600   # ~400 tokens
_OVERLAP_CHARS   = 320    # ~80 tokens

# Section-level header patterns (Markdown / clinical note headings)
_SECTION_RE = re.compile(
    r"(?m)^(?:#{1,3}\s.+|[A-Z][A-Z\s\/\-]{3,}:?\s*$)",
)


def _split_by_sections(text: str) -> list[str]:
    """Split on clinical section headers first, then fall back to paragraphs."""
    boundaries = [m.start() for m in _SECTION_RE.finditer(text)]
    if len(boundaries) < 2:
        # No clear headers — split on double newlines
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    sections = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        sections.append(text[start:end].strip())
    return [s for s in sections if s]


def _slide_window(text: str, max_chars: int, overlap: int) -> list[str]:
    """Fixed-size sliding window with overlap when a section is too long."""
    chunks, pos = [], 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        # Try to break on sentence boundary
        if end < len(text):
            last_period = text.rfind(".", pos, end)
            if last_period > pos + overlap:
                end = last_period + 1
        chunks.append(text[pos:end].strip())
        pos = end - overlap
    return [c for c in chunks if c]


def chunk_text(
    text: str,
    patient_id: str,
    source_doc: str,
    doc_type: str = "clinical_note",
    page: int = 1,
) -> list[dict[str, Any]]:
    """
    Split text into overlapping semantic chunks.
    Returns a list of chunk dicts ready for embedding + Qdrant upsert.
    """
    if not text or not text.strip():
        return []

    sections = _split_by_sections(text)
    raw_chunks: list[str] = []
    for section in sections:
        if len(section) <= _MAX_CHUNK_CHARS:
            raw_chunks.append(section)
        else:
            raw_chunks.extend(_slide_window(section, _MAX_CHUNK_CHARS, _OVERLAP_CHARS))

    return [
        {
            "chunk_id":   str(uuid.uuid4()),
            "patient_id": patient_id,
            "source_doc": source_doc,
            "doc_type":   doc_type,
            "page":       page,
            "chunk_index": idx,
            "text":       chunk,
            "char_count": len(chunk),
        }
        for idx, chunk in enumerate(raw_chunks)
        if chunk.strip()
    ]


def chunk_documents(
    documents: dict[str, str],
    patient_id: str,
) -> list[dict[str, Any]]:
    """
    Chunk all documents in a {doc_label: text} dict.
    Used by the ingestion pipeline to process all patient source docs at once.
    """
    all_chunks: list[dict[str, Any]] = []
    DOC_TYPE_MAP = {
        "clinical_report": "clinical_report",
        "labs":            "lab_report",
        "transcript":      "transcript",
        "xray_report":     "imaging_report",
        "handwritten":     "clinical_note",
    }
    for label, text in documents.items():
        if not text:
            continue
        doc_type = next(
            (v for k, v in DOC_TYPE_MAP.items() if k in label.lower()),
            "clinical_note",
        )
        all_chunks.extend(chunk_text(text, patient_id, label, doc_type))
    return all_chunks
