import importlib
import logging
from pathlib import Path

from app.ingestion.extractors import ExtractionResult

log = logging.getLogger(__name__)

# Resolve only the selected extractor: plain text must not import Torch/Docling.
_HANDLERS = {
    ".pdf": ("pdf_extractor", "parse_pdf"),
    ".docx": ("pdf_extractor", "parse_pdf"),
    ".doc": ("pdf_extractor", "parse_pdf"),
    ".jpg": ("image_extractor", "parse_image"),
    ".jpeg": ("image_extractor", "parse_image"),
    ".png": ("image_extractor", "parse_image"),
    ".tiff": ("image_extractor", "parse_image"),
    ".tif": ("image_extractor", "parse_image"),
    ".txt": ("transcript_extractor", "parse_transcript"),
}


def _handler(file_path: str, *, asynchronous: bool = False):
    ext = Path(file_path).suffix.lower()
    if ext not in _HANDLERS:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {sorted(_HANDLERS)}")
    module, function = _HANDLERS[ext]
    imported = importlib.import_module(f"app.ingestion.extractors.{module}")
    return getattr(imported, function + ("_async" if asynchronous else ""))


def parse_document(file_path: str, *, out_dir: str | None = None) -> ExtractionResult:
    return _handler(file_path)(file_path, out_dir=out_dir)


async def parse_document_async(file_path: str, *, out_dir: str | None = None) -> ExtractionResult:
    return await _handler(file_path, asynchronous=True)(file_path, out_dir=out_dir)


def is_supported(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in _HANDLERS


def supported_extensions() -> list[str]:
    return sorted(_HANDLERS)
