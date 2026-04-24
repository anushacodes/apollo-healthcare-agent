from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional, Callable

from app.ingestion.extractors import ExtractionResult
from app.ingestion.extractors.pdf_extractor import parse_pdf, parse_pdf_async
from app.ingestion.extractors.image_extractor import parse_image, parse_image_async
from app.ingestion.extractors.transcript_extractor import parse_transcript, parse_transcript_async

log = logging.getLogger(__name__)

_SYNC_HANDLERS: dict[str, Callable] = {
    ".pdf": parse_pdf,
    ".docx": parse_pdf,
    ".doc": parse_pdf,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".png": parse_image,
    ".tiff": parse_image,
    ".tif": parse_image,
    ".txt": parse_transcript,
}

_ASYNC_HANDLERS: dict[str, Callable] = {
    ".pdf": parse_pdf_async,
    ".docx": parse_pdf_async,
    ".doc": parse_pdf_async,
    ".jpg": parse_image_async,
    ".jpeg": parse_image_async,
    ".png": parse_image_async,
    ".tiff": parse_image_async,
    ".tif": parse_image_async,
    ".txt": parse_transcript_async,
}

# Public API
def parse_document(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    ext = Path(file_path).suffix.lower()
    handler = _SYNC_HANDLERS.get(ext)
    if handler is None:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {sorted(_SYNC_HANDLERS)}")
    log.info(f"parse_document: {file_path} → {handler.__module__}")
    return handler(file_path, out_dir=out_dir)

async def parse_document_async(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    ext = Path(file_path).suffix.lower()
    handler = _ASYNC_HANDLERS.get(ext)
    if handler is None:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {sorted(_ASYNC_HANDLERS)}")
    log.info(f"parse_document_async: {file_path} → {handler.__module__}")
    return await handler(file_path, out_dir=out_dir)

def is_supported(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in _SYNC_HANDLERS

def supported_extensions() -> list[str]:
    return sorted(_SYNC_HANDLERS.keys())
