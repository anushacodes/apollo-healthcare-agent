from types import SimpleNamespace
from unittest.mock import Mock

import groq
import httpx
import openai
import pytest

from app import llm_client
from app.config import settings


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def install_provider(monkeypatch, provider, completion):
    monkeypatch.setattr(settings, f"{provider}_api_key", "test-key-private")
    monkeypatch.setattr(settings, "llm_provider", provider)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    monkeypatch.setattr(llm_client, f"get_{provider}_client", lambda: client)


@pytest.mark.parametrize("call", [llm_client.call_llm_text, llm_client.call_llm_json])
def test_missing_key_has_actionable_message(call):
    with pytest.raises(llm_client.LLMProviderError) as caught:
        call([])
    assert caught.value.code == "missing_api_key"
    assert "GROQ_API_KEY" in str(caught.value)
    assert "restart" in str(caught.value)


@pytest.mark.parametrize("provider,sdk", [("groq", groq), ("openrouter", openai)])
@pytest.mark.parametrize("status,code", [
    (401, "invalid_api_key"), (402, "insufficient_credits"), (403, "access_denied"),
    (429, "rate_limited"), (408, "provider_timeout"), (400, "invalid_model_request"),
    (404, "invalid_model_request"), (503, "provider_unavailable"),
])
def test_provider_http_failures_are_actionable_and_do_not_leak_bodies(
    monkeypatch, caplog, provider, sdk, status, code,
):
    raw = "private-patient-details test-key-private"
    request = httpx.Request("POST", "https://provider.invalid/chat")
    error = sdk.APIStatusError(raw, response=httpx.Response(status, request=request), body={"detail": raw})
    install_provider(monkeypatch, provider, Mock(side_effect=error))
    with pytest.raises(llm_client.LLMProviderError) as caught:
        llm_client.call_llm_text([])
    assert caught.value.code == code
    assert ("Groq" if provider == "groq" else "OpenRouter") in str(caught.value)
    assert raw not in str(caught.value)
    assert raw not in caplog.text


@pytest.mark.parametrize("provider,sdk", [("groq", groq), ("openrouter", openai)])
@pytest.mark.parametrize("kind,code", [("timeout", "provider_timeout"), ("connection", "provider_connection")])
def test_provider_transport_errors(monkeypatch, provider, sdk, kind, code):
    request = httpx.Request("POST", "https://provider.invalid/chat")
    error = sdk.APITimeoutError(request=request) if kind == "timeout" else sdk.APIConnectionError(request=request)
    install_provider(monkeypatch, provider, Mock(side_effect=error))
    with pytest.raises(llm_client.LLMProviderError) as caught:
        llm_client.call_llm_text([])
    assert caught.value.code == code


@pytest.mark.parametrize("call,content", [
    (llm_client.call_llm_text, ""), (llm_client.call_llm_text, None),
    (llm_client.call_llm_json, "not JSON"), (llm_client.call_llm_json, "[]"),
])
def test_empty_or_malformed_provider_output_is_not_a_success(monkeypatch, call, content):
    install_provider(monkeypatch, "groq", Mock(return_value=response(content)))
    with pytest.raises(llm_client.LLMProviderError) as caught:
        call([])
    assert caught.value.code == "invalid_provider_response"


@pytest.mark.parametrize("primary", ["groq", "openrouter"])
@pytest.mark.parametrize("call,content,expected", [
    (llm_client.call_llm_text, "Fallback answer", "Fallback answer"),
    (llm_client.call_llm_json, '{"answer": "Fallback"}', {"answer": "Fallback"}),
])
def test_failed_primary_uses_configured_fallback(monkeypatch, primary, call, content, expected):
    secondary = "openrouter" if primary == "groq" else "groq"
    fallback = Mock(return_value=response(content))
    install_provider(monkeypatch, secondary, fallback)
    install_provider(monkeypatch, primary, Mock(side_effect=RuntimeError("private failure")))
    answer, model = call([])
    assert answer == expected
    assert model.startswith(f"{secondary}/")
    assert fallback.call_count == 1
