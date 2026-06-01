"""LLM abstraction layer — swaps between Ollama (local, free) and Anthropic (cloud)."""

from __future__ import annotations

import logging
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


async def chat_completion(
    messages: list[Message],
    system: str | None = None,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion using the configured provider.

    Falls back gracefully if the configured provider fails but the alternate
    one is available (e.g. Ollama down → try Anthropic if a key is set).
    """
    provider = settings.llm_provider.lower()

    primary = _chat_ollama if provider == "ollama" else _chat_anthropic
    secondary = _chat_anthropic if provider == "ollama" else _chat_ollama

    try:
        return await primary(messages, system, max_tokens)
    except LLMError as e:
        logger.warning("Primary LLM (%s) failed: %s — trying fallback", provider, e)
        try:
            return await secondary(messages, system, max_tokens)
        except LLMError as e2:
            logger.warning("Fallback LLM also failed: %s", e2)
            raise LLMError(f"Both providers failed. Primary: {e}. Fallback: {e2}") from e2


def is_configured() -> bool:
    """True if at least one provider can plausibly answer."""
    if settings.llm_provider.lower() == "anthropic":
        return bool(settings.anthropic_api_key)
    return True  # Ollama is always reachable when the container is up
