"""Per-use-case LLM temperature plumbing.

These exercise the pure provider functions + the `chat_completion` dispatch
with a stubbed httpx client. No DB is touched, so `asyncio.run` is safe here
(unlike the worker-job tests, whose asyncpg pool is loop-bound).
"""

from __future__ import annotations

import asyncio

import app.services.llm as llm
from app.services.llm import (
    TEMP_CHATBOT,
    TEMP_CONVERSATIONAL,
    TEMP_DETERMINISTIC,
    TEMP_FACTUAL,
    _chat_ollama,
    _chat_openai_compatible,
    chat_completion,
)


def _stub_httpx(monkeypatch, resp_data: dict) -> dict:
    """Patch `app.services.llm.httpx.AsyncClient` to capture the posted JSON
    body and return a canned response, instead of hitting the network."""
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return resp_data

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

    monkeypatch.setattr("app.services.llm.httpx.AsyncClient", _Client)
    return captured


_OLLAMA_OK = {"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 1}
_OPENAI_OK = {"choices": [{"message": {"content": "ok"}}], "usage": {}}


# ---------- policy constants ----------


def test_temperature_policy_values():
    # Deterministic for structured tasks; warmer for conversation.
    assert TEMP_DETERMINISTIC == 0.0
    assert TEMP_FACTUAL < TEMP_CHATBOT < TEMP_CONVERSATIONAL


# ---------- ollama ----------


def test_ollama_includes_temperature(monkeypatch):
    cap = _stub_httpx(monkeypatch, _OLLAMA_OK)
    asyncio.run(_chat_ollama([{"role": "user", "content": "hi"}], None, 100, temperature=0.0))
    assert cap["payload"]["options"]["temperature"] == 0.0


def test_ollama_omits_temperature_when_none(monkeypatch):
    cap = _stub_httpx(monkeypatch, _OLLAMA_OK)
    asyncio.run(_chat_ollama([{"role": "user", "content": "hi"}], None, 100))
    assert "temperature" not in cap["payload"]["options"]


# ---------- openai-compatible ----------


def test_openai_compat_includes_temperature(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_api_key", "k", raising=False)
    monkeypatch.setattr(llm.settings, "llm_base_url", "http://llm.test/v1", raising=False)
    monkeypatch.setattr(llm.settings, "llm_model", "m", raising=False)
    cap = _stub_httpx(monkeypatch, _OPENAI_OK)
    asyncio.run(
        _chat_openai_compatible([{"role": "user", "content": "hi"}], None, 100, temperature=0.25)
    )
    assert cap["payload"]["temperature"] == 0.25


def test_openai_compat_omits_temperature_when_none(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_api_key", "k", raising=False)
    monkeypatch.setattr(llm.settings, "llm_base_url", "http://llm.test/v1", raising=False)
    monkeypatch.setattr(llm.settings, "llm_model", "m", raising=False)
    cap = _stub_httpx(monkeypatch, _OPENAI_OK)
    asyncio.run(_chat_openai_compatible([{"role": "user", "content": "hi"}], None, 100))
    assert "temperature" not in cap["payload"]


# ---------- chat_completion dispatch forwards it ----------


def test_chat_completion_forwards_temperature(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "ollama", raising=False)
    cap = _stub_httpx(monkeypatch, _OLLAMA_OK)
    out = asyncio.run(chat_completion([{"role": "user", "content": "hi"}], temperature=0.0))
    assert out == "ok"
    assert cap["payload"]["options"]["temperature"] == 0.0
