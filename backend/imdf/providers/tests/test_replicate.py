"""P20-B: ReplicateProvider tests (mock httpx).

Coverage:
  - interface inherits BaseProvider
  - placeholder mode (no REPLICATE_API_TOKEN)
  - list_models (curated) + remote catalogue
  - invoke sync-returning model (output inline)
  - invoke async model: submit + /predictions/{id} polling until succeeded
  - error handling: failed / canceled / 4xx / 5xx
  - extract_media (image vs video URL heuristic)
  - extract_text from list output
  - kind_of heuristic

Count: 12 tests (>=8 required).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers._provider_base import BaseProvider, ProviderResponse
from providers.replicate import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_MODELS,
    ReplicateProvider,
)


def _mock_resp(status: int, json_data: dict | None = None, text: str = ""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text or str(json_data)[:200]
    return r


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Interface
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateInterface:
    def test_inherits_base_provider(self):
        assert issubclass(ReplicateProvider, BaseProvider)

    def test_provider_and_family(self):
        p = ReplicateProvider(api_key="x")
        assert p.provider_name == "replicate"
        assert p.family == "replicate"

    def test_default_models_have_chat_and_image(self):
        ids = set(DEFAULT_MODELS)
        assert any(m for m in ids if "llama" in m)
        assert any(m for m in ids if "flux" in m or "sdxl" in m)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Placeholder mode
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicatePlaceholder:
    def test_has_no_creds(self):
        p = ReplicateProvider(api_key="")
        assert p.has_credentials() is False

    @pytest.mark.asyncio
    async def test_invoke_placeholder(self):
        p = ReplicateProvider(api_key="")
        r = await p.invoke("hi")
        assert isinstance(r, ProviderResponse)
        assert r.success is False
        assert r.is_placeholder is True
        assert r.mock is True
        assert "REPLICATE_API_TOKEN" in r.error

    @pytest.mark.asyncio
    async def test_health_check_placeholder(self):
        p = ReplicateProvider(api_key="")
        h = await p.health_check()
        assert h.is_placeholder is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. List models
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateModels:
    @pytest.mark.asyncio
    async def test_list_models_curated(self):
        p = ReplicateProvider(api_key="x")
        ms = await p.list_models()
        assert DEFAULT_CHAT_MODEL in ms

    @pytest.mark.asyncio
    async def test_list_models_remote(self):
        payload = {
            "results": [
                {"owner": "openai", "name": "whisper"},
                {"owner": "x", "name": "y"},
            ],
        }
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=client):
            p = ReplicateProvider(api_key="real")
            ms = await p.list_models_remote(limit=5)
        assert "openai/whisper" in ms


# ═══════════════════════════════════════════════════════════════════════════
# 4. Invoke — async model (submit + poll until succeeded)
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateInvokeAsync:
    @pytest.mark.asyncio
    async def test_invoke_async_polling_succeeded(self):
        submit_payload = {"id": "pred-001", "status": "starting"}
        status_payloads = [
            {"id": "pred-001", "status": "processing"},
            {
                "id": "pred-001",
                "status": "succeeded",
                "output": ["https://r8.cdn/img.png", "https://r8.cdn/img2.png"],
            },
        ]
        call_count = {"n": 0}

        def _get_side_effect(*a, **kw):
            call_count["n"] += 1
            return _mock_resp(200, status_payloads[min(1, call_count["n"] - 1)])

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(202, submit_payload))
        client.get = AsyncMock(side_effect=_get_side_effect)

        with patch("httpx.AsyncClient", return_value=client), \
             patch("providers.replicate.asyncio.sleep", new=AsyncMock()):
            p = ReplicateProvider(api_key="real", timeout=30)
            r = await p.invoke("a cat", params={"model": "stability-ai/sdxl"})
        assert r.success is True
        assert r.task_id == "pred-001"
        assert "https://r8.cdn/img.png" in r.images
        assert r.status == "succeeded"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Invoke — sync (inline output)
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateInvokeSync:
    @pytest.mark.asyncio
    async def test_invoke_sync_inline(self):
        submit_payload = {"id": "pred-007", "output": ["Hello!"]}
        client = AsyncMock()
        client.post = AsyncMock(return_value=_mock_resp(200, submit_payload))
        # Use AsyncMock as ctx manager directly so httpx.AsyncClient() works
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=client)
        client_cm.__aexit__ = AsyncMock(return_value=None)
        client_cm.post = AsyncMock(return_value=_mock_resp(200, submit_payload))
        with patch("httpx.AsyncClient", return_value=client_cm):
            p = ReplicateProvider(api_key="real")
            r = await p.invoke("hello", params={"model": "meta/meta-llama-3-8b-instruct"})
        assert r.success is True
        assert r.content == "Hello!"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Errors
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateErrors:
    @pytest.mark.asyncio
    async def test_500(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(500, text="boom"))
        with patch("httpx.AsyncClient", return_value=client):
            p = ReplicateProvider(api_key="real")
            r = await p.invoke("x")
        assert r.success is False
        assert "500" in r.error

    @pytest.mark.asyncio
    async def test_polling_failed_status(self):
        submit_payload = {"id": "pred-002", "status": "starting"}
        status_payloads = [
            {"id": "pred-002", "status": "processing"},
            {"id": "pred-002", "status": "failed", "error": "nsfw detected"},
        ]
        n = {"i": 0}

        def _side(*a, **kw):
            n["i"] += 1
            return _mock_resp(200, status_payloads[min(1, n["i"] - 1)])

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(202, submit_payload))
        client.get = AsyncMock(side_effect=_side)
        with patch("httpx.AsyncClient", return_value=client), \
             patch("providers.replicate.asyncio.sleep", new=AsyncMock()):
            p = ReplicateProvider(api_key="real")
            r = await p.invoke("x")
        assert r.success is False
        assert "nsfw detected" in r.error
        assert r.task_id == "pred-002"
        assert r.status == "failed"

    @pytest.mark.asyncio
    async def test_health_check_500(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(500, text="x"))
        with patch("httpx.AsyncClient", return_value=client):
            p = ReplicateProvider(api_key="real")
            h = await p.health_check()
        assert h.success is False
        assert "500" in h.error


# ═══════════════════════════════════════════════════════════════════════════
# 7. Extract helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestReplicateHelpers:
    def test_extract_media_image_vs_video(self):
        from providers.replicate import ReplicateProvider as _P
        payload = {"output": [
            "https://r8.cdn/a.png",
            "https://r8.cdn/b.mp4",
            "https://r8.cdn/c.jpg",
            "https://r8.cdn/d.webm",
        ]}
        imgs, vids = _P._extract_media(payload)
        assert "https://r8.cdn/a.png" in imgs
        assert "https://r8.cdn/c.jpg" in imgs
        assert "https://r8.cdn/b.mp4" in vids
        assert "https://r8.cdn/d.webm" in vids

    def test_extract_text_from_list(self):
        from providers.replicate import ReplicateProvider as _P
        text = _P._extract_text({"output": ["hi", "there"]})
        assert "hi" in text and "there" in text

    def test_kind_of(self):
        from providers.replicate import ReplicateProvider as _P
        assert _P._kind_of("meta/meta-llama-3") == "chat"
        assert _P._kind_of("black-forest-labs/flux-schnell") == "image"
        assert _P._kind_of("stability-ai/stable-video-diffusion") == "video"
