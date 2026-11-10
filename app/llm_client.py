import json
import logging
from functools import lru_cache
from typing import Any, Never

import groq
import instructor
import openai
from groq import Groq
from instructor import Instructor, Mode, Provider
from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """An actionable provider failure safe to send to the workspace."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _provider_error(provider: str, exc: Exception) -> LLMProviderError:
    name = "Groq" if provider == "groq" else "OpenRouter"
    key = "GROQ_API_KEY" if provider == "groq" else "OPENROUTER_API_KEY"
    model = "GROQ_MODEL" if provider == "groq" else "OPENROUTER_MODEL"
    status = getattr(exc, "status_code", None)
    if status == 401:
        return LLMProviderError(
            "invalid_api_key", f"{name} rejected its API key. Check {key} in .env and restart the backend.",
        )
    if status == 402:
        return LLMProviderError(
            "insufficient_credits", f"{name} requires available credits. Check your provider account balance.",
        )
    if status == 403:
        return LLMProviderError(
            "access_denied", f"{name} denied access. Check your API key permissions and model access.",
        )
    if status == 429:
        return LLMProviderError(
            "rate_limited", f"{name}'s rate limit or quota was reached. "
            "Wait before retrying or check your provider usage limits.",
        )
    if status == 408 or isinstance(exc, (groq.APITimeoutError, openai.APITimeoutError)):
        return LLMProviderError("provider_timeout", f"{name} took too long to respond. Please try again.")
    if isinstance(exc, (groq.APIConnectionError, openai.APIConnectionError)):
        return LLMProviderError(
            "provider_connection", f"Cannot connect to {name}. Check the backend's network connection and try again.",
        )
    if status in (400, 404, 422):
        return LLMProviderError(
            "invalid_model_request", f"{name} rejected the model or request. Check {model} and model availability.",
        )
    if status is not None and status >= 500:
        return LLMProviderError("provider_unavailable", f"{name} is temporarily unavailable. Please try again shortly.")
    if isinstance(exc, (ValueError, IndexError)):
        return LLMProviderError(
            "invalid_provider_response", f"{name} returned an empty or unreadable response. Please try again.",
        )
    return LLMProviderError("provider_error", f"{name} could not generate a response. Please try again.")


def _raise_provider_failure(last_error: LLMProviderError | None) -> Never:
    if last_error is not None:
        raise last_error
    raise LLMProviderError(
        "missing_api_key",
        "Ask needs a Groq or OpenRouter API key. Add GROQ_API_KEY or OPENROUTER_API_KEY to .env and restart the backend.",
    )


def _response_text(response: Any) -> str:
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("Empty provider response")
    return content


def _response_json(response: Any) -> dict[str, Any]:
    content = json.loads(_response_text(response))
    if not isinstance(content, dict):
        raise ValueError("Expected a JSON object")
    return content


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    """Shared Groq client, built once and reused everywhere. Groq's sync
    client wraps httpx.Client, which is safe to share across threads."""
    return Groq(api_key=settings.groq_api_key, timeout=30.0, max_retries=0)


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
        timeout=30.0,
        max_retries=0,
    )


def call_llm_json(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    allow_fallback: bool = True,
    timeout: float | None = None,
    telemetry: dict | None = None,
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

    providers = [p for p in providers if getattr(settings, f"has_{p}")]
    if not allow_fallback:
        providers = providers[:1]
    if telemetry is not None:
        telemetry.update(requests=0, input_tokens=None, output_tokens=None, cost_usd=None)
    last_error = None
    for prov in providers:
        if telemetry is not None:
            telemetry["requests"] += 1
        if prov == "openrouter" and settings.has_openrouter:
            try:
                client = get_openrouter_client()
                if timeout is not None:
                    client = client.with_options(timeout=timeout)
                resp = client.chat.completions.create(
                    model=settings.openrouter_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result = _response_json(resp)
                _record_usage(resp, telemetry)
                return result, f"openrouter/{settings.openrouter_model}"
            except Exception as exc:
                last_error = _provider_error(prov, exc)
                log.warning("[llm_client] OpenRouter JSON call failed: %s", last_error)

        elif prov == "groq" and settings.has_groq:
            try:
                client = get_groq_client()
                if timeout is not None:
                    client = client.with_options(timeout=timeout)
                resp = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result = _response_json(resp)
                _record_usage(resp, telemetry)
                return result, f"groq/{settings.groq_model}"
            except Exception as exc:
                last_error = _provider_error(prov, exc)
                log.warning("[llm_client] Groq JSON call failed: %s", last_error)

    _raise_provider_failure(last_error)


def _record_usage(response: Any, telemetry: dict | None) -> None:
    if telemetry is None:
        return
    if telemetry["requests"] != 1:
        # A failed earlier attempt may also have been billed. Partial usage is not a total.
        return
    usage = getattr(response, "usage", None)
    for target, field in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
        value = getattr(usage, field, None)
        if isinstance(value, int) and value >= 0:
            telemetry[target] = value
    # Provider/model prices vary. Do not infer a monetary charge from token counts.


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
                return _response_text(resp), f"openrouter/{settings.openrouter_model}"
            except Exception as exc:
                last_error = _provider_error(prov, exc)
                log.warning("[llm_client] OpenRouter text call failed: %s", last_error)

        elif prov == "groq" and settings.has_groq:
            try:
                client = get_groq_client()
                resp = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return _response_text(resp), f"groq/{settings.groq_model}"
            except Exception as exc:
                last_error = _provider_error(prov, exc)
                log.warning("[llm_client] Groq text call failed: %s", last_error)

    _raise_provider_failure(last_error)
