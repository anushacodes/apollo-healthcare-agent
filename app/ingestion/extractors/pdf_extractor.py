from __future__ import annotations

import json
import logging
import asyncio
from functools import partial
from pathlib import Path
from typing import Optional

from docling.document_converter import DocumentConverter

from app.ingestion.extractors import (
    ExtractionResult,
    OCRNoteGenerator,
    format_extraction_header,
)

log = logging.getLogger(__name__)

OCR_THRESHOLD = 800
_MAX_CAPTION_PAGES = 3

_note_gen = OCRNoteGenerator()

# Public API
def parse_pdf(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    path = Path(file_path)
    if out_dir is None:
        out_dir = str(path.parent)

    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    base_name = path.stem
    md_text, tables, sections, page_count = _export_artefacts(doc, out_dir, base_name)

    text_volume = len(md_text)
    needs_ocr_fallback = text_volume < OCR_THRESHOLD

    full_text = md_text

    notes = _note_gen.generate(text=full_text, confidence=1.0)
    if needs_ocr_fallback:
        notes.append(
            f"Text volume below threshold ({text_volume} < {OCR_THRESHOLD} chars). "
            "Document may be scanned/handwritten — consider running image extractor."
        )

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
            "page_count": page_count,
            "format": "pdf",
            "text_volume": text_volume,
            "docling_available": True,
        },
        ocr_notes=notes,
        confidence=1.0,
        needs_ocr_fallback=needs_ocr_fallback,
        formatted_output=formatted_output,
    )

async def parse_pdf_async(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    loop = asyncio.get_running_loop()
    fn = partial(parse_pdf, file_path, out_dir=out_dir)
    return await loop.run_in_executor(None, fn)

# Internal helpers
def _export_artefacts(doc, out_dir: str, base_name: str) -> tuple[str, list[dict], list[dict], int]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    md_text = doc.export_to_markdown()
    md_file = out_path / f"{base_name}.md"
    md_file.write_text(md_text, encoding="utf-8")

    try:
        doc_dict = json.loads(doc.export_to_dict())
    except Exception:
        doc_dict = {}
    json_file = out_path / f"{base_name}.json"
    json_file.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2))

    raw_tables = doc_dict.get("tables", {})
    if isinstance(raw_tables, dict):
        raw_tables = list(raw_tables.values())

    tables: list[dict] = []
    for tbl in raw_tables:
        if not isinstance(tbl, dict):
            continue
        md_table = _table_to_markdown(tbl)
        tables.append({
            "markdown": md_table,
            "page": tbl.get("prov", [{}])[0].get("page", None) if tbl.get("prov") else None,
            "caption": tbl.get("caption", ""),
        })

    raw_body = doc_dict.get("texts", [])
    if isinstance(raw_body, dict):
        raw_body = list(raw_body.values())

    sections: list[dict] = []
    current_section: dict | None = None
    for item in raw_body:
        if not isinstance(item, dict):
            continue
        label = item.get("label", "")
        text = item.get("text", "").strip()
        page = item.get("prov", [{}])[0].get("page", None) if item.get("prov") else None

        if label in ("section_header", "title", "page_header"):
            current_section = {"title": text, "text": "", "page": page}
            sections.append(current_section)
        elif current_section is not None:
            current_section["text"] += " " + text
        else:
            sections.append({"title": "", "text": text, "page": page})

    page_count = doc_dict.get("num_pages", 0) or _count_pages(raw_body)
    return md_text, tables, sections, page_count

def _table_to_markdown(tbl: dict) -> str:
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
