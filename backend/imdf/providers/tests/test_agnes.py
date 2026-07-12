"""P20-A: AgnesProvider tests (refactored to BaseProvider pattern).

Covers the new P20-A API:
- Inherits BaseProvider
- list_models returns chat models
- health_check (no key → placeholder, with key → 200/4xx paths)
- invoke round-trip (200 + 401 + 429 + 500 + httpx error)
- invoke_stream yields SSE-style chunks
- Pydantic v2 ProviderResponse shape
- Multi-modal methods (image / video / drama) preserved
- has_credentials / is_placeholder_mode / cost_estimate_usd
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _openai_chat_response(
    content: str = "Agnes says hi",
    model: str = "agnes-2.0-flash",
    prompt_tokens: int = 4,
    completion_tokens: int = 8,
) -> Dict[str, Any]:
    return {
        "id": f"agnes-{model}",
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
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_CHAT_BASE_URL", raising=False)


# ─── 1. Class shape ─────────────────────────────────────────────────────────


class TestAgnesShape:
    def test_inherits_baseprovider(self):
        from providers.base import BaseProvider
        from providers.agnes import AgnesProvider
        assert issubclass(AgnesProvider, BaseProvider)

    def test_provider_metadata(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="x")
        assert p.provider_name == "agnes"
        assert p.family == "agnes"
        assert p.DEFAULT_MODEL == "agnes-2.0-flash"
        # chat_base_url is separate (legacy platform endpoint)
        assert "agnes-ai" in p.chat_base_url

    def test_api_key_from_env(self, monkeypatch):
        from providers.agnes import AgnesProvider
        monkeypatch.setenv("AGNES_API_KEY", "agnes-env")
        p = AgnesProvider()
        assert p.api_key == "agnes-env"

    def test_is_placeholder_mode(self):
        from providers.agnes import AgnesProvider
        assert AgnesProvider(api_key="").is_placeholder_mode() is True
        assert AgnesProvider(api_key="x").is_placeholder_mode() is False

    def test_has_credentials(self):
        from providers.agnes import AgnesProvider
        assert AgnesProvider(api_key="x").has_credentials() is True
        assert AgnesProvider(api_key="").has_credentials() is False

    def test_cost_is_zero(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="x")
        assert p.cost_estimate_usd(1_000_000, 1_000_000) == 0.0
        assert p.cost_estimate_usd(0, 0) == 0.0


# ─── 2. list_models ─────────────────────────────────────────────────────────


class TestAgnesListModels:
    @pytest.mark.asyncio
    async def test_returns_chat_models(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="x")
        models = await p.list_models()
        assert "agnes-2.0-flash" in models

    def test_list_all_models_includes_multimodal(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="x")
        all_models = p.list_all_models()
        assert "agnes-2.0-flash" in all_models
        assert "agnes-image-2.1-flash" in all_models
        assert "agnes-video-2.0" in all_models
        assert "agnes-drama-1.0" in all_models

    def test_get_models_includes_capabilities(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="x")
        descs = p.get_models()
        ids = {d["id"] for d in descs}
        assert "agnes-2.0-flash" in ids
        # Image/video/drama have non-chat capability tags
        caps_by_id = {d["id"]: d.get("capabilities", []) for d in descs}
        assert "image" in caps_by_id["agnes-image-2.1-flash"]
        assert "video" in caps_by_id["agnes-video-2.0"]
        assert "drama" in caps_by_id["agnes-drama-1.0"]


# ─── 3. invoke round-trip + error handling ──────────────────────────────────


class TestAgnesInvoke:
    @pytest.mark.asyncio
    async def test_invoke_success(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams, ProviderResponse
        body = _openai_chat_response("hello agnes")
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            res = await p.invoke("hi", InvokeParams())
        assert isinstance(res, ProviderResponse)
        assert res.success is True
        assert res.content == "hello agnes"
        assert res.provider == "agnes"
        assert res.usage["total_tokens"] == 12

    @pytest.mark.asyncio
    async def test_invoke_401(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams
        resp = _mock_response(401, text="unauthorized")
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-bad")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "agnes_http_401" in res.error

    @pytest.mark.asyncio
    async def test_invoke_429(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams
        resp = _mock_response(429, text="slow down")
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "agnes_http_429" in res.error

    @pytest.mark.asyncio
    async def test_invoke_500(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams
        resp = _mock_response(500, text="oops")
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "agnes_http_500" in res.error

    @pytest.mark.asyncio
    async def test_invoke_no_key_placeholder(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams
        p = AgnesProvider(api_key="")
        res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "missing_key" in res.error
        assert res.raw.get("mock") is True
        assert "AGNES_API_KEY" in res.content


# ─── 4. invoke_stream ──────────────────────────────────────────────────────


class TestAgnesStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams, ProviderChunk
        events = [
            {"choices": [{"delta": {"content": "ag"}}]},
            {"choices": [{"delta": {"content": "nes"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        sse = _sse_lines(events)
        resp = _mock_response(200, content=sse, headers={"content-type": "text/event-stream"})
        with _patch_async_client_stream([resp]):
            p = AgnesProvider(api_key="agnes-test")
            chunks: List[ProviderChunk] = []
            async for c in p.invoke_stream("hi", InvokeParams(stream=True)):
                chunks.append(c)
        text = "".join(c.delta for c in chunks)
        assert "ag" in text and "nes" in text
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_no_key_placeholder(self):
        from providers.agnes import AgnesProvider
        from providers.base import InvokeParams
        p = AgnesProvider(api_key="")
        chunks = [c async for c in p.invoke_stream("hi", InvokeParams())]
        assert len(chunks) == 1
        assert chunks[0].finish_reason == "mock"


# ─── 5. health_check ────────────────────────────────────────────────────────


class TestAgnesHealthCheck:
    @pytest.mark.asyncio
    async def test_health_no_key_placeholder(self):
        from providers.agnes import AgnesProvider
        from providers.base import HealthStatus
        p = AgnesProvider(api_key="")
        h = await p.health_check()
        assert isinstance(h, HealthStatus)
        assert h.status == "placeholder"
        assert "AGNES_API_KEY" in h.error

    @pytest.mark.asyncio
    async def test_health_ok(self):
        from providers.agnes import AgnesProvider
        resp = _mock_response(200, json_data={"data": [{"id": "agnes-2.0-flash"}]})
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            h = await p.health_check()
        assert h.status == "ok"
        assert h.provider == "agnes"

    @pytest.mark.asyncio
    async def test_health_500(self):
        from providers.agnes import AgnesProvider
        resp = _mock_response(500, text="oops")
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            h = await p.health_check()
        assert h.status == "error"
        assert "agnes_health_http_500" in h.error


# ─── 6. Multi-modal extensions ─────────────────────────────────────────────


class TestAgnesMultimodal:
    @pytest.mark.asyncio
    async def test_generate_image_no_key(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="")
        r = await p.generate_image("a cat")
        assert r["success"] is False
        assert r.get("mock") is True
        assert "placeholder_url" in r

    @pytest.mark.asyncio
    async def test_generate_image_success(self):
        from providers.agnes import AgnesProvider
        resp = _mock_response(200, json_data={"data": [{"url": "https://agnes.cdn/x.png"}]})
        with _patch_async_client([resp]):
            p = AgnesProvider(api_key="agnes-test")
            r = await p.generate_image("a cat")
        assert r["success"] is True
        assert r["urls"] == ["https://agnes.cdn/x.png"]

    @pytest.mark.asyncio
    async def test_generate_video_no_key(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="")
        r = await p.generate_video("sunset")
        assert r["success"] is False
        assert r.get("mock") is True

    @pytest.mark.asyncio
    async def test_generate_drama_no_key(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="")
        r = await p.generate_drama("romance")
        assert r["success"] is False
        assert r.get("mock") is True
