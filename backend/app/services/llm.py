"""LLM abstraction layer — swaps between Ollama (local, free) and Anthropic (cloud)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Literal, TypedDict

import httpx
from anthropic import AnthropicError, AsyncAnthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """Raised when no LLM backend can answer."""


async def _chat_anthropic(messages: list[Message], system: str | None, max_tokens: int) -> str:
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
    try:
        message = await client.messages.create(**kwargs)
    except AnthropicError as e:
        raise LLMError(f"Anthropic: {e}") from e
    return "".join(block.text for block in message.content if block.type == "text").strip()


async def _chat_ollama(messages: list[Message], system: str | None, max_tokens: int) -> str:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "model": settings.ollama_model,
        "messages": payload_messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
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
    return content.strip()


async def _chat_openai_compatible(
    messages: list[Message], system: str | None, max_tokens: int
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
    return content.strip()


# ---------- Streaming variants ----------

async def _stream_anthropic(
    messages: list[Message], system: str | None, max_tokens: int
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
    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
    except AnthropicError as e:
        raise LLMError(f"Anthropic: {e}") from e


async def _stream_ollama(
    messages: list[Message], system: str | None, max_tokens: int
) -> AsyncGenerator[str, None]:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "model": settings.ollama_model,
        "messages": payload_messages,
        "stream": True,
        "options": {"num_predict": max_tokens},
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
    messages: list[Message], system: str | None, max_tokens: int
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
) -> str:
    """Send a chat completion using the configured provider, falling back to
    any *other configured cloud* provider if it fails (e.g. Groq rate-limited
    → Anthropic when a key is set). The local Ollama backend is only attempted
    when it is the selected provider, so an unreachable Ollama can never stall
    a cloud deploy's fallback path on its long timeout.
    """
    provider = settings.llm_provider.lower()
    order = [provider] + [
        p for p in ("openai_compat", "anthropic") if p != provider and _provider_configured(p)
    ]
    errors: list[str] = []
    for name in order:
        fn = _PROVIDERS.get(name)
        if fn is None:
            continue
        try:
            return await fn(messages, system, max_tokens)
        except LLMError as e:
            errors.append(f"{name}: {e}")
            logger.warning("LLM provider %s failed: %s — trying next", name, e)
    raise LLMError("All LLM providers failed — " + " | ".join(errors))


async def chat_completion_stream(
    messages: list[Message],
    system: str | None = None,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """Streaming variant — yields text chunks as they arrive from the provider.
    No fallback between providers (can't retry mid-stream); errors surface as
    LLMError before the first yield or as a yielded error token mid-stream."""
    provider = settings.llm_provider.lower()
    fn = _STREAM_PROVIDERS.get(provider)
    if fn is None:
        raise LLMError(f"Unknown provider: {provider}")
    async for chunk in fn(messages, system, max_tokens):
        yield chunk


def is_configured() -> bool:
    """True if the selected provider has the credentials it needs."""
    return _provider_configured(settings.llm_provider.lower())


logger = logging.getLogger(__name__)
settings = get_settings()


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """Raised when no LLM backend can answer."""


async def _chat_anthropic(messages: list[Message], system: str | None, max_tokens: int) -> str:
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
    try:
        message = await client.messages.create(**kwargs)
    except AnthropicError as e:
        raise LLMError(f"Anthropic: {e}") from e
    return "".join(block.text for block in message.content if block.type == "text").strip()


async def _chat_ollama(messages: list[Message], system: str | None, max_tokens: int) -> str:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    payload = {
        "model": settings.ollama_model,
        "messages": payload_messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
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
    return content.strip()


async def _chat_openai_compatible(
    messages: list[Message], system: str | None, max_tokens: int
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
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        raise LLMError(f"OpenAI-compatible LLM: {e}") from e

    # Standard OpenAI response shape. Reasoning models (e.g. gpt-oss) put their
    # scratchpad in a separate `reasoning` field; the answer is in `content`.
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"OpenAI-compatible LLM: unexpected response: {str(data)[:200]}") from e
    if not content or not content.strip():
        raise LLMError("OpenAI-compatible LLM returned empty content")
    return content.strip()


_PROVIDERS = {
    "ollama": _chat_ollama,
    "anthropic": _chat_anthropic,
    "openai_compat": _chat_openai_compatible,
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
) -> str:
    """Send a chat completion using the configured provider, falling back to
    any *other configured cloud* provider if it fails (e.g. Groq rate-limited
    → Anthropic when a key is set). The local Ollama backend is only attempted
    when it is the selected provider, so an unreachable Ollama can never stall
    a cloud deploy's fallback path on its long timeout.
    """
    provider = settings.llm_provider.lower()
    order = [provider] + [
        p for p in ("openai_compat", "anthropic") if p != provider and _provider_configured(p)
    ]
    errors: list[str] = []
    for name in order:
        fn = _PROVIDERS.get(name)
        if fn is None:
            continue
        try:
            return await fn(messages, system, max_tokens)
        except LLMError as e:
            errors.append(f"{name}: {e}")
            logger.warning("LLM provider %s failed: %s — trying next", name, e)
    raise LLMError("All LLM providers failed — " + " | ".join(errors))


def is_configured() -> bool:
    """True if the selected provider has the credentials it needs."""
    return _provider_configured(settings.llm_provider.lower())
