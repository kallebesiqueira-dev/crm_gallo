"""Coverage for the in-app AI assistant endpoints (/api/assistant).

Contract-level: auth gate + response shape for the blocking and SSE
endpoints. The tests assert the contract regardless of whether an LLM is
configured in the env — with no provider key (the default test/local env),
`chat()` returns the graceful "not configured" message with a 200, so no
real LLM call is made.
"""

from __future__ import annotations


def test_chat_requires_auth(client):
    assert client.post("/api/assistant/chat", json={"message": "hi"}).status_code == 401


def test_chat_returns_reply(admin_client):
    r = admin_client.post("/api/assistant/chat", json={"message": "hello", "locale": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "reply" in body and isinstance(body["reply"], str) and body["reply"]


def test_chat_stream_is_sse(admin_client):
    r = admin_client.post("/api/assistant/chat/stream", json={"message": "hello"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    # The generator always terminates the stream with a [DONE] sentinel.
    assert "data:" in r.text
    assert "[DONE]" in r.text


def test_chat_stream_requires_auth(client):
    assert client.post("/api/assistant/chat/stream", json={"message": "hi"}).status_code == 401
