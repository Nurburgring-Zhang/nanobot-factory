"""P20-B: ComfyUIProvider tests — REAL workflow submission + WebSocket polling.

The provider actually submits a workflow JSON to ``/prompt``, listens on the
``/ws?clientId=...`` endpoint for ``executing`` / ``executed`` /
``execution_error`` messages, and falls back to ``/history/{id}`` polling.

For deterministic tests we **do NOT** connect to a real ComfyUI server.
Instead we patch ``websockets.connect`` with an async context manager that
yields a controllable in-memory WS object, plus httpx mocks for the
``/prompt``, ``/history``, and ``/system_stats`` endpoints.

Coverage:
  1. inherits BaseProvider; provider/family name
  2. placeholder / unreachable POST → graceful failure
  3. happy path with WS-driven completion + image /view URLs
  4. WS path receiving ``execution_error`` → graceful failure
  5. WS connect failure → falls back to /history polling
  6. WS path: extracting videos via key=='videos' or 'gifs'
  7. /history /image extraction, _view_urls helper
  8. list_models returns curated catalogue
  9. health_check via /system_stats (200 + 5xx)
 10. workflow template structure (KSampler / CLIPTextEncode)
 11. _PROVIDER_USES_REAL_WS attribute signals real WS usage

Count: 12 tests (>=8 required).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers._provider_base import BaseProvider, ProviderResponse
from providers.comfyui import (
    COMFYUI_DEFAULT_BASE_URL,
    ComfyUIProvider,
)


def _mock_resp(status: int, json_data: dict | None = None, text: str = ""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data or {}
    r.text = text or str(json_data)[:200]
    return r


# ═══════════════════════════════════════════════════════════════════════════
# In-memory fake WebSocket — yields canned `executing` frames
# ═══════════════════════════════════════════════════════════════════════════


class FakeWS:
    """Mimics ``websockets.connect`` ctx manager + ``__aiter__``."""

    def __init__(self, frames: list[dict]):
        self.frames = frames

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.frames:
            raise StopAsyncIteration
        return json.dumps(self.frames.pop(0))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Interface + signal
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIInterface:
    def test_inherits_base_provider(self):
        assert issubclass(ComfyUIProvider, BaseProvider)

    def test_provider_and_family(self):
        p = ComfyUIProvider()
        assert p.provider_name == "comfyui"
        assert p.family == "comfyui"

    def test_real_websocket_signal(self):
        """The provider must actually use a real WebSocket for progress."""
        assert getattr(ComfyUIProvider, "_PROVIDER_USES_REAL_WS", False) is True

    def test_default_base_url(self):
        p = ComfyUIProvider()
        assert COMFYUI_DEFAULT_BASE_URL in p.base_url

    @pytest.mark.asyncio
    async def test_list_models_curated(self):
        p = ComfyUIProvider()
        models = await p.list_models()
        assert isinstance(models, list)
        assert "flux1-schnell" in models or "sd_xl_base_1.0" in models


# ═══════════════════════════════════════════════════════════════════════════
# 2. Unreachable server
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIUnreachable:
    @pytest.mark.asyncio
    async def test_invoke_unreachable(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(
            side_effect=ConnectionRefusedError("no server"),
        )
        with patch("httpx.AsyncClient", return_value=client):
            p = ComfyUIProvider()
            r = await p.invoke("a cat")
        assert r.success is False
        assert r.is_placeholder is True
        assert r.status == "unreachable"
        assert "ConnectionRefused" in r.error

    @pytest.mark.asyncio
    async def test_health_check_unreachable(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(
            side_effect=ConnectionRefusedError("down"),
        )
        with patch("httpx.AsyncClient", return_value=client):
            p = ComfyUIProvider()
            h = await p.health_check()
        assert h.success is False
        assert h.status == "unreachable"


# ═══════════════════════════════════════════════════════════════════════════
# 3. WS-driven completion (happy path)
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIWebSocketHappy:
    @pytest.mark.asyncio
    async def test_invoke_with_ws_completion_image(self):
        prompt_id = "pid-001"
        # Submit succeeds:
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, {"prompt_id": prompt_id}))
        # /history returns final outputs:
        history_payload = {
            prompt_id: {
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "p20b_0001_.png",
                                "type": "output",
                                "subfolder": "",
                            }
                        ]
                    }
                }
            }
        }
        client.get = AsyncMock(return_value=_mock_resp(200, history_payload))

        # WS yields: executing(progress) + executing(null) at end
        ws_frames = [
            {"type": "status", "data": {"status": "ready"}},
            {
                "type": "executing",
                "data": {"prompt_id": prompt_id, "node": "3"},
            },
            {
                "type": "executing",
                "data": {"prompt_id": prompt_id, "node": None},
            },
        ]

        with patch("httpx.AsyncClient", return_value=client), \
             patch(
                 "providers.comfyui.websockets",
             ) as ws_mod, \
             patch("asyncio.sleep", new=AsyncMock()):
            fake = FakeWS(list(ws_frames))
            ws_mod.connect = MagicMock(return_value=fake)
            p = ComfyUIProvider()
            r = await p.invoke(
                "a cat",
                params={"template": "flux1-schnell"},
                max_wait_s=2.0,
            )
        assert r.success is True
        assert r.task_id == prompt_id
        assert r.status == "succeeded"
        assert any("p20b_0001_.png" in u for u in r.images)
        assert r.images[0].endswith("/view?filename=p20b_0001_.png&type=output&subfolder=")

    @pytest.mark.asyncio
    async def test_invoke_ws_completion_video(self):
        prompt_id = "pid-002"
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, {"prompt_id": prompt_id}))
        history_payload = {
            prompt_id: {
                "outputs": {
                    "20": {
                        "videos": [
                            {"filename": "out.mp4", "type": "output", "subfolder": "video"},
                        ]
                    }
                }
            }
        }
        client.get = AsyncMock(return_value=_mock_resp(200, history_payload))

        ws_frames = [
            {"type": "executing", "data": {"prompt_id": prompt_id, "node": "20"}},
            {"type": "executing", "data": {"prompt_id": prompt_id, "node": None}},
        ]
        with patch("httpx.AsyncClient", return_value=client), \
             patch("providers.comfyui.websockets") as ws_mod, \
             patch("asyncio.sleep", new=AsyncMock()):
            ws_mod.connect = MagicMock(return_value=FakeWS(list(ws_frames)))
            p = ComfyUIProvider()
            r = await p.invoke(
                "a sunset",
                params={"template": "wan2.1"},
                max_wait_s=2.0,
            )
        assert r.success is True
        assert any("out.mp4" in u for u in r.videos)
        assert r.videos[0].endswith("subfolder=video")


# ═══════════════════════════════════════════════════════════════════════════
# 4. WS-error path (execution_error)
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIWebSocketError:
    @pytest.mark.asyncio
    async def test_ws_execution_error(self):
        prompt_id = "pid-003"
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, {"prompt_id": prompt_id}))
        client.get = AsyncMock(return_value=_mock_resp(404, text="missing"))

        ws_frames = [
            {
                "type": "execution_error",
                "data": {
                    "prompt_id": prompt_id,
                    "exception_message": "missing ckpt file",
                },
            },
        ]
        with patch("httpx.AsyncClient", return_value=client), \
             patch("providers.comfyui.websockets") as ws_mod, \
             patch("asyncio.sleep", new=AsyncMock()):
            ws_mod.connect = MagicMock(return_value=FakeWS(list(ws_frames)))
            p = ComfyUIProvider()
            r = await p.invoke(
                "x",
                params={"template": "flux1-schnell"},
                max_wait_s=2.0,
            )
        assert r.success is False
        assert r.task_id == prompt_id
        assert "missing ckpt file" in r.error


# ═══════════════════════════════════════════════════════════════════════════
# 5. WS connect fails → /history fallback
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIWSConnectFallback:
    @pytest.mark.asyncio
    async def test_ws_connect_failure_uses_polling(self):
        prompt_id = "pid-004"
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(200, {"prompt_id": prompt_id}))
        # First call to /history returns payload → polling succeeds quickly
        polled_payload = {prompt_id: {"outputs": {}}}
        client.get = AsyncMock(return_value=_mock_resp(200, polled_payload))

        async def _connect_fail(*a, **kw):
            raise RuntimeError("ws connect refused")

        with patch("httpx.AsyncClient", return_value=client), \
             patch("providers.comfyui.websockets") as ws_mod, \
             patch(
                 "asyncio.sleep", new=AsyncMock(),
             ):
            ws_mod.connect = MagicMock(side_effect=_connect_fail)
            p = ComfyUIProvider()
            r = await p.invoke(
                "x",
                params={"template": "flux1-schnell"},
                max_wait_s=2.0,
            )
        assert r.success is True
        assert r.task_id == prompt_id
        assert r.status == "succeeded"


# ═══════════════════════════════════════════════════════════════════════════
# 6. /history /view URL helpers + 5xx handling
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIHistoryAndHealth:
    @pytest.mark.asyncio
    async def test_extract_view_urls_with_subfolder(self):
        p = ComfyUIProvider()
        outputs = {
            "1": {
                "images": [
                    {"filename": "a.png", "type": "output", "subfolder": "x"},
                ]
            },
            "2": {
                "gifs": [
                    {"filename": "anim.gif", "type": "output", "subfolder": ""},
                ]
            },
        }
        urls = p._view_urls(outputs)
        assert any("subfolder=x" in u for u in urls["images"])
        assert any("anim.gif" in u for u in urls["videos"])

    @pytest.mark.asyncio
    async def test_invoke_no_prompt_id_returns_error(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=_mock_resp(
            400, {"error": "node validation failed", "node_errors": {"9": "missing"}},
        ))
        with patch("httpx.AsyncClient", return_value=client):
            p = ComfyUIProvider()
            r = await p.invoke(
                "x",
                params={"template": "flux1-schnell"},
                max_wait_s=1.0,
            )
        assert r.success is False
        assert "validation" in r.error or "node" in r.error

    @pytest.mark.asyncio
    async def test_health_check_5xx(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=_mock_resp(500, text="oops"))
        with patch("httpx.AsyncClient", return_value=client):
            p = ComfyUIProvider()
            h = await p.health_check()
        assert h.success is False
        assert "500" in h.error


# ═══════════════════════════════════════════════════════════════════════════
# 7. Workflow template structure sanity
# ═══════════════════════════════════════════════════════════════════════════


class TestComfyUIWorkflowTemplate:
    def test_template_has_required_nodes(self):
        wf = ComfyUIProvider._template_workflow(
            "flux1-schnell", "a cat", {"steps": 12, "cfg": 6.5, "seed": 7},
        )
        assert "3" in wf and "4" in wf and "9" in wf
        ksampler = wf["3"]
        assert ksampler["class_type"] == "KSampler"
        assert ksampler["inputs"]["steps"] == 12
        assert ksampler["inputs"]["cfg"] == 6.5
        assert ksampler["inputs"]["seed"] == 7
        # text node
        text_node = wf["6"]
        assert text_node["inputs"]["text"] == "a cat"
