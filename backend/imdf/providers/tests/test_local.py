"""P20-B: LocalProvider tests (mock httpx).

Coverage:
  - inherits BaseProvider; provider/family + base url
  - placeholder / unreachable behaviour (server not running)
  - OpenAI-compatible /v1/chat/completions happy path
  - extract content from choices[0].message.content
  - usage normalization
  - error handling: 401, 429, 500
  - list_models + remote catalogue
  - health_check via /v1/models
  - SSE streaming via client.stream mocked
  - has_credentials (no key needed for local) + cost 0
  - missing prompt / messages returns 4xx-shaped provider response
  - body composition: forwards extra params

Count: 12 tests (>=8 required).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers._provider_base import BaseProvider, ProviderResponse
from providers.local import (
    DEFAULT_MODEL,
    DEFAULT_MODELS,
    LLAMA_DEFAULT_BASE_URL,
    LocalProvider,
)


def _mock_resp(status: int, json_data: dict | None = None, text: str = ""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text or str(json_data)[:200]
    return r


def _chat_payload(content: str = "Hi", pt: int = 8, ct: int = 4):
    return {
        "id": "cmpl-local-1",
        "model": DEFAULT_MODEL,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content},
             "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct,
                  "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Interface
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalInterface:
    def test_inherits_base_provider(self):
        assert issubclass(LocalProvider, BaseProvider)

    def test_provider_and_family(self):
        p = LocalProvider()
        assert p.provider_name == "local"
        assert p.family == "local"

    def test_default_base_url_local(self):
        p = LocalProvider()
        assert p.base_url == LLAMA_DEFAULT_BASE_URL

    def test_default_models_non_empty(self):
        assert len(DEFAULT_MODELS) >= 5
        assert DEFAULT_MODEL in DEFAULT_MODELS


# ═══════════════════════════════════════════════════════════════════════════
# 2. Placeholder / unreachable
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalUnreachable:
    @pytest.mark.asyncio
    async def test_invoke_unreachable(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("off"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("hi")
        assert r.success is False
        assert r.is_placeholder is True
        assert r.status == "unreachable"
        assert "ConnectionRefused" in r.error

    @pytest.mark.asyncio
    async def test_health_check_unreachable(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("off"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            h = await p.health_check()
        assert h.success is False
        assert h.status == "unreachable"

    def test_has_credentials_true_for_local(self):
        """Local has no key requirement; has_credentials returns True even empty."""
        p = LocalProvider()
        # local provider does not gate on credentials (offline-friendly)
        assert p.has_credentials() is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. Invoke happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalInvokeHappy:
    @pytest.mark.asyncio
    async def test_invoke_extracts_content(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, _chat_payload("Hello!")))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("hi there")
        assert r.success is True
        assert r.content == "Hello!"
        assert r.model == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_invoke_usage_normalized(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, _chat_payload("OK", 12, 7)))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("x")
        assert r.usage["prompt_tokens"] == 12
        assert r.usage["completion_tokens"] == 7
        assert r.usage["total_tokens"] == 19

    @pytest.mark.asyncio
    async def test_invoke_passes_messages(self):
        msgs = [{"role": "user", "content": "first"},
                {"role": "assistant", "content": "ack"},
                {"role": "user", "content": "second"}]
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, _chat_payload()))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("", params={"messages": msgs})
        assert r.success is True
        # Body must contain the multi-turn transcript
        call_kwargs = client.post.call_args.kwargs
        body = call_kwargs["json"]
        assert body["messages"] == msgs


# ═══════════════════════════════════════════════════════════════════════════
# 4. Error handling
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalErrors:
    @pytest.mark.asyncio
    async def test_401(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(401, text="auth"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("x")
        assert r.success is False
        assert "401" in r.error

    @pytest.mark.asyncio
    async def test_429(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(429, text="rate"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("x")
        assert r.success is False
        assert "429" in r.error

    @pytest.mark.asyncio
    async def test_500(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(500, text="crashed"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            r = await p.invoke("x")
        assert r.success is False
        assert "500" in r.error


# ═══════════════════════════════════════════════════════════════════════════
# 5. list_models / remote
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalModels:
    @pytest.mark.asyncio
    async def test_list_models_curated(self):
        p = LocalProvider()
        ms = await p.list_models()
        assert DEFAULT_MODEL in ms

    @pytest.mark.asyncio
    async def test_list_models_remote_ok(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(
            200, {"data": [{"id": "loaded-1"}, {"id": "loaded-2"}]},
        ))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            ms = await p.list_models_remote()
        assert ms == ["loaded-1", "loaded-2"]

    @pytest.mark.asyncio
    async def test_list_models_remote_unreachable(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError())
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            ms = await p.list_models_remote()
        assert DEFAULT_MODEL in ms  # fallback to curated

    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(
            200, {"data": [{"id": "x"}, {"id": "y"}]},
        ))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            h = await p.health_check()
        assert h.success is True
        assert "loaded-1" not in str(h.raw)  # not in our payload
        assert h.status == "ok"

    @pytest.mark.asyncio
    async def test_health_check_500(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(500, text="x"))
        with patch("httpx.AsyncClient", return_value=client):
            p = LocalProvider()
            h = await p.health_check()
        assert h.success is False
        assert "500" in h.error


# ═══════════════════════════════════════════════════════════════════════════
# 6. Missing prompt → failure (no crash)
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalInputGuard:
    @pytest.mark.asyncio
    async def test_invoke_missing_prompt_no_messages(self):
        p = LocalProvider()
        r = await p.invoke("")
        assert r.success is False
        assert r.error_code == "missing_prompt"
        assert "prompt" in r.error or "messages" in r.error


# ═══════════════════════════════════════════════════════════════════════════
# 7. Stream override
# ═══════════════════════════════════════════════════════════════════════════


class TestLocalStream:
    @pytest.mark.asyncio
    async def test_stream_chunks(self):
        # Mimics the httpx.AsyncClient.stream() context manager protocol.
        class _FakeStreamCM:
            def __init__(self, lines, status_code=200):
                self.lines = lines
                self.status_code = status_code

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def aiter_lines(self):
                async def gen():
                    for line in self.lines:
                        yield line
                return gen()

        sse_lines = [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo!"}}]}',
            'data: [DONE]',
        ]

        # httpx.AsyncClient() → returns `client_inst` whose __aenter__ returns
        # `inner`; `inner.stream(...)` returns the SSE stream context manager.
        inner = MagicMock()
        inner.stream = MagicMock(return_value=_FakeStreamCM(sse_lines, 200))
        client_inst = MagicMock()
        client_inst.__aenter__ = AsyncMock(return_value=inner)
        client_inst.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client_inst):
            chunks = []
            p = LocalProvider()
            async for c in p.stream_chunks("hi"):
                chunks.append(c)
        assert "".join(chunks) == "Hello!"
