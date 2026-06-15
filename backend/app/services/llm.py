"""LLM abstraction layer — swaps between Ollama (local, free) and Anthropic (cloud)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, TypedDict

import httpx
from anthropic import AnthropicError, AsyncAnthropic

from app.config import get_settings
from app.metrics import LLM_DURATION, LLM_REQUESTS, LLM_TOKENS

logger = logging.getLogger(__name__)
settings = get_settings()


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """Raised when no LLM backend can answer."""


# Per-use-case temperature policy (None ⇒ provider default). Structured /
# extraction tasks run deterministic so the same input yields the same output
# (reproducible lead scores, stable summaries); conversation runs warmer.
TEMP_DETERMINISTIC = 0.0  # lead scoring — parses a numeric score + fixed enum
TEMP_FACTUAL = 0.3  # customer summaries — concise, low variance
TEMP_CONVERSATIONAL = 0.5  # in-app AI assistant chat
TEMP_CHATBOT = 0.4  # public landing chatbot


# Per-call token usage is fanned out to Prometheus (LLM_TOKENS) AND, when a
# `capture_usage()` block is active on the current task, buffered for per-org
# persistence (app.services.llm_usage). The ContextVar keeps llm.py DB-free:
# providers just append; the caller (which has the org + DB session) persists.
_usage_buffer: ContextVar[list[dict] | None] = ContextVar("llm_usage_buffer", default=None)


def _record_usage(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    buf = _usage_buffer.get()
    if buf is not None:
        buf.append(
            {
                "provider": provider,
                "model": model,
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
            }
        )


@contextmanager
def capture_usage() -> Iterator[list[dict]]:
    """Collect token usage from blocking LLM calls made inside the block.

    Yields a list of {provider, model, input_tokens, output_tokens} dicts —
    one per completion. Streaming calls don't carry usage from the providers,
    so they record nothing. Reset-token based, so nesting is safe."""
    buf: list[dict] = []
    token = _usage_buffer.set(buf)
    try:
        yield buf
    finally:
        _usage_buffer.reset(token)


async def _chat_anthropic(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> str:
    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is empty")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        message = await client.messages.create(**kwargs)
    except AnthropicError as e:
        raise LLMError(f"Anthropic: {e}") from e
    usage = getattr(message, "usage", None)
    if usage:
        inp = getattr(usage, "input_tokens", 0)
        out = getattr(usage, "output_tokens", 0)
        LLM_TOKENS.labels(provider="anthropic", direction="input").inc(inp)
        LLM_TOKENS.labels(provider="anthropic", direction="output").inc(out)
        _record_usage("anthropic", settings.anthropic_model, inp, out)
    return "".join(block.text for block in message.content if block.type == "text").strip()


async def _chat_ollama(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> str:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    options: dict = {"num_predict": max_tokens}
    if temperature is not None:
        options["temperature"] = temperature
    payload = {
        "model": settings.ollama_model,
        "messages": payload_messages,
        "stream": False,
        "options": options,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            res = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama: {e}") from e

    content = data.get("message", {}).get("content", "")
    if not content:
        raise LLMError(f"Ollama returned empty content: {data}")
    inp = data.get("prompt_eval_count", 0)
    out = data.get("eval_count", 0)
    LLM_TOKENS.labels(provider="ollama", direction="input").inc(inp)
    LLM_TOKENS.labels(provider="ollama", direction="output").inc(out)
    _record_usage("ollama", settings.ollama_model, inp, out)
    return content.strip()


async def _chat_openai_compatible(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> str:
    """Any provider that speaks the OpenAI `POST /chat/completions` shape —
    Groq, Mistral, Cerebras, OpenRouter, Together, a self-hosted vLLM, etc.
    Selected via `llm_provider="openai_compat"`; the endpoint, model and key
    come from LLM_BASE_URL / LLM_MODEL / LLM_API_KEY so swapping vendors is an
    env change, not a code change."""
    if not settings.llm_api_key or not settings.llm_base_url:
        raise LLMError("LLM_BASE_URL / LLM_API_KEY not set")

    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "model": settings.llm_model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        raise LLMError(f"OpenAI-compatible LLM: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"OpenAI-compatible LLM: unexpected response: {str(data)[:200]}") from e
    if not content or not content.strip():
        raise LLMError("OpenAI-compatible LLM returned empty content")
    usage = data.get("usage") or {}
    if usage:
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
        LLM_TOKENS.labels(provider="openai_compat", direction="input").inc(inp)
        LLM_TOKENS.labels(provider="openai_compat", direction="output").inc(out)
        _record_usage("openai_compat", settings.llm_model, inp, out)
    return content.strip()


# ---------- Streaming variants ----------


async def _stream_anthropic(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> AsyncGenerator[str, None]:
    if not settings.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY is empty")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
    except AnthropicError as e:
        raise LLMError(f"Anthropic: {e}") from e


async def _stream_ollama(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> AsyncGenerator[str, None]:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    options: dict = {"num_predict": max_tokens}
    if temperature is not None:
        options["temperature"] = temperature
    payload = {
        "model": settings.ollama_model,
        "messages": payload_messages,
        "stream": True,
        "options": options,
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", f"{settings.ollama_url}/api/chat", json=payload
            ) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama: {e}") from e


async def _stream_openai_compatible(
    messages: list[Message], system: str | None, max_tokens: int, temperature: float | None = None
) -> AsyncGenerator[str, None]:
    if not settings.llm_api_key or not settings.llm_base_url:
        raise LLMError("LLM_BASE_URL / LLM_API_KEY not set")

    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "model": settings.llm_model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        chunk = data["choices"][0].get("delta", {}).get("content") or ""
                        if chunk:
                            yield chunk
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
    except httpx.HTTPError as e:
        raise LLMError(f"OpenAI-compatible LLM: {e}") from e


_PROVIDERS = {
    "ollama": _chat_ollama,
    "anthropic": _chat_anthropic,
    "openai_compat": _chat_openai_compatible,
}

_STREAM_PROVIDERS: dict[str, object] = {
    "ollama": _stream_ollama,
    "anthropic": _stream_anthropic,
    "openai_compat": _stream_openai_compatible,
}


def _provider_configured(name: str) -> bool:
    """Whether a provider has the credentials it needs to be worth trying.
    Ollama is the local backend — treated as 'reachable' only when it is the
    selected provider, never as a blind cloud fallback (its long timeout would
    stall the request when no Ollama is deployed)."""
    if name == "anthropic":
        return bool(settings.anthropic_api_key)
    if name == "openai_compat":
        return bool(settings.llm_api_key and settings.llm_base_url)
    if name == "ollama":
        return True
    return False


async def chat_completion(
    messages: list[Message],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
) -> str:
    """Send a chat completion using the configured provider, falling back to
    any *other configured cloud* provider if it fails (e.g. Groq rate-limited
    → Anthropic when a key is set). The local Ollama backend is only attempted
    when it is the selected provider, so an unreachable Ollama can never stall
    a cloud deploy's fallback path on its long timeout.

    `temperature` is forwarded to the provider when set; leave it None to use
    the provider default. Callers pick a value per use case — e.g. 0.0 for the
    deterministic lead score, warmer for the conversational assistant.
    """
    provider = settings.llm_provider.lower()
    order = [provider] + [
        p for p in ("openai_compat", "anthropic") if p != provider and _provider_configured(p)
    ]
    errors: list[str] = []
    start = time.perf_counter()
    used_provider = provider
    for i, name in enumerate(order):
        fn = _PROVIDERS.get(name)
        if fn is None:
            continue
        try:
            result = await fn(messages, system, max_tokens, temperature)
            status = "fallback" if i > 0 else "success"
            used_provider = name
            LLM_REQUESTS.labels(provider=used_provider, status=status).inc()
            LLM_DURATION.labels(provider=used_provider).observe(time.perf_counter() - start)
            return result
        except LLMError as e:
            errors.append(f"{name}: {e}")
            logger.warning("LLM provider %s failed: %s — trying next", name, e)
            LLM_REQUESTS.labels(provider=name, status="error").inc()
    raise LLMError("All LLM providers failed — " + " | ".join(errors))


async def chat_completion_stream(
    messages: list[Message],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming variant — yields text chunks as they arrive from the provider.
    No fallback between providers (can't retry mid-stream); errors surface as
    LLMError before the first yield or as a yielded error token mid-stream."""
    provider = settings.llm_provider.lower()
    fn = _STREAM_PROVIDERS.get(provider)
    if fn is None:
        raise LLMError(f"Unknown provider: {provider}")
    async for chunk in fn(messages, system, max_tokens, temperature):
        yield chunk


def is_configured() -> bool:
    """True if the selected provider has the credentials it needs."""
    return _provider_configured(settings.llm_provider.lower())
