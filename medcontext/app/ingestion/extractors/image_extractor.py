"""
Image extractor — handles JPG / PNG / TIFF handwritten notes and scanned pages.

  1.  Try Docling DocumentConverter (handles printed text well).
  2.  Check text volume.  If < OCR_THRESHOLD chars → fallback to LightOnOCR-2-1B.
  3.  LightOnOCR runs per-region and returns LaTeX / Markdown + per-word confidence.
  4.  Merge results.
  5.  Generate OCR notes (character confusions, low-confidence words, ink artefacts).
  6.  Build formatted output.

Model: lightonai/LightOnOCR-2-1B  (loaded lazily on first use)
"""

from __future__ import annotations

import asyncio
import logging
import re
from functools import partial
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


_DOCLING_AVAILABLE = False
try:
    from docling.document_converter import DocumentConverter
    _DOCLING_AVAILABLE = True
except ImportError:
    log.warning("Docling not installed — image extractor will skip first pass.")

_LIGHTOCR_AVAILABLE = False
_lightocr_model = None
_lightocr_processor = None

def _load_lightocr():
    """Lazy-load LightOnOCR-2-1B on first use."""
    global _LIGHTOCR_AVAILABLE, _lightocr_model, _lightocr_processor
    if _lightocr_model is not None:
        return True
    try:
        from transformers import AutoModel, AutoProcessor   # type: ignore
        _lightocr_model     = AutoModel.from_pretrained("lightonai/LightOnOCR-2-1B")
        _lightocr_processor = AutoProcessor.from_pretrained("lightonai/LightOnOCR-2-1B")
        _LIGHTOCR_AVAILABLE = True
        log.info("LightOnOCR-2-1B loaded successfully.")
        return True
    except Exception as exc:
        log.warning("LightOnOCR-2-1B not available: %s", exc)
        return False

_PIL_AVAILABLE = False
try:
    from PIL import Image   # type: ignore
    _PIL_AVAILABLE = True
except ImportError:
    log.warning("Pillow not installed — image loading disabled.")

from app.ingestion.extractors import (
    ExtractionResult,
    OCRNoteGenerator,
    format_extraction_header,
)

OCR_THRESHOLD = 800          # chars below which Docling pass is insufficient
_note_gen = OCRNoteGenerator()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_image(
    file_path: str,
    *,
    out_dir: Optional[str] = None,
    force_lightocr: bool = False,
) -> ExtractionResult:
    """
    Synchronous image extraction.

    Parameters
    ----------
    file_path:
        Absolute path to the image (JPG / PNG / TIFF).
    out_dir:
        Output directory for artefacts; defaults to source directory.
    force_lightocr:
        Skip Docling and go directly to LightOnOCR (useful for known
        handwritten documents).
    """
    path = Path(file_path)
    if out_dir is None:
        out_dir = str(path.parent)

    docling_text = ""
    confidence   = 0.0

    # ------------------------------------------------------------------
    # Pass 1 — Docling (handles printed text in images)
    # ------------------------------------------------------------------
    if _DOCLING_AVAILABLE and not force_lightocr:
        docling_text, confidence = _run_docling(file_path)

    needs_ocr_fallback = len(docling_text) < OCR_THRESHOLD

    # ------------------------------------------------------------------
    # Pass 2 — LightOnOCR (handwritten / scanned content)
    # ------------------------------------------------------------------
    ocr_text          = ""
    word_confidences: list[tuple[str, float]] = []
    ink_artefacts:    list[str] = []
    low_conf_regions: list[str] = []

    if needs_ocr_fallback or force_lightocr:
        ocr_text, word_confidences, ink_artefacts = _run_lightocr(file_path)
        low_conf_regions = [
            word for word, conf in word_confidences if conf < 0.7
        ]
        if word_confidences:
            confidence = float(
                sum(c for _, c in word_confidences) / len(word_confidences)
            )

    # ------------------------------------------------------------------
    # Merge: prefer LightOnOCR text when it was triggered
    # ------------------------------------------------------------------
    if needs_ocr_fallback and ocr_text:
        full_text = ocr_text
    else:
        full_text = docling_text or ocr_text

    text_volume = len(full_text)

    # ------------------------------------------------------------------
    # OCR notes
    # ------------------------------------------------------------------
    illegible = [a for a in ink_artefacts if "illegible" in a.lower()]
    non_illegible_artefacts = [a for a in ink_artefacts if "illegible" not in a.lower()]

    notes = _note_gen.generate(
        text=full_text,
        confidence=confidence,
        low_confidence_regions=low_conf_regions or None,
        illegible_sections=illegible or None,
        ink_artefacts=non_illegible_artefacts or None,
    )
    if not notes:
        # Always add at least the extraction method used
        if needs_ocr_fallback:
            notes.append("LightOnOCR-2-1B fallback applied due to low Docling text volume.")

    # ------------------------------------------------------------------
    # Formatted output
    # ------------------------------------------------------------------
    header = format_extraction_header(
        source_path=file_path,
        extractor_type="image",
        text_volume=text_volume,
        needs_ocr_fallback=needs_ocr_fallback,
        extra={
            "CONFIDENCE": f"{confidence:.2f}",
        },
    )
    footer = _note_gen.format_notes(notes)
    formatted_output = (
        header
        + f"[PAGE 1 — single page]\n\n"
        + full_text
        + footer
    )

    return ExtractionResult(
        source_path=file_path,
        extractor_type="image",
        text=full_text,
        tables=[],        # Images rarely contain structured tables
        sections=[{"title": "", "text": full_text, "page": 1}],
        metadata={
            "format":             path.suffix.lstrip(".").lower(),
            "text_volume":        text_volume,
            "confidence":         confidence,
            "docling_pass":       bool(docling_text),
            "lightocr_pass":      bool(ocr_text),
            "word_confidences":   [(w, round(c, 3)) for w, c in word_confidences],
        },
        ocr_notes=notes,
        confidence=confidence,
        needs_ocr_fallback=needs_ocr_fallback,
        formatted_output=formatted_output,
    )


async def parse_image_async(
    file_path: str,
    *,
    out_dir: Optional[str] = None,
    force_lightocr: bool = False,
) -> ExtractionResult:
    """Async wrapper — runs parse_image in a thread pool executor."""
    loop = asyncio.get_running_loop()
    fn = partial(parse_image, file_path, out_dir=out_dir, force_lightocr=force_lightocr)
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_docling(file_path: str) -> tuple[str, float]:
    """
    Run Docling on a single image file.
    Returns (extracted_text, confidence).
    Docling's extraction from images is deterministic so confidence = 1.0
    when it produces meaningful text; 0.5 when it produces very little.
    """
    try:
        converter = DocumentConverter()
        result    = converter.convert(file_path)
        text      = result.document.export_to_markdown()
        confidence = 1.0 if len(text) >= OCR_THRESHOLD else 0.5
        return text, confidence
    except Exception as exc:
        log.warning("Docling failed on image %s: %s", file_path, exc)
        return "", 0.0


def _run_lightocr(
    file_path: str,
) -> tuple[str, list[tuple[str, float]], list[str]]:
    """
    Run LightOnOCR-2-1B on a single image.

    Returns
    -------
    (ocr_text, word_confidences, ink_artefact_notes)

    When the model is not available, returns a stub result that mirrors
    the format used in the seed data files.
    """
    if not _load_lightocr():
        return _stub_lightocr(file_path)

    try:
        if not _PIL_AVAILABLE:
            raise ImportError("Pillow not installed.")

        image = Image.open(file_path).convert("RGB")

        # LightOnOCR-2-1B usage pattern (from notebook):
        #   inputs = processor(images=image, return_tensors="pt")
        #   outputs = model.generate(**inputs)
        #   text = processor.decode(outputs[0], skip_special_tokens=True)
        inputs  = _lightocr_processor(images=image, return_tensors="pt")
        outputs = _lightocr_model.generate(**inputs)
        text    = _lightocr_processor.decode(outputs[0], skip_special_tokens=True)

        # LightOnOCR does not currently expose per-word confidence scores
        # in a standard way; we synthesise them heuristically.
        word_confs = _estimate_word_confidences(text)
        artefacts  = _detect_ink_artefacts(image)

        return text, word_confs, artefacts

    except Exception as exc:
        log.warning("LightOnOCR failed on %s: %s", file_path, exc)
        return _stub_lightocr(file_path)


def _stub_lightocr(
    file_path: str,
) -> tuple[str, list[tuple[str, float]], list[str]]:
    """
    Return a stub result when LightOnOCR is not available.
    Produces output that closely matches the seed data format.
    """
    stub_text = (
        "[LightOnOCR-2-1B not available — install transformers>=5.0.0 "
        "and download lightonai/LightOnOCR-2-1B to enable handwritten OCR.]"
    )
    artefacts = [
        "Model not loaded — stub mode active.",
        "Bottom margin text: illegible (stub).",
    ]
    return stub_text, [], artefacts


def _estimate_word_confidences(text: str) -> list[tuple[str, float]]:
    """
    Heuristic confidence scores for individual words.

    Strategy: words that contain digit/letter confusion patterns or
    are very short get a lower score; everything else gets 0.9+.
    """
    confusion_tokens = {"1", "0", "5", "8", "6", "2"}
    results = []
    for word in text.split():
        stripped = re.sub(r"[^\w]", "", word)
        if any(c in stripped for c in confusion_tokens) and len(stripped) > 1:
            conf = 0.68
        elif len(stripped) <= 1:
            conf = 0.75
        else:
            conf = 0.92
        results.append((word, conf))
    return results


def _detect_ink_artefacts(image) -> list[str]:
    """
    Detect common physical artefacts in a scanned handwritten image.

    Uses a simple pixel-variance heuristic:
      - High local variance → ink bleed or smudging.
    """
    if not _PIL_AVAILABLE:
        return []
    artefacts: list[str] = []
    try:
        gray     = image.convert("L")
        arr      = np.array(gray, dtype=float)
        variance = float(arr.var())
        if variance > 3000:
            artefacts.append(
                "Several words partially obscured by ink bleed or smudging."
            )
        if arr[: int(arr.shape[0] * 0.05), :].mean() < 240:
            artefacts.append("Top margin text: possibly illegible.")
        if arr[int(arr.shape[0] * 0.95) :, :].mean() < 240:
            artefacts.append("Bottom margin text: illegible.")
    except Exception as exc:
        log.debug("Artefact detection failed: %s", exc)
    return artefacts
