"""P19-A1: DeepSeekProvider 单元测试 (mock httpx).

覆盖:
- 无 API key → placeholder
- 有 key → 真实 mock 调用走通 (OpenAI 兼容)
- 生成图/视频 不支持
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import httpx


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _openai_chat_response(content: str = "Hello from DeepSeek",
                            prompt_tokens: int = 10,
                            completion_tokens: int = 20) -> dict:
    return {
        "id": "chatcmpl-deepseek-001",
        "object": "chat.completion",
        "model": "deepseek-chat",
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


def _mock_response(status: int = 200, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or _openai_chat_response()
    resp.text = str(json_data)[:500]
    return resp


class TestDeepSeekNoKey:
    @pytest.mark.asyncio
    async def test_chat_returns_placeholder_when_no_key(self):
        from providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="")
        resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is False
        assert "DEEPSEEK_API_KEY" in resp["error"]
        assert resp["provider"] == "deepseek"

    def test_models_present(self):
        from providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="")
        models = p.get_models()
        assert {m["id"] for m in models} >= {"deepseek-chat", "deepseek-coder"}

    @pytest.mark.asyncio
    async def test_generate_image_unsupported(self):
        from providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="")
        r = await p.generate_image("cat")
        assert r["success"] is False
        assert r["provider"] == "deepseek"


class TestDeepSeekWithKey:
    @pytest.mark.asyncio
    async def test_chat_success(self):
        from providers.deepseek import DeepSeekProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200, _openai_chat_response("hi", 5, 10)))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DeepSeekProvider(api_key="sk-ds")
            resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is True
        assert resp["content"] == "hi"
        assert resp["usage"]["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_chat_coder_model(self):
        from providers.deepseek import DeepSeekProvider
        captured = {}

        async def fake_post(url, **kwargs):
            captured.update(kwargs.get("json") or {})
            return _mock_response(200)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DeepSeekProvider(api_key="sk-ds")
            await p.chat(
                [{"role": "user", "content": "write fibonacci"}],
                model="deepseek-coder",
            )
        assert captured.get("model") == "deepseek-coder"

    @pytest.mark.asyncio
    async def test_chat_http_error(self):
        from providers.deepseek import DeepSeekProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(429, {"error": "rate limited"}))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DeepSeekProvider(api_key="sk-ds")
            resp = await p.chat([{"role": "user", "content": "x"}])
        assert resp["success"] is False
        assert "HTTP 429" in resp["error"]

    def test_cost_estimate(self):
        from providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="sk")
        # 1M + 1M = 0.14 + 0.28 = 0.42
        assert abs(p.cost_estimate_usd(1_000_000, 1_000_000) - 0.42) < 1e-6
        assert p.cost_estimate_usd(0, 0) == 0.0

    @pytest.mark.asyncio
    async def test_health_check(self):
        from providers.deepseek import DeepSeekProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DeepSeekProvider(api_key="sk-ds")
            health = await p.health_check()
        assert health["status"] == "ok"
        assert health["provider"] == "deepseek"
