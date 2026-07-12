"""P20-A: FireworksProvider tests.

Covers invoke round-trip, list_models, health_check, error handling
(401/429/500), streaming chunk, function-calling + JSON mode pass-through,
and Pydantic v2 shape.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _openai_chat_response(
    content: str = "Fireworks says hi",
    model: str = "accounts/fireworks/models/llama-v3p1-70b-instruct",
    prompt_tokens: int = 9,
    completion_tokens: int = 18,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-{model}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": msg,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _sse_lines(events: List[Dict[str, Any]]) -> bytes:
    parts: List[bytes] = []
    for ev in events:
        parts.append(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
    parts.append(b"data: [DONE]\n\n")
    return b"".join(parts)


def _mock_response(status: int = 200, json_data: Any = None, text: str = "",
                   content: bytes = b"", headers: Optional[Dict[str, str]] = None) -> MagicMock:
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
    ac = MagicMock()
    ac.__aenter__ = AsyncMock(return_value=ac)
    ac.__aexit__ = AsyncMock(return_value=None)
    it = iter(responses)

    async def fake_post(*a, **kw):
        try:
            return next(it)
        except StopIteration:
            return _mock_response(500, text="exhausted")

    async def fake_get(*a, **kw):
        try:
            return next(it)
        except StopIteration:
            return _mock_response(500, text="exhausted")

    ac.post = fake_post
    ac.get = fake_get
    return patch("httpx.AsyncClient", return_value=ac)


def _patch_async_client_stream(responses: List[MagicMock]) -> Any:
    ac = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    it = iter(responses)

    def fake_stream(method, url, **kwargs):
        try:
            resp = next(it)
        except StopIteration:
            resp = _mock_response(500, text="exhausted")
        cm.status_code = resp.status_code
        cm.headers = resp.headers
        cm.aread = resp.aread if hasattr(resp, "aread") else AsyncMock(return_value=b"")
        body_text = resp.content.decode("utf-8", errors="ignore") if hasattr(resp, "content") and resp.content else ""
        lines = body_text.split("\n")

        async def aiter_lines():
            for ln in lines:
                yield ln

        cm.aiter_lines = aiter_lines
        return cm

    ac.stream = fake_stream
    ac.__aenter__ = AsyncMock(return_value=ac)
    ac.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ac)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)


# ─── 1. Class shape ─────────────────────────────────────────────────────────


class TestFireworksShape:
    def test_inherits_baseprovider(self):
        from providers.base import BaseProvider
        from providers.fireworks import FireworksProvider
        assert issubclass(FireworksProvider, BaseProvider)

    def test_provider_metadata(self):
        from providers.fireworks import FireworksProvider
        p = FireworksProvider(api_key="x")
        assert p.provider_name == "fireworks"
        assert p.family == "fireworks"
        assert p.DEFAULT_BASE_URL == "https://api.fireworks.ai/inference/v1"
        assert p.DEFAULT_MODEL == "accounts/fireworks/models/llama-v3p1-70b-instruct"

    def test_api_key_from_env(self, monkeypatch):
        from providers.fireworks import FireworksProvider
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-env")
        p = FireworksProvider()
        assert p.api_key == "fw-env"

    def test_curated_models(self):
        from providers.fireworks import FireworksProvider
        ids = FireworksProvider.DEFAULT_MODELS
        assert "accounts/fireworks/models/llama-v3p1-70b-instruct" in ids
        assert "accounts/fireworks/models/llama-v3p1-70b-instruct-function-calling" in ids


# ─── 2. list_models ─────────────────────────────────────────────────────────


class TestFireworksListModels:
    @pytest.mark.asyncio
    async def test_returns_curated_models(self):
        from providers.fireworks import FireworksProvider
        p = FireworksProvider(api_key="x")
        models = await p.list_models()
        assert isinstance(models, list)
        assert len(models) >= 5
        assert "accounts/fireworks/models/mixtral-8x7b-instruct" in models


# ─── 3. invoke round-trip + function-call + JSON mode ──────────────────────


class TestFireworksInvoke:
    @pytest.mark.asyncio
    async def test_invoke_success(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams, ProviderResponse
        body = _openai_chat_response("fw ok", prompt_tokens=3, completion_tokens=6)
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            res = await p.invoke("hi", InvokeParams())
        assert isinstance(res, ProviderResponse)
        assert res.success is True
        assert res.content == "fw ok"
        assert res.provider == "fireworks"
        assert res.usage["total_tokens"] == 9

    @pytest.mark.asyncio
    async def test_invoke_function_calling(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        tool_calls = [
            {
                "id": "call_001",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "SF"}',
                },
            }
        ]
        body = _openai_chat_response("", tool_calls=tool_calls)
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            res = await p.invoke("weather SF", InvokeParams(
                extra={"tools": [{"type": "function",
                                  "function": {"name": "get_weather"}}]},
            ))
        assert res.success is True
        # raw should carry the tool_calls list.
        assert "tool_calls" in res.raw
        assert res.raw["tool_calls"][0]["function"]["name"] == "get_weather"

    @pytest.mark.asyncio
    async def test_invoke_json_mode(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        body = _openai_chat_response('{"answer": 42}')
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            res = await p.invoke("42?", InvokeParams(
                extra={"response_format": {"type": "json_object"}},
            ))
        assert res.success is True
        assert '"answer"' in res.content

    @pytest.mark.asyncio
    async def test_invoke_401(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        resp = _mock_response(401, text="unauthorized")
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-bad")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "fireworks_http_401" in res.error

    @pytest.mark.asyncio
    async def test_invoke_429(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        resp = _mock_response(429, text="slow down")
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "fireworks_http_429" in res.error

    @pytest.mark.asyncio
    async def test_invoke_500(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        resp = _mock_response(500, text="oops")
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "fireworks_http_500" in res.error

    @pytest.mark.asyncio
    async def test_invoke_no_key_placeholder(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        p = FireworksProvider(api_key="")
        res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "missing_key" in res.error
        assert "FIREWORKS_API_KEY" in res.content


# ─── 4. invoke_stream ──────────────────────────────────────────────────────


class TestFireworksStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams, ProviderChunk
        events = [
            {"choices": [{"delta": {"content": "fire"}}]},
            {"choices": [{"delta": {"content": "works"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        sse = _sse_lines(events)
        resp = _mock_response(200, content=sse, headers={"content-type": "text/event-stream"})
        with _patch_async_client_stream([resp]):
            p = FireworksProvider(api_key="fw-test")
            chunks: List[ProviderChunk] = []
            async for c in p.invoke_stream("hi", InvokeParams(stream=True)):
                chunks.append(c)
        text = "".join(c.delta for c in chunks)
        assert "fire" in text and "works" in text
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_no_key_placeholder(self):
        from providers.fireworks import FireworksProvider
        from providers.base import InvokeParams
        p = FireworksProvider(api_key="")
        chunks = [c async for c in p.invoke_stream("hi", InvokeParams())]
        assert len(chunks) == 1
        assert chunks[0].finish_reason == "mock"


# ─── 5. health_check ────────────────────────────────────────────────────────


class TestFireworksHealthCheck:
    @pytest.mark.asyncio
    async def test_health_no_key(self):
        from providers.fireworks import FireworksProvider
        from providers.base import HealthStatus
        p = FireworksProvider(api_key="")
        h = await p.health_check()
        assert isinstance(h, HealthStatus)
        assert h.status == "placeholder"

    @pytest.mark.asyncio
    async def test_health_ok(self):
        from providers.fireworks import FireworksProvider
        resp = _mock_response(200, json_data={"models": []})
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            h = await p.health_check()
        assert h.status == "ok"
        assert h.provider == "fireworks"

    @pytest.mark.asyncio
    async def test_health_500(self):
        from providers.fireworks import FireworksProvider
        resp = _mock_response(500, text="oops")
        with _patch_async_client([resp]):
            p = FireworksProvider(api_key="fw-test")
            h = await p.health_check()
        assert h.status == "error"
        assert "fireworks_health_http_500" in h.error
