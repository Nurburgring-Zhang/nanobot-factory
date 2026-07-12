"""P10-B: Tests for /api/chat endpoint — ``call_provider_smart`` integration.

Verifies:
1. ``POST /api/chat`` with a text prompt now flows through
   ``call_provider_smart`` (P5-W1 统一入口) — not the legacy NanobotAdapter.chat().
2. The response shape is preserved: ``{success, message, model, provider_id, cost_usd}``.
3. When no provider is enabled, it falls back to NanobotAdapter (graceful degradation).
4. ``call_provider_smart`` is invoked with a chat payload (messages + model + temperature).
5. Mock provider success → success=True with cost_usd populated.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Set required env vars BEFORE imports
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p10b-chat-1234567890")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

# Resolve imdf/ and load canvas_web by file path (sidesteps the api/ namespace clash
# with backend/api/__init__.py which is also on sys.path).
IMDF_ROOT = Path(__file__).resolve().parent.parent
CANVAS_WEB_PATH = IMDF_ROOT / "api" / "canvas_web.py"
NANOBOT_ADAPTER_PATH = IMDF_ROOT / "api" / "nanobot_adapter.py"

# Remove any cached "api" module that points to backend/api (not imdf/api)
for _cached in list(sys.modules.keys()):
    if _cached == "api" or _cached.startswith("api."):
        # Check if it was loaded from the wrong location
        mod = sys.modules[_cached]
        if hasattr(mod, "__file__") and mod.__file__:
            mod_path = str(mod.__file__).replace("\\", "/")
            if "backend/api" in mod_path and "imdf/api" not in mod_path:
                del sys.modules[_cached]

# Force imdf/ at the FRONT of sys.path
imdf_str = str(IMDF_ROOT)
sys.path = [imdf_str] + [p for p in sys.path if p != imdf_str]

# Pre-mark real-model probe done
try:
    from multimodal import embedding as _emb
    _emb._REAL_PROBED = True
    _emb._REAL_TEXT_ENC = None
    _emb._REAL_IMAGE_ENC = None
except Exception:
    pass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Now import canvas_web the normal way (imdf is at sys.path[0])
from api import canvas_web  # noqa: E402
from api import nanobot_adapter  # noqa: E402


# ── 1. Endpoint imports without error ────────────────────────────────────
def test_chat_endpoint_module_imports():
    """Verify the chat endpoint is still defined after refactor."""
    assert hasattr(canvas_web, "chat_api")
    assert callable(canvas_web.chat_api)


# ── 2. FastAPI testclient hits /api/chat with mocked provider_smart ──────
def _build_minimal_app():
    """Build a minimal FastAPI app with just the chat_api (PlanRequest) endpoint."""
    app = FastAPI()
    # canvas_web defines TWO POST /api/chat endpoints:
    #   1. model_routes.unified_chat (line ~2505, expects {"messages": [...], "model": "auto"})
    #   2. canvas_web.chat_api (line ~3736, expects {"user_input": "..."})  ← P10-B target
    # We pick the one with `chat_api` function (PlanRequest body).
    # Match by endpoint name + accept PlanRequest.
    from api.canvas_web import chat_api
    app.post("/api/chat")(chat_api)
    return app


def test_chat_calls_call_provider_smart_with_chat_payload():
    """Mock call_provider_smart and assert the chat endpoint routes through it."""
    captured = {}

    async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
        captured["provider"] = provider
        captured["payload"] = payload
        captured["kind"] = kind
        captured["kw"] = kw
        return {
            "ok": True,
            "data": {
                "id": "chatcmpl-xxx",
                "choices": [{"message": {"role": "assistant", "content": "Hello back"}}],
                "model": payload.get("model", "test-model"),
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            "provider_id": provider.get("id", "test-provider"),
            "cost_usd": 0.00021,
            "usage_tokens": 15,
            "mock": False,
        }

    with patch("engines.provider_registry._get_default_providers", return_value=[
        {"id": "test-openai", "label": "Test OpenAI", "protocol": "openai-compatible",
         "baseUrl": "https://api.test.com", "enabled": True, "apiKey": "sk-test",
         "chatModels": ["gpt-4o-mini"],
         "defaults": {"chatModel": "gpt-4o-mini"}},
    ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"user_input": "hi there"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Hello back"
        assert data["model"] == "gpt-4o-mini"
        assert data["provider_id"] == "test-openai"
        assert data["cost_usd"] == 0.00021
        assert data["usage"] == 15
        # call_provider_smart was invoked with the right shape
        assert captured["payload"]["model"] == "gpt-4o-mini"
        assert captured["payload"]["messages"] == [{"role": "user", "content": "hi there"}]
        assert captured["payload"]["temperature"] == 0.7
        assert captured["payload"]["max_tokens"] == 4096
        assert captured["kind"] == "chat"


def test_chat_handles_provider_smart_failure_gracefully():
    """When call_provider_smart returns ok=False, endpoint still returns 200 with success=False."""
    async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
        return {
            "ok": False,
            "code": "rate_limited",
            "error": "用户 anonymous 对 provider test 超出每小时限额",
            "provider_id": "test",
        }

    with patch("engines.provider_registry._get_default_providers", return_value=[
        {"id": "test", "label": "T", "protocol": "openai-compatible", "enabled": True,
         "apiKey": "sk", "chatModels": ["gpt-4o"], "defaults": {"chatModel": "gpt-4o"}},
    ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"user_input": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "rate_limited" in data["error"].lower() or "限额" in data["error"]
        assert data["code"] == "rate_limited"
        assert data["provider_id"] == "test"


def test_chat_falls_back_to_nanobot_when_no_providers():
    """If no default provider is enabled, falls back to NanobotAdapter."""
    fallback_called = {"value": False}

    async def fake_nanobot_chat(self, user_input):
        fallback_called["value"] = True
        return {"success": True, "message": "nanobot fallback reply"}

    with patch("engines.provider_registry._get_default_providers", return_value=[
        # all providers disabled or have no chatModels
        {"id": "x", "label": "X", "protocol": "openai-compatible", "enabled": False,
         "chatModels": [], "defaults": {}},
    ]), patch.object(nanobot_adapter.NanobotAdapter, "chat", fake_nanobot_chat):
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"user_input": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "nanobot fallback reply"
        assert fallback_called["value"] is True


def test_chat_handles_exception_with_nanobot_fallback():
    """If call_provider_smart raises, endpoint still returns a 200 with fallback result."""
    async def boom(*a, **kw):
        raise RuntimeError("simulated smart call failure")

    async def fake_nanobot_chat(self, user_input):
        return {"success": True, "message": "nanobot fallback after exception"}

    with patch("engines.provider_registry._get_default_providers", return_value=[
        {"id": "test", "label": "T", "protocol": "openai-compatible", "enabled": True,
         "apiKey": "sk", "chatModels": ["gpt-4o"], "defaults": {"chatModel": "gpt-4o"}},
    ]), patch("engines.provider_registry.call_provider_smart", boom), \
         patch.object(nanobot_adapter.NanobotAdapter, "chat", fake_nanobot_chat):
        app = _build_minimal_app()
        client = TestClient(app)
        resp = client.post("/api/chat", json={"user_input": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "nanobot fallback" in data["message"]


# ── 3. verify call_provider_smart is the one imported, not NanobotAdapter.chat ──
def test_chat_endpoint_uses_provider_smart_in_source():
    """Source-level: confirm the chat endpoint references call_provider_smart."""
    import inspect
    src = inspect.getsource(canvas_web.chat_api)
    assert "call_provider_smart" in src, (
        "chat_api should call call_provider_smart (P10-B migration). "
        "Found legacy NanobotAdapter references: "
        f"{[l for l in src.split(chr(10)) if 'NanobotAdapter' in l]}"
    )
    # The legacy "adapter.chat(req.user_input)" direct call should be GONE
    # (we have a fallback path inside except, but the primary path is provider_smart)
    primary_path = src.split("except Exception")[0]
    assert "call_provider_smart" in primary_path


# ── 4. verify multimodal routes are integrated into canvas_web ──────────
def test_multimodal_routes_included_in_canvas_web():
    """After P10-B, canvas_web.app should have /api/v1/multimodal/* routes mounted."""
    paths = [r.path for r in canvas_web.app.routes]
    multimodal_paths = [p for p in paths if "multimodal" in p]
    assert len(multimodal_paths) >= 4, (
        f"expected multimodal routes to be mounted, found only: {multimodal_paths}"
    )
    # spot-check a few endpoints
    expected = [
        "/api/v1/multimodal/healthz",
        "/api/v1/multimodal/providers",
        "/api/v1/multimodal/rag/index",
        "/api/v1/multimodal/rag/search",
    ]
    for ep in expected:
        assert ep in paths, f"missing endpoint: {ep}, have: {paths[:30]}"
