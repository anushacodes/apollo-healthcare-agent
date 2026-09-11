import logging
from typing import Any

from app.agent.contracts import EvalScores
from app.config import settings
from app.llm_client import call_llm_json, get_structured_groq_client

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
    if not answer or answer.strip().startswith("Generation error:") or answer.strip().startswith("No relevant sources"):
        return EvalScores(
            evaluation_notes=answer or "No answer provided.",
        ).model_dump()

    if not chunks:
        return EvalScores(
            faithfulness=0.0,
            context_relevance=0.0,
            answer_completeness=0.0,
            hallucination_detected=True,
            blocked=True,
            block_reason="No source chunks were retrieved — cannot verify answer.",
            evaluation_notes="No context provided for evaluation.",
        ).model_dump()

    chunk_text = _format_chunks_for_eval(chunks)
    prompt = _EVAL_PROMPT.format(
        chunks=chunk_text,
        question=question,
        answer=answer[:2000],
    )
    messages = [
        {"role": "system", "content": _EVAL_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    result = None
    if settings.has_groq:
        try:
            client = get_structured_groq_client()
            result = client.chat.completions.create(
                model=settings.groq_eval_model,
                response_model=EvalScores,
                messages=messages,
                temperature=0.0,
                max_tokens=2048,
                reasoning_effort="low",
            )
        except Exception as exc:
            log.warning("[eval] Groq tool evaluation failed, trying JSON mode: %s", exc)

    if result is None and (settings.has_groq or settings.has_openrouter):
        try:
            raw_dict, _ = call_llm_json(messages, temperature=0.0, max_tokens=2048)
            result = EvalScores.model_validate(raw_dict)
        except Exception as exc:
            log.error("[eval] Scoring failed: %s", exc)
            return EvalScores(
                evaluation_notes=f"Eval agent unavailable: {exc}",
            ).model_dump()

    if result is None:
        return EvalScores(evaluation_notes="Eval agent unavailable.").model_dump()

    log.info(
        "[eval] faith=%.2f relevance=%.2f completeness=%.2f hallucination=%s",
        result.faithfulness,
        result.context_relevance,
        result.answer_completeness,
        result.hallucination_detected,
    )
    return result.model_dump()

