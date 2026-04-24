from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ExtractionResult:
    source_path: str
    extractor_type: str
    text: str
    tables: list[dict]
    sections: list[dict]
    metadata: dict
    ocr_notes: list[str]
    confidence: float
    needs_ocr_fallback: bool
    formatted_output: str = ""

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "extractor_type": self.extractor_type,
            "text": self.text,
            "tables": self.tables,
            "sections": self.sections,
            "metadata": self.metadata,
            "ocr_notes": self.ocr_notes,
            "confidence": self.confidence,
            "needs_ocr_fallback": self.needs_ocr_fallback,
        }

    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

class OCRNoteGenerator:
    _CHAR_PAIRS = [
        ("l", "1"), ("I", "1"), ("O", "0"), ("S", "5"),
        ("B", "8"), ("rn", "m"), ("cl", "d"), ("G", "6"), ("Z", "2"),
    ]

    _COMMON_MISREADS = {
        "unwe11": "'unwell' parsed as 'unwe11'",
        "Hartwe11": "'Hartwell' parsed as 'Hartwe11'",
        "tmrw": "'tomorrow' interpreted as 'tmrw'",
        "SOB": "Clinical abbreviation 'SOB' (shortness of breath) preserved",
        "c/o": "Abbreviation 'c/o' (complaining of) detected",
        "O/E": "Abbreviation 'O/E' (on examination) detected",
    }

    def generate(
        self,
        text: str,
        confidence: float,
        low_confidence_regions: Optional[list[str]] = None,
        illegible_sections: Optional[list[str]] = None,
        ink_artefacts: Optional[list[str]] = None,
    ) -> list[str]:
        notes: list[str] = []

        if ink_artefacts:
            notes.extend(ink_artefacts)

        for token, description in self._COMMON_MISREADS.items():
            if token in text:
                notes.append(description)

        found_confusions: list[str] = []
        for real_char, ocr_char in self._CHAR_PAIRS:
            if re.search(re.escape(ocr_char), text) and not re.search(re.escape(real_char), text):
                found_confusions.append(f"Character '{real_char}' may have been parsed as '{ocr_char}' in some locations")
        if found_confusions:
            notes.extend(found_confusions)

        if low_confidence_regions:
            for region in low_confidence_regions:
                notes.append(f"Low-confidence region: '{region}'")

        if illegible_sections:
            notes.extend(illegible_sections)

        if confidence < 0.7:
            notes.append(f"Overall OCR confidence is low ({confidence:.2f}). Manual review recommended.")
        elif confidence < 0.85:
            notes.append(f"Overall OCR confidence is moderate ({confidence:.2f}). Some words may have been misread.")

        return notes

    def format_notes(self, notes: list[str]) -> str:
        if not notes:
            return ""
        lines = "\n ".join(notes)
        return f"\n--- [end of content] ---\n\n[OCR NOTE: {lines}]\n"

def format_extraction_header(
    source_path: str,
    extractor_type: str,
    text_volume: int,
    needs_ocr_fallback: bool,
    extra: Optional[dict] = None,
) -> str:
    type_label = {
        "pdf": "DocumentConverter (typed document)",
        "image": "LightOnOCR-2-1B  (handwritten / image content)",
        "transcript": "Whisper transcript (plain-text import)",
    }.get(extractor_type, extractor_type)

    volume_note = f"{text_volume} chars  →  {'⚠ OCR fallback applied' if needs_ocr_fallback else '✓ sufficient'}"
    
    extra_lines = ""
    if extra:
        for k, v in extra.items():
            extra_lines += f"\n  {k}: {v}"

    return (
        "============================================================\n"
        f"  DOCLING EXTRACTION OUTPUT — SOURCE: {Path(source_path).name}\n"
        f"  FORMAT: {type_label}\n"
        f"  TEXT VOLUME: {volume_note}"
        f"{extra_lines}\n"
        "============================================================\n\n"
    )
