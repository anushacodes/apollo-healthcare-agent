from __future__ import annotations

import asyncio
import logging
import re
from functools import partial
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from transformers import AutoModel, AutoProcessor
from docling.document_converter import DocumentConverter

from app.ingestion.extractors import (
    ExtractionResult,
    OCRNoteGenerator,
    format_extraction_header,
)

log = logging.getLogger(__name__)

OCR_THRESHOLD = 800

_note_gen = OCRNoteGenerator()
_lightocr_model = None
_lightocr_processor = None

def _load_lightocr():
    global _lightocr_model, _lightocr_processor
    if _lightocr_model is None:
        try:
            _lightocr_model = AutoModel.from_pretrained("lightonai/LightOnOCR-2-1B")
            _lightocr_processor = AutoProcessor.from_pretrained("lightonai/LightOnOCR-2-1B")
            log.info("LightOnOCR-2-1B loaded.")
        except Exception as exc:
            log.warning(f"LightOnOCR-2-1B not available: {exc}")
            return False
    return True

# Public API
def parse_image(
    file_path: str,
    *,
    out_dir: Optional[str] = None,
    force_lightocr: bool = False,
) -> ExtractionResult:
    path = Path(file_path)
    if out_dir is None:
        out_dir = str(path.parent)

    docling_text = ""
    confidence = 0.0

    if not force_lightocr:
        docling_text, confidence = _run_docling(file_path)

    needs_ocr_fallback = len(docling_text) < OCR_THRESHOLD
    ocr_text = ""
    word_confidences: list[tuple[str, float]] = []
    ink_artefacts: list[str] = []
    low_conf_regions: list[str] = []

    if needs_ocr_fallback or force_lightocr:
        ocr_text, word_confidences, ink_artefacts = _run_lightocr(file_path)
        low_conf_regions = [word for word, conf in word_confidences if conf < 0.7]
        if word_confidences:
            confidence = float(sum(c for _, c in word_confidences) / len(word_confidences))

    full_text = ocr_text if (needs_ocr_fallback and ocr_text) else (docling_text or ocr_text)
    text_volume = len(full_text)

    illegible = [a for a in ink_artefacts if "illegible" in a.lower()]
    non_illegible_artefacts = [a for a in ink_artefacts if "illegible" not in a.lower()]

    notes = _note_gen.generate(
        text=full_text,
        confidence=confidence,
        low_confidence_regions=low_conf_regions or None,
        illegible_sections=illegible or None,
        ink_artefacts=non_illegible_artefacts or None,
    )
    if not notes and needs_ocr_fallback:
        notes.append("LightOnOCR-2-1B fallback applied due to low Docling text volume.")

    header = format_extraction_header(
        source_path=file_path,
        extractor_type="image",
        text_volume=text_volume,
        needs_ocr_fallback=needs_ocr_fallback,
        extra={"CONFIDENCE": f"{confidence:.2f}"},
    )
    footer = _note_gen.format_notes(notes)
    formatted_output = header + "[PAGE 1 — single page]\n\n" + full_text + footer

    return ExtractionResult(
        source_path=file_path,
        extractor_type="image",
        text=full_text,
        tables=[],
        sections=[{"title": "", "text": full_text, "page": 1}],
        metadata={
            "format": path.suffix.lstrip(".").lower(),
            "text_volume": text_volume,
            "confidence": confidence,
            "docling_pass": bool(docling_text),
            "lightocr_pass": bool(ocr_text),
            "word_confidences": [(w, round(c, 3)) for w, c in word_confidences],
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
    loop = asyncio.get_running_loop()
    fn = partial(parse_image, file_path, out_dir=out_dir, force_lightocr=force_lightocr)
    return await loop.run_in_executor(None, fn)

# Internal helpers
def _run_docling(file_path: str) -> tuple[str, float]:
    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        text = result.document.export_to_markdown()
        confidence = 1.0 if len(text) >= OCR_THRESHOLD else 0.5
        return text, confidence
    except Exception as exc:
        log.warning(f"Docling failed on image {file_path}: {exc}")
        return "", 0.0

def _run_lightocr(file_path: str) -> tuple[str, list[tuple[str, float]], list[str]]:
    if not _load_lightocr():
        return _stub_lightocr(file_path)

    try:
        image = Image.open(file_path).convert("RGB")
        inputs = _lightocr_processor(images=image, return_tensors="pt")
        outputs = _lightocr_model.generate(**inputs)
        text = _lightocr_processor.decode(outputs[0], skip_special_tokens=True)

        word_confs = _estimate_word_confidences(text)
        artefacts = _detect_ink_artefacts(image)

        return text, word_confs, artefacts
    except Exception as exc:
        log.warning(f"LightOnOCR failed on {file_path}: {exc}")
        return _stub_lightocr(file_path)

def _stub_lightocr(file_path: str) -> tuple[str, list[tuple[str, float]], list[str]]:
    stub_text = "[LightOnOCR-2-1B not available — install transformers>=5.0.0 and download lightonai/LightOnOCR-2-1B to enable handwritten OCR.]"
    artefacts = ["Model not loaded — stub mode active.", "Bottom margin text: illegible (stub)."]
    return stub_text, [], artefacts

def _estimate_word_confidences(text: str) -> list[tuple[str, float]]:
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
    artefacts: list[str] = []
    try:
        gray = image.convert("L")
        arr = np.array(gray, dtype=float)
        variance = float(arr.var())
        if variance > 3000:
            artefacts.append("Several words partially obscured by ink bleed or smudging.")
        if arr[: int(arr.shape[0] * 0.05), :].mean() < 240:
            artefacts.append("Top margin text: possibly illegible.")
        if arr[int(arr.shape[0] * 0.95) :, :].mean() < 240:
            artefacts.append("Bottom margin text: illegible.")
    except Exception as exc:
        log.debug(f"Artefact detection failed: {exc}")
    return artefacts
