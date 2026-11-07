"""The numbered evidence excerpts shared by answer generation and evaluation."""

import re


class AnswerCitationError(RuntimeError):
    code = "invalid_citations"


def format_evidence(chunks: list[dict]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_doc") or chunk.get("title") or "unknown"
        # Keep the record's later sections, including labs and medications.
        limit = 12000 if chunk.get("doc_type") == "structured_summary" else 900
        text = chunk.get("text", "")[:limit]
        lines.append(f"[{i}] Source: {source}\n{text}")
    return "\n\n---\n\n".join(lines)


def citation_refs(answer: str, source_count: int) -> set[int]:
    refs = {int(ref) for ref in re.findall(r"\[(\d+)\]", answer)}
    if not refs or any(ref < 1 or ref > source_count for ref in refs):
        raise AnswerCitationError(
            "The answer could not be linked to its sources. Please try again."
        )
    return refs
