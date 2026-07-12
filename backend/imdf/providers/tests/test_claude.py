"""P19-A1: ClaudeProvider 单元测试 (mock httpx).

覆盖:
- 无 API key → placeholder response (success=False)
- 有 key → 真实 mock 调用走通
- system message 抽离
- 健康检查 / generate_image (不支持) / cost_estimate
"""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import httpx


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """保证 ClaudeProvider 起始状态是 '无 key'。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _anthropic_response(content: str = "Hello from Claude",
                          input_tokens: int = 12,
                          output_tokens: int = 18) -> dict:
    return {
        "id": "msg_abc123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": "claude-3-5-sonnet-20241022",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def _make_mock_response(status: int = 200, json_data: dict = None):
    """构造 httpx 风格的 response mock。"""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or _anthropic_response()
    resp.text = str(json_data)[:500]
    return resp


class TestClaudeProviderNoKey:
    """无 API key — 必须返回 placeholder,不能 raise。"""

    @pytest.mark.asyncio
    async def test_chat_returns_placeholder_when_no_key(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="")
        resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is False
        assert "ANTHROPIC_API_KEY" in resp["error"]
        assert resp["provider"] == "claude"
        assert resp["model"] == "claude-3-5-sonnet-20241022"
        assert resp["usage"]["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_health_check_no_key_returns_error_status(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="")
        health = await p.health_check()
        assert health["status"] == "error"
        assert "ANTHROPIC_API_KEY" in health["error"]

    def test_get_models_returns_3_models(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="")
        models = p.get_models()
        assert len(models) == 3
        ids = {m["id"] for m in models}
        assert ids == {"claude-3-5-sonnet-20241022",
                        "claude-opus-4-20250514",
                        "claude-3-haiku-20240307"}
        # 默认模型必须存在
        assert next((m for m in models if m.get("default")), None) is not None

    def test_has_credentials(self):
        from providers.claude import ClaudeProvider
        assert ClaudeProvider(api_key="").has_credentials() is False
        assert ClaudeProvider(api_key="sk-test-123").has_credentials() is True

    @pytest.mark.asyncio
    async def test_generate_image_unsupported(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="")
        r = await p.generate_image("a cat")
        assert r["success"] is False
        assert "image" in r.get("error", "").lower() or "image" in r.get("error", "").lower()


class TestClaudeProviderWithKey:
    """有 API key — mock httpx 拦截,不走真实网络。"""

    @pytest.mark.asyncio
    async def test_chat_success_via_mock(self, monkeypatch):
        from providers.claude import ClaudeProvider
        mock_resp = _make_mock_response(200)

        # patch httpx.AsyncClient.post
        mock_post = AsyncMock(return_value=mock_resp)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = ClaudeProvider(api_key="sk-test-real-key")
            resp = await p.chat(
                [{"role": "user", "content": "describe Claude"}],
                model="claude-3-5-sonnet-20241022",
            )
        assert resp["success"] is True
        assert "Hello from Claude" in resp["content"]
        assert resp["usage"]["prompt_tokens"] == 12
        assert resp["usage"]["completion_tokens"] == 18
        assert resp["usage"]["total_tokens"] == 30
        assert resp["provider"] == "claude"
        assert resp["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_chat_separates_system_message(self, monkeypatch):
        from providers.claude import ClaudeProvider
        captured_body = {}

        async def fake_post(url, **kwargs):
            # url is the only positional arg in client.post(url, json=..., headers=...)
            captured_body.update(kwargs.get("json") or {})
            return _make_mock_response(200)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = ClaudeProvider(api_key="sk-test")
            await p.chat([
                {"role": "system", "content": "你是 helpful assistant"},
                {"role": "user", "content": "hi"},
            ])
        assert captured_body.get("system") == "你是 helpful assistant"
        assert len(captured_body.get("messages", [])) == 1
        assert captured_body["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_chat_http_error_returns_failure(self):
        from providers.claude import ClaudeProvider
        mock_resp = _make_mock_response(500, {"error": "server overloaded"})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = ClaudeProvider(api_key="sk-test")
            resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is False
        assert "HTTP 500" in resp["error"]
        assert "server overloaded" in resp["error"]

    def test_cost_estimate_pricing(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="sk")
        # 1M input + 1M output = $3 + $15 = $18
        c = p.cost_estimate_usd(1_000_000, 1_000_000)
        assert abs(c - 18.0) < 1e-6
        # 1000 input + 1000 output = 0.003 + 0.015 = 0.018
        c2 = p.cost_estimate_usd(1000, 1000)
        assert abs(c2 - 0.018) < 1e-6
        # 0 tokens → 0
        assert p.cost_estimate_usd(0, 0) == 0.0
