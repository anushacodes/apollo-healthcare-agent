#!/usr/bin/env python3
"""
scripts/test_extraction.py
--------------------------
Quick smoke-test that runs the extraction pipeline against all seed-data files
and prints the formatted output + OCR notes for each.

Run from the medcontext/ root:
    python scripts/test_extraction.py
"""

import sys
import os
from pathlib import Path

# Make sure the app package is importable when run from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.parser import parse_document, supported_extensions

SEED_DIR = Path(__file__).parent.parent / "data" / "seed"

TARGET_FILES = [
    "james_hartwell_handwritten_note_1.txt",  # simulated OCR output → transcript
    "james_hartwell_handwritten_note_2.txt",
    "james_hartwell_clinical_report.txt",
    "james_hartwell_labs.txt",
    "james_hartwell_xray_report.txt",
    "james_hartwell_transcript.txt",
]


def main() -> None:
    print(f"Supported extensions: {supported_extensions()}\n")
    print("=" * 70)

    for fname in TARGET_FILES:
        fpath = SEED_DIR / fname
        if not fpath.exists():
            print(f"[SKIP] {fname} — file not found at {fpath}")
            continue

        print(f"\n{'=' * 70}")
        print(f"  FILE: {fname}")
        print(f"{'=' * 70}")

        try:
            result = parse_document(str(fpath))
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            continue

        print(f"  Extractor type : {result.extractor_type}")
        print(f"  Text volume    : {result.metadata.get('text_volume', '?')} chars")
        print(f"  Confidence     : {result.confidence:.2f}")
        print(f"  Needs OCR FB   : {result.needs_ocr_fallback}")
        print(f"  Sections       : {len(result.sections)}")
        print(f"  Tables         : {len(result.tables)}")

        if result.ocr_notes:
            print(f"\n  OCR Notes:")
            for note in result.ocr_notes:
                print(f"    • {note}")

        print(f"\n  --- First 500 chars of extracted text ---")
        print(result.text[:500])
        print("  ...")

    print(f"\n{'=' * 70}")
    print("Extraction smoke-test complete.")


if __name__ == "__main__":
    main()
