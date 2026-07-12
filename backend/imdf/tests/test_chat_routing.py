"""P11-A: Chat 路由去重 / call_provider_smart 路径 inert 修复验证.

覆盖:
1. ``/api/chat`` (unified_chat) 不再走 model_gateway.chat() — 走 call_provider_smart
2. ``/api/v1/chat/smart`` (chat_api) 也走 call_provider_smart — 路由不再 inert
3. ``/api/chat`` 和 ``/api/v1/chat/smart`` 两个端点路径不冲突 (no 409)
4. 两者都至少返回 200 + 标准结构 (success + content + model + provider_id)
5. call_provider_smart 用默认 provider 命中 (mock 降级, 无 apiKey)
6. 限流/熔断由 call_provider_smart 自动处理 (不依赖 model_gateway)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Set required env vars BEFORE imports
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p11a-chat-routing-12345678")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

# Resolve imdf/ and load canvas_web / model_routes by file path (sidesteps the api/
# namespace clash with backend/api/__init__.py).
IMDF_ROOT = Path(__file__).resolve().parent.parent
CANVAS_WEB_PATH = IMDF_ROOT / "api" / "canvas_web.py"
MODEL_ROUTES_PATH = IMDF_ROOT / "api" / "model_routes.py"

# Remove any cached "api" module that points to backend/api (not imdf/api)
for _cached in list(sys.modules.keys()):
    if _cached == "api" or _cached.startswith("api."):
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

# Now import model_routes and canvas_web the normal way (imdf is at sys.path[0])
from api import model_routes  # noqa: E402
from api import canvas_web  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 1. 路由路径去重 — 无冲突
# ═══════════════════════════════════════════════════════════════════════════

class TestRoutingPaths:
    """验证 chat_api 与 unified_chat 不再冲突 (no 409 from FastAPI)."""

    def test_chat_api_moved_to_v1_chat_smart(self):
        """P11-A 修复: chat_api 现在注册在 /api/v1/chat/smart (不再是 /api/chat)."""
        from api.canvas_web import chat_api
        # 1. chat_api 函数本身还在
        assert callable(chat_api), "chat_api 必须仍是 callable function"

        # 2. 检查其路由路径 (FastAPI 把 path 存在 .path 属性)
        # 直接检查 canvas_web.app.routes 里有没有 /api/v1/chat/smart
        paths = [getattr(r, "path", "") for r in canvas_web.app.routes]
        assert "/api/v1/chat/smart" in paths, (
            f"chat_api 应注册到 /api/v1/chat/smart (避免与 unified_chat 冲突). "
            f"实际 paths: {[p for p in paths if 'chat' in p.lower()]}"
        )
        # 3. 同时确认 /api/chat 上只有 unified_chat, 没有 chat_api
        api_chat_handlers = [
            r for r in canvas_web.app.routes
            if getattr(r, "path", "") == "/api/chat"
            and "POST" in getattr(r, "methods", set())
        ]
        # 这些是 model_routes 挂载进来的 unified_chat (路径前缀 /api)
        # 不应该有 chat_api 重复注册
        chat_api_count = sum(
            1 for r in api_chat_handlers
            if getattr(r, "endpoint", None) is canvas_web.chat_api
        )
        assert chat_api_count == 0, (
            f"chat_api 不应该再注册到 /api/chat (会和 unified_chat 冲突). "
            f"实际找到 {chat_api_count} 个"
        )

    def test_unified_chat_still_at_api_chat(self):
        """unified_chat 保留在 /api/chat (model_routes 挂载)."""
        paths = [getattr(r, "path", "") for r in canvas_web.app.routes]
        assert "/api/chat" in paths, "unified_chat 必须仍在 /api/chat"

    def test_no_path_collision_409(self):
        """完整 app 启动时 (TestClient) 不抛 409 Conflict."""
        # TestClient 启动时会校验所有路由, 有冲突会立即抛 RuntimeError
        app = canvas_web.app
        try:
            client = TestClient(app)
        except RuntimeError as e:
            if "duplicate" in str(e).lower() or "conflict" in str(e).lower():
                pytest.fail(f"P11-A 修复: 路由冲突: {e}")
            raise
        # 简单 GET 健康检查 / 健康路径 不报 409
        # /api/chat 用 POST 测试, 需要 body
        resp = client.post("/api/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "model": "auto",
            "temperature": 0.7,
            "max_tokens": 100,
        })
        # 不管业务结果, 不应该 405 (method not allowed) 或 409 (conflict)
        assert resp.status_code != 409, f"路由冲突: {resp.text}"
        assert resp.status_code != 405, f"路由 method 冲突: {resp.text}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. unified_chat 内部走 call_provider_smart
# ═══════════════════════════════════════════════════════════════════════════

class TestUnifiedChatUsesCallProviderSmart:
    """验证 /api/chat 的 unified_chat handler 现在真正调用 call_provider_smart."""

    def _build_unified_chat_app(self):
        """构建只挂载 unified_chat 的最小 app (避免 canvas_web 的副作用)."""
        from api.model_routes import unified_chat
        app = FastAPI()
        app.post("/api/chat")(unified_chat)
        return app

    def test_unified_chat_calls_call_provider_smart(self):
        """Mock call_provider_smart → 验证 unified_chat 路由通过它."""
        captured = {}

        async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
            captured["provider"] = provider
            captured["payload"] = payload
            captured["kind"] = kind
            captured["kw"] = kw
            return {
                "ok": True,
                "data": {
                    "id": "chatcmpl-p11a-test",
                    "choices": [{"message": {"role": "assistant", "content": "P11-A 测试回复"}}],
                    "model": payload.get("model", "test-model"),
                    "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
                },
                "provider_id": provider.get("id", "test-provider"),
                "cost_usd": 0.0003,
                "usage_tokens": 20,
                "mock": True,
            }

        with patch("engines.provider_registry._get_default_providers", return_value=[
            {"id": "test-openai", "label": "Test", "protocol": "openai-compatible",
             "baseUrl": "https://api.test.com", "enabled": True, "apiKey": "sk-test",
             "chatModels": ["gpt-4o-mini"],
             "defaults": {"chatModel": "gpt-4o-mini"}},
        ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
            app = self._build_unified_chat_app()
            client = TestClient(app)
            resp = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "ping"}],
                "model": "auto",
                "temperature": 0.5,
                "max_tokens": 512,
            })
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["success"] is True
            assert data["content"] == "P11-A 测试回复"
            assert data["model"] == "gpt-4o-mini"
            assert data["provider_id"] == "test-openai"
            assert data["cost_usd"] == 0.0003
            # call_provider_smart 收到了正确的 payload
            assert captured["payload"]["model"] == "gpt-4o-mini"
            assert captured["payload"]["messages"] == [{"role": "user", "content": "ping"}]
            assert captured["payload"]["temperature"] == 0.5
            assert captured["payload"]["max_tokens"] == 512
            assert captured["kind"] == "chat"
            assert captured["kw"]["user_id"] == "anonymous"

    def test_unified_chat_respects_explicit_model(self):
        """unified_chat 收到 model="gpt-4o" 时应透传给 call_provider_smart."""
        captured = {}

        async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
            captured["payload"] = payload
            return {
                "ok": True,
                "data": {
                    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                    "model": payload.get("model"),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
                "provider_id": provider["id"],
                "cost_usd": 0.0,
                "usage_tokens": 2,
            }

        with patch("engines.provider_registry._get_default_providers", return_value=[
            {"id": "openai-compatible", "label": "OpenAI", "protocol": "openai-compatible",
             "baseUrl": "https://api.openai.com/v1", "enabled": True, "apiKey": "sk",
             "chatModels": ["gpt-4o-mini", "gpt-4o"],
             "defaults": {"chatModel": "gpt-4o-mini"}},
        ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
            app = self._build_unified_chat_app()
            client = TestClient(app)
            resp = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "use gpt-4o"}],
                "model": "gpt-4o",
            })
            assert resp.status_code == 200
            assert captured["payload"]["model"] == "gpt-4o", (
                f"unified_chat 必须透传显式 model, 实际: {captured['payload']['model']}"
            )

    def test_unified_chat_handles_failure(self):
        """call_provider_smart 返回 ok=False → unified_chat 返回 success=False + error."""
        async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
            return {
                "ok": False,
                "code": "rate_limited",
                "error": "rate limit exceeded",
                "provider_id": provider["id"],
            }

        with patch("engines.provider_registry._get_default_providers", return_value=[
            {"id": "openai-compatible", "label": "OpenAI", "protocol": "openai-compatible",
             "baseUrl": "https://api.openai.com/v1", "enabled": True,
             "chatModels": ["gpt-4o-mini"], "defaults": {}},
        ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
            app = self._build_unified_chat_app()
            client = TestClient(app)
            resp = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "hi"}],
                "model": "auto",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert data["code"] == "rate_limited"
            assert "rate" in data["error"].lower()

    def test_unified_chat_falls_back_when_no_providers(self):
        """没有任何 default provider → unified_chat 应降级到 gateway.chat() (不 500)."""
        async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
            return {"ok": True, "data": {"choices": [{"message": {"content": "x"}}]}}

        async def fake_gateway_chat(self, messages, model="auto", temperature=0.7,
                                    max_tokens=4096, max_fallbacks=3):
            return model_routes.ChatResponse(
                success=True, content="fallback-via-gateway",
                model="deepseek-chat", provider="deepseek",
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

        with patch("engines.provider_registry._get_default_providers", return_value=[
            # 全部 disabled, 无 enabled provider
            {"id": "x", "label": "X", "protocol": "openai-compatible", "enabled": False,
             "chatModels": [], "defaults": {}},
        ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart), \
             patch.object(model_routes.get_gateway().__class__, "chat", fake_gateway_chat):
            app = self._build_unified_chat_app()
            client = TestClient(app)
            resp = client.post("/api/chat", json={
                "messages": [{"role": "user", "content": "hi"}],
                "model": "auto",
            })
            # 即使 fallback 路径, 也应 200 不 500
            assert resp.status_code == 200, resp.text


# ═══════════════════════════════════════════════════════════════════════════
# 3. chat_api (P10-B 路径) — 也走 call_provider_smart
# ═══════════════════════════════════════════════════════════════════════════

class TestChatApiV1ChatSmart:
    """验证 /api/v1/chat/smart (P10-B chat_api 路径) 仍走 call_provider_smart."""

    def _build_chat_api_app(self):
        from api.canvas_web import chat_api
        app = FastAPI()
        app.post("/api/v1/chat/smart")(chat_api)
        return app

    def test_chat_api_calls_call_provider_smart(self):
        """POST /api/v1/chat/smart → 仍调 call_provider_smart."""
        captured = {}

        async def fake_call_provider_smart(provider, payload, kind="chat", **kw):
            captured["payload"] = payload
            captured["provider"] = provider
            return {
                "ok": True,
                "data": {
                    "choices": [{"message": {"role": "assistant", "content": "smart path OK"}}],
                    "model": payload.get("model"),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
                "provider_id": provider["id"],
                "cost_usd": 0.001,
                "usage_tokens": 2,
            }

        with patch("engines.provider_registry._get_default_providers", return_value=[
            {"id": "openai-compatible", "label": "OpenAI", "protocol": "openai-compatible",
             "baseUrl": "https://api.openai.com/v1", "enabled": True, "apiKey": "sk",
             "chatModels": ["gpt-4o-mini"],
             "defaults": {"chatModel": "gpt-4o-mini"}},
        ]), patch("engines.provider_registry.call_provider_smart", fake_call_provider_smart):
            app = self._build_chat_api_app()
            client = TestClient(app)
            resp = client.post("/api/v1/chat/smart", json={"user_input": "hello smart"})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["success"] is True
            assert data["message"] == "smart path OK"
            assert data["model"] == "gpt-4o-mini"
            assert data["cost_usd"] == 0.001
            # payload 形状符合 chat_api 期望 (user_input → messages[0].content)
            assert captured["payload"]["messages"] == [{"role": "user", "content": "hello smart"}]
            assert captured["payload"]["temperature"] == 0.7
            assert captured["payload"]["max_tokens"] == 4096


# ═══════════════════════════════════════════════════════════════════════════
# 4. 三个端点共存 — 完整 canvas_web.app
# ═══════════════════════════════════════════════════════════════════════════

class TestAllChatEndpointsCoexist:
    """完整 canvas_web.app 上同时存在 unified_chat, chat_api, v1_chat_api 三个端点."""

    def test_three_chat_endpoints_registered(self):
        """canvas_web.app 上 /api/chat, /api/v1/chat, /api/v1/chat/smart 三个端点都在."""
        paths = [getattr(r, "path", "") for r in canvas_web.app.routes]
        for path in ("/api/chat", "/api/v1/chat", "/api/v1/chat/smart"):
            assert path in paths, (
                f"完整 canvas_web.app 必须注册 {path}, "
                f"实际 chat 相关 paths: {[p for p in paths if 'chat' in p.lower()]}"
            )

    def test_only_one_handler_per_path(self):
        """每个 chat 路径只有 1 个 POST handler (no duplicate)."""
        paths = ["/api/chat", "/api/v1/chat", "/api/v1/chat/smart"]
        for p in paths:
            handlers = [
                r for r in canvas_web.app.routes
                if getattr(r, "path", "") == p
                and "POST" in getattr(r, "methods", set())
            ]
            assert len(handlers) == 1, (
                f"{p} 应只有 1 个 POST handler, 实际 {len(handlers)} 个"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Source-level 验证 — 源码确实走 call_provider_smart
# ═══════════════════════════════════════════════════════════════════════════

class TestSourceLevelRefactor:
    """源码级验证: unified_chat 不再 import gateway.chat 作为主路径."""

    def test_unified_chat_source_uses_provider_smart(self):
        """unified_chat 函数源码应引用 call_provider_smart (不只是 docstring)."""
        import inspect
        src = inspect.getsource(model_routes.unified_chat)
        assert "call_provider_smart" in src, (
            "unified_chat 源码必须引用 call_provider_smart (P11-A 修复)"
        )
        # 必须有实际调用: ``result = await call_provider_smart(``
        assert "await call_provider_smart(" in src, (
            "unified_chat 必须有实际 await 调用 call_provider_smart 的代码"
        )

    def test_chat_api_source_uses_provider_smart(self):
        """chat_api (P10-B) 源码仍引用 call_provider_smart (P11-A 不应回退)."""
        import inspect
        src = inspect.getsource(canvas_web.chat_api)
        assert "call_provider_smart" in src, (
            "chat_api 源码必须仍引用 call_provider_smart (P10-B 不应回退)"
        )
        primary_path = src.split("except Exception")[0]
        assert "call_provider_smart" in primary_path