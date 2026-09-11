import json
import logging
from functools import lru_cache
from typing import Any

import instructor
from groq import Groq
from instructor import Instructor, Mode, Provider
from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    """Shared Groq client, built once and reused everywhere. Groq's sync
    client wraps httpx.Client, which is safe to share across threads."""
    return Groq(api_key=settings.groq_api_key)


@lru_cache(maxsize=1)
def get_structured_groq_client() -> Instructor:
    """
    Groq client patched with instructor for validated, typed completions —
    pass `response_model=<a pydantic model>` to `.chat.completions.create`
    and get back a validated instance instead of a raw dict from
    `json.loads`. Uses tool-calling mode (Groq doesn't support instructor's
    plain JSON mode).
    """
    return instructor.patch(get_groq_client(), mode=Mode.TOOLS, provider=Provider.GROQ)


@lru_cache(maxsize=1)
def get_openrouter_client() -> OpenAI:
    """Shared OpenAI-compatible client configured for OpenRouter."""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key or "",
    )


def call_llm_json(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> tuple[dict[str, Any], str]:
    """
    Call the active LLM provider (Groq or OpenRouter) requesting a JSON object.
    Falls back gracefully if the primary provider fails.
    Returns (parsed_dict, provider_model_used).
    """
    providers = []
    if settings.active_llm_provider == "openrouter":
        providers = ["openrouter", "groq"]
    else:
        providers = ["groq", "openrouter"]

    last_error = None
    for prov in providers:
        if prov == "openrouter" and settings.has_openrouter:
            try:
                client = get_openrouter_client()
                resp = client.chat.completions.create(
                    model=settings.openrouter_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or "{}"
                return json.loads(content), f"openrouter/{settings.openrouter_model}"
            except Exception as exc:
                log.warning("[llm_client] OpenRouter JSON call failed: %s", exc)
                last_error = exc

        elif prov == "groq" and settings.has_groq:
            try:
                client = get_groq_client()
                resp = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or "{}"
                return json.loads(content), f"groq/{settings.groq_model}"
            except Exception as exc:
                log.warning("[llm_client] Groq JSON call failed: %s", exc)
                last_error = exc

    raise RuntimeError(f"All available LLM providers failed. Last error: {last_error}")


def call_llm_text(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> tuple[str, str]:
    """
    Call the active LLM provider (Groq or OpenRouter) requesting text.
    Falls back gracefully between providers.
    Returns (text_response, provider_model_used).
    """
    providers = []
    if settings.active_llm_provider == "openrouter":
        providers = ["openrouter", "groq"]
    else:
        providers = ["groq", "openrouter"]

    last_error = None
    for prov in providers:
        if prov == "openrouter" and settings.has_openrouter:
            try:
                client = get_openrouter_client()
                resp = client.chat.completions.create(
                    model=settings.openrouter_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return (resp.choices[0].message.content or "").strip(), f"openrouter/{settings.openrouter_model}"
            except Exception as exc:
                log.warning("[llm_client] OpenRouter text call failed: %s", exc)
                last_error = exc

        elif prov == "groq" and settings.has_groq:
            try:
                client = get_groq_client()
                resp = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return (resp.choices[0].message.content or "").strip(), f"groq/{settings.groq_model}"
            except Exception as exc:
                log.warning("[llm_client] Groq text call failed: %s", exc)
                last_error = exc

    raise RuntimeError(f"All available LLM providers failed. Last error: {last_error}")
