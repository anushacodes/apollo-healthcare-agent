"""Extract embedded PDF text without loading document or OCR models."""
import asyncio
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ingestion.extractors import ExtractionResult


def parse_pdf(file_path: str, *, out_dir: str | None = None) -> ExtractionResult:
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            raise ValueError("This PDF is encrypted. Upload an unencrypted copy.")
        if not reader.pages or len(reader.pages) > 100:
            raise ValueError("Upload a PDF containing between 1 and 100 pages.")
        pages = [page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False)
                 for page in reader.pages]
    except PdfReadError as exc:
        raise ValueError("This PDF could not be read. Upload a valid PDF or its text export.") from exc

    if any(not page.strip() for page in pages):
        try:
            from app.ingestion.extractors.pdf_extractor import parse_pdf as parse_with_models
        except ModuleNotFoundError as exc:
            if not (exc.name or "").startswith("docling"):
                raise
            raise ValueError("This PDF contains pages without selectable text. Upload a text export, or enable the optional document models for scanned PDFs.") from exc
        return parse_with_models(file_path, out_dir=out_dir)

    text = "\n\n".join(pages)
    return ExtractionResult(
        source_path=str(Path(file_path)), extractor_type="pdf", text=text, tables=[],
        sections=[{"title": f"Page {i + 1}", "text": page, "page": i + 1} for i, page in enumerate(pages)],
        metadata={"page_count": len(pages), "format": "pdf", "parser": "pypdf", "ocr_used": False},
        ocr_notes=["Embedded PDF text was read without OCR. No OCR confidence score is available."],
        confidence=0.0, needs_ocr_fallback=False, formatted_output=text,
    )


async def parse_pdf_async(file_path: str, *, out_dir: str | None = None) -> ExtractionResult:
    return await asyncio.to_thread(parse_pdf, file_path, out_dir=out_dir)
