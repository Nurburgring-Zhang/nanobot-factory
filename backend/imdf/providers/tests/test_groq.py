"""P20-A: GroqProvider tests.

Covers:
- Inherits BaseProvider
- list_models returns curated catalog
- health_check (no key → placeholder, with key → 200/4xx paths)
- invoke round-trip (200 + 401 + 429 + 500 + httpx error)
- invoke_stream yields SSE-style chunks
- Pydantic v2 ProviderResponse shape

Uses AsyncMock to patch ``httpx.AsyncClient`` so the production code's
``async with httpx.AsyncClient(...) as client`` flows through a mock
context manager — no real network.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _openai_chat_response(
    content: str = "Groq says hi",
    model: str = "llama-3.1-70b-versatile",
    prompt_tokens: int = 8,
    completion_tokens: int = 12,
) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{model}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _sse_lines(events: List[Dict[str, Any]]) -> bytes:
    """Build an OpenAI-style SSE response body (text/event-stream)."""
    parts: List[bytes] = []
    for ev in events:
        parts.append(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
    parts.append(b"data: [DONE]\n\n")
    return b"".join(parts)


def _mock_response(status: int = 200, json_data: Any = None, text: str = "",
                   content: bytes = b"", headers: Optional[Dict[str, str]] = None) -> MagicMock:
    """Build a fake httpx.Response."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.headers = headers or {}
    if json_data is not None:
        r.json.return_value = json_data
    r.text = text or (json.dumps(json_data) if json_data is not None else "")
    if content:
        r.content = content
        r.aread = AsyncMock(return_value=content)
    return r


def _patch_async_client(responses: List[MagicMock]) -> Any:
    """Patch httpx.AsyncClient so that ``async with AsyncClient() as c``
    yields a client whose ``post(...)`` returns the next mock response.
    """
    async_client_mock = MagicMock()
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)
    iterator = iter(responses)

    async def fake_post(*args: Any, **kwargs: Any) -> MagicMock:
        try:
            return next(iterator)
        except StopIteration:
            return _mock_response(500, text="exhausted")

    async def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        try:
            return next(iterator)
        except StopIteration:
            return _mock_response(500, text="exhausted")

    async_client_mock.post = fake_post
    async_client_mock.get = fake_get
    return patch("httpx.AsyncClient", return_value=async_client_mock)


def _patch_async_client_stream(responses: List[MagicMock]) -> Any:
    """Patch httpx.AsyncClient for streaming.  ``client.stream('POST', ...)``
    returns an async context manager yielding the mock response.
    """
    async_client_mock = MagicMock()
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=stream_cm)
    stream_cm.__aexit__ = AsyncMock(return_value=None)
    iterator = iter(responses)

    def fake_stream(method: str, url: str, **kwargs: Any) -> MagicMock:
        try:
            resp = next(iterator)
        except StopIteration:
            resp = _mock_response(500, text="exhausted")
        # Set the response onto the stream_cm itself.
        stream_cm.status_code = resp.status_code
        stream_cm.headers = resp.headers
        stream_cm.aread = resp.aread if hasattr(resp, "aread") else AsyncMock(return_value=b"")
        # Build an aiter_lines that yields the SSE body line by line.
        if hasattr(resp, "content") and resp.content:
            body_text = resp.content.decode("utf-8", errors="ignore")
            lines = body_text.split("\n")
        else:
            lines = []

        async def aiter_lines() -> Any:
            for ln in lines:
                yield ln

        stream_cm.aiter_lines = aiter_lines
        return stream_cm

    async_client_mock.stream = fake_stream
    # Also set post/get in case the code path doesn't use stream.
    async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
    async_client_mock.__aexit__ = AsyncMock(return_value=None)
    iterator_post = iter(responses)

    async def fake_post(*args: Any, **kwargs: Any) -> MagicMock:
        try:
            return next(iterator_post)
        except StopIteration:
            return _mock_response(500, text="exhausted")

    async_client_mock.post = fake_post
    async_client_mock.get = fake_post
    return patch("httpx.AsyncClient", return_value=async_client_mock)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


# ─── 1. Class shape / inheritance ───────────────────────────────────────────


class TestGroqShape:
    def test_inherits_baseprovider(self):
        from providers.base import BaseProvider
        from providers.groq import GroqProvider
        assert issubclass(GroqProvider, BaseProvider)

    def test_provider_name_and_family(self):
        from providers.groq import GroqProvider
        p = GroqProvider(api_key="x")
        assert p.provider_name == "groq"
        assert p.family == "groq"
        assert p.DEFAULT_BASE_URL == "https://api.groq.com/openai/v1"
        assert p.DEFAULT_MODEL == "llama-3.1-70b-versatile"

    def test_default_model_used_when_param_model_none(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        p = GroqProvider(api_key="x")
        assert p.api_key == "x"
        params = InvokeParams()
        assert params.model is None  # → invoke() falls back to DEFAULT_MODEL

    def test_api_key_from_env(self, monkeypatch):
        from providers.groq import GroqProvider
        monkeypatch.setenv("GROQ_API_KEY", "sk-groq-env")
        p = GroqProvider()
        assert p.api_key == "sk-groq-env"

    def test_timeout_override(self):
        from providers.groq import GroqProvider
        p = GroqProvider(api_key="x", timeout=12.5)
        assert p.timeout == 12.5


# ─── 2. list_models ─────────────────────────────────────────────────────────


class TestGroqListModels:
    @pytest.mark.asyncio
    async def test_returns_curated_models(self):
        from providers.groq import GroqProvider
        p = GroqProvider(api_key="x")
        models = await p.list_models()
        assert isinstance(models, list)
        assert "llama-3.1-70b-versatile" in models
        assert "mixtral-8x7b-32768" in models
        assert "gemma2-9b-it" in models

    def test_default_model_in_catalog(self):
        from providers.groq import GroqProvider
        assert GroqProvider.DEFAULT_MODEL in GroqProvider.DEFAULT_MODELS


# ─── 3. invoke round-trip (200 / 401 / 429 / 500 / 4xx) ─────────────────────


class TestGroqInvoke:
    @pytest.mark.asyncio
    async def test_invoke_success(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams, ProviderResponse
        body = _openai_chat_response("hi from groq", prompt_tokens=5, completion_tokens=7)
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-test")
            res = await p.invoke("hello", InvokeParams())
        assert isinstance(res, ProviderResponse)
        assert res.success is True
        assert res.content == "hi from groq"
        assert res.provider == "groq"
        assert res.usage["total_tokens"] == 12

    @pytest.mark.asyncio
    async def test_invoke_401_unauthorized(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        resp = _mock_response(401, text="invalid api key")
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-bad")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "groq_http_401" in res.error
        assert res.provider == "groq"

    @pytest.mark.asyncio
    async def test_invoke_429_rate_limit(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        resp = _mock_response(429, text="rate limited")
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "groq_http_429" in res.error

    @pytest.mark.asyncio
    async def test_invoke_500_server_error(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        resp = _mock_response(500, text="internal")
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "groq_http_500" in res.error

    @pytest.mark.asyncio
    async def test_invoke_no_key_returns_placeholder(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        p = GroqProvider(api_key="")
        res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "missing_key" in res.error
        assert res.raw.get("mock") is True
        # Content should mention GROQ_API_KEY for diagnosability.
        assert "GROQ_API_KEY" in res.content

    @pytest.mark.asyncio
    async def test_invoke_network_error(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams

        # Simulate httpx.ConnectError by raising from post().
        ac_mock = MagicMock()
        ac_mock.__aenter__ = AsyncMock(return_value=ac_mock)
        ac_mock.__aexit__ = AsyncMock(return_value=None)

        async def raise_conn(*a, **kw):
            raise httpx.ConnectError("simulated dns failure")

        ac_mock.post = raise_conn
        with patch("httpx.AsyncClient", return_value=ac_mock):
            p = GroqProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "groq_http_error" in res.error
        assert "ConnectError" in res.error


# ─── 4. invoke_stream SSE chunks ───────────────────────────────────────────


class TestGroqInvokeStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams, ProviderChunk
        events = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello "}}]},
            {"choices": [{"index": 0, "delta": {"content": "world"}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        sse_body = _sse_lines(events)
        resp = _mock_response(200, content=sse_body,
                              headers={"content-type": "text/event-stream"})
        with _patch_async_client_stream([resp]):
            p = GroqProvider(api_key="sk-test")
            chunks: List[ProviderChunk] = []
            async for c in p.invoke_stream("hi", InvokeParams(stream=True)):
                chunks.append(c)
        # 3 deltas + [DONE] sentinel
        assert len(chunks) >= 3
        text = "".join(c.delta for c in chunks)
        assert "hello" in text and "world" in text
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_no_key_yields_placeholder(self):
        from providers.groq import GroqProvider
        from providers.base import InvokeParams
        p = GroqProvider(api_key="")
        chunks = [c async for c in p.invoke_stream("hi", InvokeParams())]
        assert len(chunks) == 1
        assert chunks[0].done is True
        assert chunks[0].finish_reason == "mock"


# ─── 5. health_check ────────────────────────────────────────────────────────


class TestGroqHealthCheck:
    @pytest.mark.asyncio
    async def test_health_no_key_placeholder(self):
        from providers.groq import GroqProvider
        from providers.base import HealthStatus
        p = GroqProvider(api_key="")
        h = await p.health_check()
        assert isinstance(h, HealthStatus)
        assert h.status == "placeholder"
        assert "GROQ_API_KEY" in h.error

    @pytest.mark.asyncio
    async def test_health_ok(self):
        from providers.groq import GroqProvider
        from providers.base import HealthStatus
        resp = _mock_response(200, json_data={"data": [{"id": "llama-3.1-70b-versatile"}]})
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-test")
            h = await p.health_check()
        assert h.status == "ok"
        assert h.provider == "groq"

    @pytest.mark.asyncio
    async def test_health_401(self):
        from providers.groq import GroqProvider
        resp = _mock_response(401, text="bad key")
        with _patch_async_client([resp]):
            p = GroqProvider(api_key="sk-bad")
            h = await p.health_check()
        assert h.status == "error"
        assert "groq_health_http_401" in h.error
