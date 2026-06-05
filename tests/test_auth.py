"""Tests for the HTTP bearer-auth gate and gateway degradation.

The allowlist (the local exec gate) is covered in test_ops.py. This file covers
the *network* security boundary — the pure-ASGI bearer gate that protects the
Streamable-HTTP endpoint over Tailscale — plus graceful degradation of
gpu_generate when no gateway key is configured.
"""
from __future__ import annotations

import asyncio

import httpx

from labcontrol import ops
from labcontrol.server import _BearerAuthASGI


def _drive(app, scope) -> list[dict]:
    """Run a one-shot ASGI request against `app` and capture sent messages."""
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


class _Inner:
    """Inner ASGI app that records whether it was reached."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _http_scope(auth: bytes | None) -> dict:
    headers = [(b"authorization", auth)] if auth is not None else []
    return {"type": "http", "headers": headers}


def test_auth_allows_correct_token():
    inner = _Inner()
    sent = _drive(_BearerAuthASGI(inner, "s3cret"), _http_scope(b"Bearer s3cret"))
    assert inner.called
    assert sent[0]["status"] == 200


def test_auth_rejects_wrong_token():
    inner = _Inner()
    sent = _drive(_BearerAuthASGI(inner, "s3cret"), _http_scope(b"Bearer nope"))
    assert not inner.called, "wrong token must not reach the wrapped app"
    assert sent[0]["status"] == 401
    assert b"unauthorized" in sent[1]["body"]


def test_auth_rejects_missing_header():
    inner = _Inner()
    sent = _drive(_BearerAuthASGI(inner, "s3cret"), _http_scope(None))
    assert not inner.called
    assert sent[0]["status"] == 401


def test_auth_rejects_bare_token_without_scheme():
    # The expected value is "Bearer <token>"; a raw token must not pass.
    inner = _Inner()
    sent = _drive(_BearerAuthASGI(inner, "s3cret"), _http_scope(b"s3cret"))
    assert not inner.called
    assert sent[0]["status"] == 401


def test_auth_passes_through_non_http_scope():
    # lifespan/websocket scopes are not gated and must pass through untouched.
    inner = _Inner()
    _drive(_BearerAuthASGI(inner, "s3cret"), {"type": "lifespan", "headers": []})
    assert inner.called


def test_gpu_generate_degrades_without_key(monkeypatch):
    monkeypatch.setattr(ops.cfg, "master_key", None)

    def _must_not_call(*a, **k):
        raise AssertionError("gateway must not be called without a key")

    monkeypatch.setattr(ops.httpx, "post", _must_not_call)
    out = ops.gateway_generate("hi")
    assert "error" in out and "LITELLM_MASTER_KEY" in out["error"]
    assert "hint" in out
    assert "text" not in out


def test_gateway_generate_returns_structured_error_on_failure(monkeypatch):
    monkeypatch.setattr(ops.cfg, "master_key", "k")

    def _raise(*a, **k):
        raise httpx.ConnectError("gateway down")

    monkeypatch.setattr(ops.httpx, "post", _raise)
    out = ops.gateway_generate("hi")
    assert "error" in out
    assert "text" not in out
