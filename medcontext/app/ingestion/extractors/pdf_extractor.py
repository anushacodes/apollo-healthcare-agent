"""
PDF extractor — wraps Docling's DocumentConverter.

Pipeline:
  1.  Run Docling DocumentConverter  →  structured document object
  2.  Export to Markdown + JSON
  3.  Extract sections, tables (as Markdown), figure captions (via VLM if GPU available)
  4.  Check text volume; flag needs_ocr_fallback if < OCR_THRESHOLD chars
  5.  Generate OCR notes
  6.  Build formatted output string (matches seed-data style)
"""

from __future__ import annotations

import json
import logging
import asyncio
from functools import partial
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Docling imports (lazy — expensive to import at module level)
# ---------------------------------------------------------------------------
_DOCLING_AVAILABLE = False
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    _DOCLING_AVAILABLE = True
except ImportError:
    log.warning("Docling not installed — PDF extractor will run in stub mode.")

# ---------------------------------------------------------------------------
# PyMuPDF for page-preview rendering
# ---------------------------------------------------------------------------
_FITZ_AVAILABLE = False
try:
    import fitz  # type: ignore  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    log.warning("PyMuPDF not installed — page previews disabled.")

from app.ingestion.extractors import (
    ExtractionResult,
    OCRNoteGenerator,
    format_extraction_header,
)

# Minimum chars below which we consider the PDF hand-written / scanned
OCR_THRESHOLD = 800
# Maximum chars per page-preview image (sent to VLM for figure captions)
_MAX_CAPTION_PAGES = 3

_note_gen = OCRNoteGenerator()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    """
    Synchronous PDF extraction.

    Parameters
    ----------
    file_path:
        Absolute path to the PDF file.
    out_dir:
        Directory in which to write Markdown / JSON artefacts.
        Defaults to the same directory as the source file.

    Returns
    -------
    ExtractionResult
    """
    path = Path(file_path)
    if out_dir is None:
        out_dir = str(path.parent)

    if not _DOCLING_AVAILABLE:
        return _stub_result(file_path)

    # ------------------------------------------------------------------
    # 1.  Run Docling
    # ------------------------------------------------------------------
    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    # ------------------------------------------------------------------
    # 2.  Export artefacts
    # ------------------------------------------------------------------
    base_name = path.stem
    md_text, tables, sections, page_count = _export_artefacts(
        doc, out_dir, base_name
    )

    # ------------------------------------------------------------------
    # 3.  Figure captions (Qwen3-VL if GPU; stub otherwise)
    # ------------------------------------------------------------------
    figure_captions = _generate_figure_captions(str(path), page_count)

    # ------------------------------------------------------------------
    # 4.  Text volume & OCR flag
    # ------------------------------------------------------------------
    text_volume = len(md_text)
    needs_ocr_fallback = text_volume < OCR_THRESHOLD

    # ------------------------------------------------------------------
    # 5.  Assemble full text block
    # ------------------------------------------------------------------
    full_text_parts = [md_text]
    if figure_captions:
        full_text_parts.append("\n\n--- FIGURE CAPTIONS (VLM-generated) ---\n")
        full_text_parts.extend(
            f"[Page {p}: {cap}]" for p, cap in figure_captions.items()
        )
    full_text = "\n".join(full_text_parts)

    # ------------------------------------------------------------------
    # 6.  OCR notes
    # ------------------------------------------------------------------
    notes = _note_gen.generate(
        text=full_text,
        confidence=1.0,          # PDF text extraction is deterministic
    )
    if needs_ocr_fallback:
        notes.append(
            f"Text volume below threshold ({text_volume} < {OCR_THRESHOLD} chars). "
            "Document may be scanned/handwritten — consider running image extractor."
        )

    # ------------------------------------------------------------------
    # 7.  Build formatted output
    # ------------------------------------------------------------------
    header = format_extraction_header(
        source_path=file_path,
        extractor_type="pdf",
        text_volume=text_volume,
        needs_ocr_fallback=needs_ocr_fallback,
        extra={
            "TABLES DETECTED": f"{len(tables)}  (exported as Markdown)",
            "SECTIONS DETECTED": str(len(sections)),
            "PAGES": str(page_count),
        },
    )
    footer = _note_gen.format_notes(notes)
    formatted_output = header + full_text + footer

    return ExtractionResult(
        source_path=file_path,
        extractor_type="pdf",
        text=full_text,
        tables=tables,
        sections=sections,
        metadata={
            "page_count":          page_count,
            "format":              "pdf",
            "text_volume":         text_volume,
            "figure_captions":     figure_captions,
            "docling_available":   True,
        },
        ocr_notes=notes,
        confidence=1.0,
        needs_ocr_fallback=needs_ocr_fallback,
        formatted_output=formatted_output,
    )


async def parse_pdf_async(
    file_path: str, *, out_dir: Optional[str] = None
) -> ExtractionResult:
    """
    Async wrapper — runs parse_pdf in a thread pool so it does not
    block the FastAPI event loop.  Docling is CPU-bound and synchronous.
    """
    loop = asyncio.get_running_loop()
    fn = partial(parse_pdf, file_path, out_dir=out_dir)
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _export_artefacts(
    doc, out_dir: str, base_name: str
) -> tuple[str, list[dict], list[dict], int]:
    """
    Mirror of the notebook's export_artifacts() function.

    Returns (markdown_text, tables, sections, page_count).
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # --- Markdown export ---
    md_text = doc.export_to_markdown()
    md_file = out_path / f"{base_name}.md"
    md_file.write_text(md_text, encoding="utf-8")

    # --- JSON export ---
    try:
        doc_dict = json.loads(doc.export_to_dict())
    except Exception:
        doc_dict = {}
    json_file = out_path / f"{base_name}.json"
    json_file.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2))

    # --- Parse tables ---
    raw_tables = doc_dict.get("tables", {})
    if isinstance(raw_tables, dict):
        raw_tables = list(raw_tables.values())

    tables: list[dict] = []
    for tbl in raw_tables:
        if not isinstance(tbl, dict):
            continue
        # Docling encodes tables as grid; convert to Markdown
        md_table = _table_to_markdown(tbl)
        tables.append(
            {
                "markdown": md_table,
                "page":     tbl.get("prov", [{}])[0].get("page", None) if tbl.get("prov") else None,
                "caption":  tbl.get("caption", ""),
            }
        )

    # --- Parse sections ---
    raw_body = doc_dict.get("texts", [])
    if isinstance(raw_body, dict):
        raw_body = list(raw_body.values())

    sections: list[dict] = []
    current_section: dict | None = None
    for item in raw_body:
        if not isinstance(item, dict):
            continue
        label = item.get("label", "")
        text  = item.get("text", "").strip()
        page  = (
            item.get("prov", [{}])[0].get("page", None)
            if item.get("prov")
            else None
        )
        if label in ("section_header", "title", "page_header"):
            current_section = {"title": text, "text": "", "page": page}
            sections.append(current_section)
        elif current_section is not None:
            current_section["text"] += " " + text
        else:
            # Text before any section header
            sections.append({"title": "", "text": text, "page": page})

    # --- Page count ---
    page_count = doc_dict.get("num_pages", 0) or _count_pages(raw_body)

    return md_text, tables, sections, page_count


def _table_to_markdown(tbl: dict) -> str:
    """Convert a Docling table dict to a Markdown table string."""
    grid = tbl.get("grid", [])
    if not grid:
        return ""

    rows = []
    for row in grid:
        cells = [cell.get("text", "") for cell in row]
        rows.append("| " + " | ".join(cells) + " |")

    if len(rows) >= 2:
        header = rows[0]
        separator = "| " + " | ".join(["---"] * len(grid[0])) + " |"
        return "\n".join([header, separator] + rows[1:])
    elif rows:
        return rows[0]
    return ""


def _count_pages(body: list) -> int:
    max_page = 0
    for item in body:
        if isinstance(item, dict) and item.get("prov"):
            p = item["prov"][0].get("page", 0)
            if isinstance(p, int) and p > max_page:
                max_page = p
    return max_page


def _generate_figure_captions(pdf_path: str, page_count: int) -> dict[int, str]:
    """
    Render page previews and generate captions via Qwen3-VL-2B-Instruct.

    Falls back to a placeholder caption when the model is unavailable
    (no GPU / model not downloaded).
    """
    if not _FITZ_AVAILABLE:
        return {}

    captions: dict[int, str] = {}
    pages_to_caption = list(range(1, min(page_count, _MAX_CAPTION_PAGES) + 1))

    try:
        doc = fitz.open(pdf_path)
        for page_num in pages_to_caption:
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            # Qwen3-VL caption generation would go here.
            # Placeholder until the model is loaded:
            captions[page_num] = (
                "[Figure: page preview — VLM caption not generated "
                "(model not loaded)]"
            )
        doc.close()
    except Exception as exc:
        log.warning("Figure caption generation failed: %s", exc)

    return captions


def _stub_result(file_path: str) -> ExtractionResult:
    """Return a minimal result when Docling is not installed."""
    header = format_extraction_header(
        source_path=file_path,
        extractor_type="pdf",
        text_volume=0,
        needs_ocr_fallback=True,
        extra={"WARNING": "Docling not installed — stub result"},
    )
    return ExtractionResult(
        source_path=file_path,
        extractor_type="pdf",
        text="[Docling not available — install with: pip install docling]",
        tables=[],
        sections=[],
        metadata={"docling_available": False},
        ocr_notes=["Docling not installed. Install it to enable PDF extraction."],
        confidence=0.0,
        needs_ocr_fallback=True,
        formatted_output=header + "[Docling not available]\n",
    )
