"""P20-A: PerplexityProvider tests.

Covers invoke round-trip, list_models, health_check, error handling
(401/429/500), streaming chunk, citation extraction, and search
augmentation pass-through.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _perplexity_chat_response(
    content: str = "Perplexity says hi with citations [1].",
    model: str = "llama-3.1-sonar-small-128k-online",
    prompt_tokens: int = 7,
    completion_tokens: int = 14,
    citations: Optional[List[str]] = None,
    search_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "id": f"pplx-{model}",
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
        "citations": citations or [
            "https://en.wikipedia.org/wiki/Test",
            "https://example.com/article",
        ],
        "search_results": search_results or [
            {"title": "Test article", "url": "https://en.wikipedia.org/wiki/Test",
             "date": "2025-01-01"},
        ],
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
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)


# ─── 1. Class shape ─────────────────────────────────────────────────────────


class TestPerplexityShape:
    def test_inherits_baseprovider(self):
        from providers.base import BaseProvider
        from providers.perplexity import PerplexityProvider
        assert issubclass(PerplexityProvider, BaseProvider)

    def test_provider_metadata(self):
        from providers.perplexity import PerplexityProvider
        p = PerplexityProvider(api_key="x")
        assert p.provider_name == "perplexity"
        assert p.family == "perplexity"
        assert p.DEFAULT_BASE_URL == "https://api.perplexity.ai"
        assert p.DEFAULT_MODEL == "llama-3.1-sonar-small-128k-online"

    def test_api_key_from_env(self, monkeypatch):
        from providers.perplexity import PerplexityProvider
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-env")
        p = PerplexityProvider()
        assert p.api_key == "pplx-env"

    def test_curated_online_and_offline_models(self):
        from providers.perplexity import PerplexityProvider
        ids = PerplexityProvider.DEFAULT_MODELS
        # Online models
        assert "llama-3.1-sonar-large-128k-online" in ids
        # Offline chat models
        assert "llama-3.1-70b-instruct" in ids


# ─── 2. list_models ─────────────────────────────────────────────────────────


class TestPerplexityListModels:
    @pytest.mark.asyncio
    async def test_returns_curated_models(self):
        from providers.perplexity import PerplexityProvider
        p = PerplexityProvider(api_key="x")
        models = await p.list_models()
        assert isinstance(models, list)
        assert "llama-3.1-sonar-small-128k-online" in models
        assert "llama-3.1-sonar-huge-128k-online" in models


# ─── 3. invoke + citations ──────────────────────────────────────────────────


class TestPerplexityInvoke:
    @pytest.mark.asyncio
    async def test_invoke_success_with_citations(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams, ProviderResponse
        body = _perplexity_chat_response("pplx answer")
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            res = await p.invoke("hi", InvokeParams())
        assert isinstance(res, ProviderResponse)
        assert res.success is True
        assert res.provider == "perplexity"
        assert res.content == "pplx answer"
        # Citations / search_results flow into raw.
        assert "citations" in res.raw
        assert len(res.raw["citations"]) == 2
        assert "search_results" in res.raw

    @pytest.mark.asyncio
    async def test_invoke_search_options(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        body = _perplexity_chat_response("ok")
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            res = await p.invoke("hi", InvokeParams(extra={
                "search_recency_filter": "week",
                "search_domain_filter": ["-reddit.com"],
                "return_citations": True,
            }))
        assert res.success is True

    @pytest.mark.asyncio
    async def test_invoke_401(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        resp = _mock_response(401, text="unauthorized")
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-bad")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "perplexity_http_401" in res.error

    @pytest.mark.asyncio
    async def test_invoke_429(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        resp = _mock_response(429, text="too many")
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "perplexity_http_429" in res.error

    @pytest.mark.asyncio
    async def test_invoke_500(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        resp = _mock_response(500, text="server error")
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "perplexity_http_500" in res.error

    @pytest.mark.asyncio
    async def test_invoke_no_key_placeholder(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        p = PerplexityProvider(api_key="")
        res = await p.invoke("hi", InvokeParams())
        assert res.success is False
        assert "missing_key" in res.error
        assert res.raw.get("mock") is True


# ─── 4. invoke_stream ──────────────────────────────────────────────────────


class TestPerplexityStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams, ProviderChunk
        events = [
            {"choices": [{"delta": {"content": "ppl"}}]},
            {"choices": [{"delta": {"content": "x"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        sse = _sse_lines(events)
        resp = _mock_response(200, content=sse, headers={"content-type": "text/event-stream"})
        with _patch_async_client_stream([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            chunks: List[ProviderChunk] = []
            async for c in p.invoke_stream("hi", InvokeParams(stream=True)):
                chunks.append(c)
        text = "".join(c.delta for c in chunks)
        assert "ppl" in text and "x" in text
        assert chunks[-1].done is True

    @pytest.mark.asyncio
    async def test_stream_no_key_placeholder(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import InvokeParams
        p = PerplexityProvider(api_key="")
        chunks = [c async for c in p.invoke_stream("hi", InvokeParams())]
        assert len(chunks) == 1
        assert chunks[0].finish_reason == "mock"


# ─── 5. health_check ────────────────────────────────────────────────────────


class TestPerplexityHealthCheck:
    @pytest.mark.asyncio
    async def test_health_no_key(self):
        from providers.perplexity import PerplexityProvider
        from providers.base import HealthStatus
        p = PerplexityProvider(api_key="")
        h = await p.health_check()
        assert isinstance(h, HealthStatus)
        assert h.status == "placeholder"
        assert "PERPLEXITY_API_KEY" in h.error

    @pytest.mark.asyncio
    async def test_health_ok(self):
        from providers.perplexity import PerplexityProvider
        # Perplexity doesn't have /models — health uses a tiny chat call.
        body = _perplexity_chat_response("ok", prompt_tokens=1, completion_tokens=1)
        resp = _mock_response(200, json_data=body)
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            h = await p.health_check()
        assert h.status == "ok"
        assert h.provider == "perplexity"

    @pytest.mark.asyncio
    async def test_health_500(self):
        from providers.perplexity import PerplexityProvider
        resp = _mock_response(500, text="oops")
        with _patch_async_client([resp]):
            p = PerplexityProvider(api_key="pplx-test")
            h = await p.health_check()
        assert h.status == "error"
        assert "perplexity_health_http_500" in h.error
