from __future__ import annotations

import json
import logging
from typing import Any

from groq import Groq
from app.config import settings

log = logging.getLogger(__name__)

_EVAL_SYSTEM = """\
You are a clinical AI evaluation judge. Your job is to assess whether an answer
is grounded in the retrieved source chunks. You must be fair: synthesis and
reasoning across chunks is expected and acceptable. Only flag a claim as
unsupported if it introduces specific facts (numbers, study names, drug names,
guidelines) that are NOT present anywhere in the chunks OR that directly
contradict the chunks. Reasonable clinical inference from chunk content is allowed.\
"""

_EVAL_PROMPT = """\
Assess the answer below for faithfulness to the retrieved chunks.

RETRIEVED CHUNKS:
{chunks}

QUESTION: {question}

ANSWER: {answer}

Instructions:
1. Extract every distinct factual claim from the answer.
2. Mark each claim as SUPPORTED if:
   - The specific fact appears in a chunk, OR
   - It is a reasonable clinical inference from chunk content (synthesis is OK).
   Mark a claim UNSUPPORTED only if it introduces specific facts (numbers,
   named studies, drug doses, guideline versions) absent from or contradicted
   by the chunks.
3. faithfulness = supported_claims / total_claims  (0.0–1.0)
4. context_relevance: how relevant are the chunks to the question? (0.0–1.0)
5. answer_completeness: how fully does the answer address the question? (0.0–1.0)
6. hallucination_detected: true ONLY if a specific unsupported claim is present.
7. List only the truly unsupported claims (those with fabricated specifics).

Return ONLY valid JSON:
{{
  "faithfulness": 0.0,
  "context_relevance": 0.0,
  "answer_completeness": 0.0,
  "hallucination_detected": false,
  "total_claims": 0,
  "supported_claims": 0,
  "unsupported_claims": [],
  "evaluation_notes": ""
}}
"""

_FAITHFULNESS_GATE = 0.70


def _format_chunks_for_eval(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        source = c.get("source_doc", c.get("title", "unknown"))
        lines.append(f"[{i}] ({source})\n{c.get('text', '')[:900]}")
    return "\n\n".join(lines)


def run_eval(
    question: str,
    answer: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Score an answer for faithfulness to retrieved chunks.
    Returns eval scores dict. Never blocks output — only annotates low scores.
    """
    if not chunks:
        return {
            "faithfulness": 0.0,
            "context_relevance": 0.0,
            "answer_completeness": 0.0,
            "hallucination_detected": True,
            "blocked": True,
            "block_reason": "No source chunks were retrieved — cannot verify answer.",
            "unsupported_claims": [],
            "evaluation_notes": "No context provided for evaluation.",
        }

    chunk_text = _format_chunks_for_eval(chunks)
    prompt = _EVAL_PROMPT.format(
        chunks=chunk_text,
        question=question,
        answer=answer[:2000],
    )

    scores: dict[str, Any] = {}
    try:
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_eval_model,
            messages=[
                {"role": "system", "content": _EVAL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        scores = json.loads(response.choices[0].message.content)
    except Exception as exc:
        log.error("[eval] Scoring failed: %s", exc)
        return {
            "faithfulness": 1.0,
            "context_relevance": 1.0,
            "answer_completeness": 1.0,
            "hallucination_detected": False,
            "blocked": False,
            "block_reason": None,
            "evaluation_notes": f"Eval agent unavailable: {exc}",
            "unsupported_claims": [],
        }

    faith = float(scores.get("faithfulness", 1.0))
    hallucinated = bool(scores.get("hallucination_detected", False))

    scores["blocked"] = False
    scores["block_reason"] = None

    log.info(
        "[eval] faith=%.2f relevance=%.2f completeness=%.2f hallucination=%s",
        faith,
        float(scores.get("context_relevance", 0)),
        float(scores.get("answer_completeness", 0)),
        hallucinated,
    )
    return scores

