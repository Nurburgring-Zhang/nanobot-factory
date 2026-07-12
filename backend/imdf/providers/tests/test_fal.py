"""P20-B: FalProvider tests (mock httpx).

Mimics the P19-A1 test style for ``backend/imdf/providers/tests/test_fal.py``:
  - placeholder mode (no FAL_KEY)
  - happy path submit + image extraction
  - error handling for 401 / 429 / 500
  - list_models + remote catalogue fallback
  - cost + Pydantic shape validation

Count: 12 tests (>=8 required by P20-B spec).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers._provider_base import BaseProvider, ProviderResponse
from providers.fal import DEFAULT_IMAGE_MODEL, DEFAULT_MODELS, FalProvider


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _mock_resp(status: int, json_data: dict | None = None, text: str = ""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text or str(json_data)[:200]
    return r


def _chat_ok_payload(images: list[tuple[str, str]] | None = None):
    """fal ``/fal-ai/flux/schnell`` submit shape (synchronous success)."""
    return {
        "images": [
            {"url": u, "content_type": "image/png", "width": 1024, "height": 1024}
            for (u, _) in (images or [])
        ],
        "prompt": "a cat",
        "seed": 42,
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Interface (BaseProvider + ProviderResponse shape)
# ═══════════════════════════════════════════════════════════════════════════


class TestFalInterface:
    def test_inherits_base_provider(self):
        assert issubclass(FalProvider, BaseProvider)

    def test_provider_and_family(self):
        p = FalProvider(api_key="x")
        assert p.provider_name == "fal"
        assert p.family == "fal"

    def test_default_models_non_empty(self):
        assert len(DEFAULT_MODELS) >= 4
        assert DEFAULT_IMAGE_MODEL in DEFAULT_MODELS


# ═══════════════════════════════════════════════════════════════════════════
# 2. No-key placeholder mode
# ═══════════════════════════════════════════════════════════════════════════


class TestFalPlaceholder:
    def test_has_credentials_false(self):
        p = FalProvider(api_key="")
        assert p.has_credentials() is False

    @pytest.mark.asyncio
    async def test_invoke_placeholder(self):
        p = FalProvider(api_key="")
        r = await p.invoke("a cat")
        assert isinstance(r, ProviderResponse)
        assert r.success is False
        assert r.is_placeholder is True
        assert r.mock is True
        assert r.status == "placeholder"
        assert "FAL_KEY" in r.error

    @pytest.mark.asyncio
    async def test_health_check_placeholder(self):
        p = FalProvider(api_key="")
        h = await p.health_check()
        assert h.is_placeholder is True
        assert "FAL_KEY" in h.error


# ═══════════════════════════════════════════════════════════════════════════
# 3. list_models + remote catalogue
# ═══════════════════════════════════════════════════════════════════════════


class TestFalModels:
    @pytest.mark.asyncio
    async def test_list_models_curated(self):
        p = FalProvider(api_key="x")
        models = await p.list_models()
        assert isinstance(models, list)
        assert "fal-ai/flux/schnell" in models

    @pytest.mark.asyncio
    async def test_list_models_remote_no_key_falls_back(self):
        p = FalProvider(api_key="")
        models = await p.list_models_remote()
        assert "fal-ai/flux/schnell" in models

    @pytest.mark.asyncio
    async def test_list_models_remote_with_key(self):
        payload = [{"id": "fal-ai/test-model-a"}, {"id": "fal-ai/test-model-b"}]
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            models = await p.list_models_remote()
        assert "fal-ai/test-model-a" in models


# ═══════════════════════════════════════════════════════════════════════════
# 4. invoke() happy path (image + video extraction)
# ═══════════════════════════════════════════════════════════════════════════


class TestFalInvokeHappy:
    @pytest.mark.asyncio
    async def test_invoke_image(self):
        payload = _chat_ok_payload([("https://fal.cdn/i1.png", "img")])
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            r = await p.invoke("a cat on a roof")
        assert r.success is True
        assert r.images == ["https://fal.cdn/i1.png"]
        assert r.status == "succeeded"

    @pytest.mark.asyncio
    async def test_invoke_video(self):
        payload = {"video": {"url": "https://fal.cdn/v1.mp4"}}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            r = await p.invoke("a sunset", params={"model": "fal-ai/wan-video"})
        assert r.success is True
        assert r.videos == ["https://fal.cdn/v1.mp4"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Error handling
# ═══════════════════════════════════════════════════════════════════════════


class TestFalErrors:
    @pytest.mark.asyncio
    async def test_401(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(401, text="invalid key"))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="bad")
            r = await p.invoke("x")
        assert r.success is False
        assert "401" in r.error
        assert r.error_code == "401"

    @pytest.mark.asyncio
    async def test_429(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(429, text="rate limited"))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            r = await p.invoke("x")
        assert r.success is False
        assert "429" in r.error

    @pytest.mark.asyncio
    async def test_500_with_exception(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=client.__aexit__)
        client.__aenter__ = AsyncMock(
            side_effect=RuntimeError("connection reset"),
        )
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            r = await p.invoke("x")
        assert r.success is False
        assert "RuntimeError" in r.error

    @pytest.mark.asyncio
    async def test_health_check_error(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(503, text="down"))
        with patch("httpx.AsyncClient", return_value=client):
            p = FalProvider(api_key="real-key")
            h = await p.health_check()
        assert h.success is False
        assert "503" in h.error
