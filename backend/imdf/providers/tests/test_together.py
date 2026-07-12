"""P20-A: TogetherProvider tests.

Covers invoke round-trip, list_models, health_check, error handling
(401/429/500), streaming chunk, and Pydantic v2 shape.

Same mock pattern as test_groq.py — patch httpx.AsyncClient via context
manager mock + AsyncMock.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ─── helpers (re-implemented to keep tests self-contained) ──────────────────


def _openai_chat_response(
    content: str = "Together says hi",
    model: str = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
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
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)


# ─── 1. Class shape ─────────────────────────────────────────────────────────


class TestTogetherShape:
    def test_inherits_baseprovider(self):
        from providers.base import BaseProvider
        from providers.together import TogetherProvider
        assert issubclass(TogetherProvider, BaseProvider)

    def test_provider_metadata(self):
        from providers.together import TogetherProvider
        p = TogetherProvider(api_key="x")
        assert p.provider_name == "together"
        assert p.family == "together"
        assert p.DEFAULT_BASE_URL == "https://api.together.xyz/v1"
        assert p.DEFAULT_MODEL == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"

    def test_api_key_from_env(self, monkeypatch):
        from providers.together import TogetherProvider
        monkeypatch.setenv("TOGETHER_API_KEY", "sk-tog-env")
        p = TogetherProvider()
        assert p.api_key == "sk-tog-env"

    def test_curated_model_set(self):
        from providers.together import TogetherProvider
        ids = TogetherProvider.DEFAULT_MODELS
        assert "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo" in ids
        assert "mistralai/Mixtral-8x7B-Instruct-v0.1" in ids
        assert "Qwen/Qwen2.5-72B-Instruct-Turbo" in ids


# ─── 2. list_models ─────────────────────────────────────────────────────────


class TestTogetherListModels:
    @pytest.mark.asyncio
    async def test_returns_curated_models(self):
        from providers.together import TogetherProvider
        p = TogetherProvider(api_key="x")
        models = await p.list_models()
        assert isinstance(models, list)
        assert "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo" in models
        assert "deepseek-ai/DeepSeek-V3" in models


# ─── 3. invoke round-trip + errors ──────────────────────────────────────────


class TestTogetherInvoke:
    @pytest.mark.asyncio
    async def test_invoke_success(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams, ProviderResponse
        body = _openai_chat_response("together hi", prompt_tokens=4, completion_tokens=8)
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert isinstance(res, ProviderResponse)
        assert res.success is True
        assert res.content == "together hi"
        assert res.provider == "together"
        assert res.usage["total_tokens"] == 12

    @pytest.mark.asyncio
    async def test_invoke_401(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams
        resp = _mock_response(401, text="bad key")
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-bad")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "together_http_401" in res.error

    @pytest.mark.asyncio
    async def test_invoke_429(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams
        resp = _mock_response(429, text="too many requests")
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "together_http_429" in res.error

    @pytest.mark.asyncio
    async def test_invoke_500(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams
        resp = _mock_response(500, text="internal")
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "together_http_500" in res.error

    @pytest.mark.asyncio
    async def test_invoke_no_key_placeholder(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams
        p = TogetherProvider(api_key="")
        res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "missing_key" in res.error
        assert res.raw.get("mock") is True
        assert "TOGETHER_API_KEY" in res.content


# ─── 4. invoke_stream ──────────────────────────────────────────────────────


class TestTogetherStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams, ProviderChunk
        events = [
            {"choices": [{"delta": {"content": "tog"}}]},
            {"choices": [{"delta": {"content": "ether"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        sse = _sse_lines(events)
        resp = _mock_response(200, content=sse, headers={"content-type": "text/event-stream"})
        with _patch_async_client_stream([resp]):
            p = TogetherProvider(api_key="sk-test")
            chunks: List[ProviderChunk] = []
            async for c in p.invoke_stream("hi", InvokeParams(stream=True)):
                chunks.append(c)
        text = "".join(c.delta for c in chunks)
        assert "tog" in text and "ether" in text
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_no_key_yields_placeholder(self):
        from providers.together import TogetherProvider
        from providers.base import InvokeParams
        p = TogetherProvider(api_key="")
        chunks = [c async for c in p.invoke_stream("hi", InvokeParams())]
        assert len(chunks) == 1
        assert chunks[0].finish_reason == "mock"


# ─── 5. health_check ────────────────────────────────────────────────────────


class TestTogetherHealthCheck:
    @pytest.mark.asyncio
    async def test_health_no_key(self):
        from providers.together import TogetherProvider
        from providers.base import HealthStatus
        p = TogetherProvider(api_key="")
        h = await p.health_check()
        assert isinstance(h, HealthStatus)
        assert h.status == "placeholder"
        assert "TOGETHER_API_KEY" in h.error

    @pytest.mark.asyncio
    async def test_health_ok(self):
        from providers.together import TogetherProvider
        resp = _mock_response(200, json_data=[{"id": "m1"}])
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-test")
            h = await p.health_check()
        assert h.status == "ok"
        assert h.provider == "together"

    @pytest.mark.asyncio
    async def test_health_500(self):
        from providers.together import TogetherProvider
        resp = _mock_response(500, text="server error")
        with _patch_async_client([resp]):
            p = TogetherProvider(api_key="sk-test")
            h = await p.health_check()
        assert h.status == "error"
        assert "together_health_http_500" in h.error
