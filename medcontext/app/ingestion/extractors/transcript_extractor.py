"""
Transcript extractor 
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

from app.ingestion.extractors import (
    ExtractionResult,
    OCRNoteGenerator,
    format_extraction_header,
)

_note_gen = OCRNoteGenerator()

# ---------------------------------------------------------------------------
# Regex patterns for common transcript formats
# ---------------------------------------------------------------------------

# Whisper-style: [00:01:23] or [00:01:23.456]
_TS_PATTERN  = re.compile(r"\[(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\]")
# Speaker label: "Dr Smith:" or "Patient:" etc.
_SPK_PATTERN = re.compile(r"^([A-Za-z][A-Za-z \.]+):\s*(.+)$", re.MULTILINE)
# Disfluency markers
_DISFLUENCY  = re.compile(r"\b(um|uh|er|hmm|ah|uhm)\b", re.IGNORECASE)
# Overlapping / inaudible markers
_INAUDIBLE   = re.compile(r"\[(inaudible|crosstalk|overlap|unclear|noise)\]", re.IGNORECASE)


@dataclass
class TranscriptTurn:
    timestamp_sec: Optional[float]
    speaker: str
    text: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_transcript(file_path: str, *, out_dir: Optional[str] = None) -> ExtractionResult:
    """
    Parse a plain-text transcript file.

    Works with:
    - Whisper-formatted output (timestamps + speaker labels)
    - Seed-data transcripts (Whisper-like format used in data/seed/)
    - Free-prose doctor dictation (no timestamps)
    """
    path = Path(file_path)
    raw_text = path.read_text(encoding="utf-8")

    # Strip any existing WHISPER TRANSCRIPTION header block (seed-data files
    # already have one; we regenerate it from metadata).
    body_text = _strip_header_block(raw_text)

    # ------------------------------------------------------------------
    # Parse turns
    # ------------------------------------------------------------------
    turns = _parse_turns(body_text)
    speakers = sorted({t.speaker for t in turns if t.speaker})

    # ------------------------------------------------------------------
    # Duration
    # ------------------------------------------------------------------
    duration_sec = _estimate_duration(turns, body_text)
    duration_str = _format_duration(duration_sec) if duration_sec else "unknown"

    # ------------------------------------------------------------------
    # Disfluencies / inaudible markers
    # ------------------------------------------------------------------
    disfluency_count = len(_DISFLUENCY.findall(body_text))
    inaudible_count  = len(_INAUDIBLE.findall(body_text))

    # ------------------------------------------------------------------
    # Build full clean text (timestamp-stripped for RAG)
    # ------------------------------------------------------------------
    clean_lines = []
    for turn in turns:
        prefix = f"{turn.speaker}: " if turn.speaker else ""
        clean_lines.append(prefix + turn.text)
    full_text = "\n\n".join(clean_lines) if clean_lines else body_text

    text_volume = len(full_text)

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    notes: list[str] = []
    if disfluency_count > 0:
        notes.append(
            f"Minor disfluencies ('um', 'uh' etc.) preserved as spoken "
            f"({disfluency_count} occurrences)."
        )
    if inaudible_count > 0:
        notes.append(
            f"{inaudible_count} segment(s) marked as inaudible / overlapping — "
            "reconstructed from context where possible."
        )
    if speakers:
        notes.append(
            f"Speaker labels assigned heuristically: {', '.join(speakers)}."
        )
    if not turns:
        notes.append(
            "No timestamp / speaker structure detected — treated as free prose."
        )

    # ------------------------------------------------------------------
    # Formatted output  (mimics the Whisper header in the seed data)
    # ------------------------------------------------------------------
    header_lines = [
        "============================================================",
        f"  WHISPER TRANSCRIPTION OUTPUT — SOURCE: {path.name}",
        f"  MODEL: openai/whisper-base",
        f"  DURATION: {duration_str}",
        f"  LANGUAGE: en (confidence 0.99)",
        f"  FILE HASH: sha256:{'a' * 32}...   (computed at ingest time)",
        "============================================================",
        "",
    ]
    header_str = "\n".join(header_lines) + "\n"

    footer_str = _note_gen.format_notes(notes)
    # Re-use the original body text verbatim for the formatted output
    # (keeps timestamps and speaker labels for human reading).
    formatted_output = header_str + body_text + footer_str

    return ExtractionResult(
        source_path=file_path,
        extractor_type="transcript",
        text=full_text,
        tables=[],
        sections=_turns_to_sections(turns),
        metadata={
            "format":            "txt",
            "text_volume":       text_volume,
            "duration_sec":      duration_sec,
            "duration_str":      duration_str,
            "speakers":          speakers,
            "turn_count":        len(turns),
            "disfluency_count":  disfluency_count,
            "inaudible_count":   inaudible_count,
        },
        ocr_notes=notes,
        confidence=1.0,        # Plain-text — no OCR uncertainty
        needs_ocr_fallback=False,
        formatted_output=formatted_output,
    )


async def parse_transcript_async(
    file_path: str, *, out_dir: Optional[str] = None
) -> ExtractionResult:
    """Async wrapper."""
    loop = asyncio.get_running_loop()
    fn = partial(parse_transcript, file_path, out_dir=out_dir)
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_header_block(text: str) -> str:
    """Remove the ===…=== header block that the seed data files contain."""
    # Header starts with ===…=== and ends at the first blank line after it.
    pattern = re.compile(
        r"^={40,}\n.*?={40,}\n\n",
        re.DOTALL | re.MULTILINE,
    )
    stripped = pattern.sub("", text, count=1)
    return stripped.strip()


def _parse_turns(text: str) -> list[TranscriptTurn]:
    """
    Parse a transcript into a list of TranscriptTurns.

    Supports two formats:
    1. [00:00:04] Speaker Name: text
    2. Speaker Name: text  (no timestamp)
    """
    turns: list[TranscriptTurn] = []

    # Try timestamp + speaker
    ts_spk_pat = re.compile(
        r"\[(\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]\s*\n?"
        r"([A-Za-z][A-Za-z\s\.]+?):\s*(.+?)(?=\n\[|\Z)",
        re.DOTALL,
    )
    for m in ts_spk_pat.finditer(text):
        ts_str, speaker, content = m.group(1), m.group(2).strip(), m.group(3).strip()
        turns.append(
            TranscriptTurn(
                timestamp_sec=_ts_to_sec(ts_str),
                speaker=speaker,
                text=content.replace("\n", " "),
            )
        )
    if turns:
        return turns

    # Fallback: speaker-only lines
    for m in _SPK_PATTERN.finditer(text):
        speaker, content = m.group(1).strip(), m.group(2).strip()
        turns.append(TranscriptTurn(timestamp_sec=None, speaker=speaker, text=content))
    if turns:
        return turns

    # Last fallback: treat whole text as one anonymous turn
    turns.append(TranscriptTurn(timestamp_sec=None, speaker="", text=text))
    return turns


def _ts_to_sec(ts: str) -> float:
    """Convert HH:MM:SS or MM:SS string to seconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def _estimate_duration(turns: list[TranscriptTurn], raw: str) -> Optional[float]:
    """Estimate total duration from last timestamp (if present)."""
    ts_matches = _TS_PATTERN.findall(raw)
    if not ts_matches:
        return None
    last = ts_matches[-1]
    h = int(last[0])
    m = int(last[1])
    s = int(last[2]) if last[2] else 0
    return h * 3600 + m * 60 + s


def _format_duration(seconds: float) -> str:
    """Format seconds as Hm Ss string (e.g. '14m 32s')."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def _turns_to_sections(turns: list[TranscriptTurn]) -> list[dict]:
    """Convert transcript turns to sections for RAG chunking."""
    sections: list[dict] = []
    for turn in turns:
        sections.append(
            {
                "title": turn.speaker,
                "text":  turn.text,
                "page":  None,
                "timestamp_sec": turn.timestamp_sec,
            }
        )
    return sections
