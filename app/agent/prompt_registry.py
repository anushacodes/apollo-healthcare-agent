"""
Lightweight prompt-version registry. Each prompt tracked here can have
multiple named versions; the registry records the real eval outcome (from
`eval_agent.run_eval`) every time a version is actually used to generate an
answer, so version quality is backed by measured scores in
`prompt_eval_scores`, not a bare version string with no data behind it.

Only prompts with a real eval signal downstream are worth registering —
currently that's just the RAG generator prompt, since it's the only one
`eval_agent` scores. Diagnostics prompts (orchestrator, diagnosis, drug
interaction) have no equivalent automated quality signal yet.
"""


from app.agent.rag.prompts import _GENERATOR_PROMPT
from app.agent.sqlite_cache import get_prompt_version_stats, record_prompt_score

PROMPT_VERSIONS: dict[str, dict[str, str]] = {
    "generator": {
        "v1": _GENERATOR_PROMPT,
    },
}

ACTIVE_VERSION: dict[str, str] = {
    "generator": "v1",
}


def get_active_prompt(name: str) -> tuple[str, str]:
    """Returns (version, template) for the currently active version of a registered prompt."""
    version = ACTIVE_VERSION[name]
    return version, PROMPT_VERSIONS[name][version]


def record_eval(
    name: str,
    version: str,
    *,
    faithfulness: float | None,
    hallucination_detected: bool | None,
) -> None:
    record_prompt_score(
        name, version, faithfulness=faithfulness, hallucination_detected=hallucination_detected
    )


def get_version_stats(name: str) -> list[dict]:
    """Per-version avg faithfulness / hallucination rate / sample count for a registered prompt."""
    return get_prompt_version_stats(name)
