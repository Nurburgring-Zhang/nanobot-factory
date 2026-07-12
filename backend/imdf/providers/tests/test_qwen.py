"""P19-A1: QwenProvider 单元测试 (mock httpx).

覆盖:
- 无 API key → placeholder
- 有 key → chat 走通
- 多环境变量名 (QWEN_API_KEY / DASHSCOPE_API_KEY)
- generate_image (vl-plus 支持,走 DashScope wanx 端点)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ALIYUN_DASHSCOPE_API_KEY", raising=False)


def _qwen_response(content: str = "通义答",
                      prompt_tokens: int = 8,
                      completion_tokens: int = 16) -> dict:
    return {
        "id": "chatcmpl-qwen-001",
        "object": "chat.completion",
        "model": "qwen-plus",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content},
             "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _qwen_image_response() -> dict:
    return {
        "output": {
            "task_id": "test-task-uuid",
            "results": [{"url": "https://dashscope.oss/test.png"}],
        },
        "request_id": "req-001",
    }


def _mock_response(status: int = 200, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or _qwen_response()
    resp.text = str(json_data)[:500]
    return resp


class TestQwenNoKey:
    @pytest.mark.asyncio
    async def test_chat_returns_placeholder(self):
        from providers.qwen import QwenProvider
        p = QwenProvider(api_key="")
        resp = await p.chat([{"role": "user", "content": "你好"}])
        assert resp["success"] is False
        assert "QWEN_API_KEY" in resp["error"] or "DASHSCOPE_API_KEY" in resp["error"]

    def test_alt_env_var_fallback(self, monkeypatch):
        """QWEN_API_KEY 不存在,但 DASHSCOPE_API_KEY 在 → 应能加载到 key."""
        from providers.qwen import QwenProvider
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
        p = QwenProvider()
        assert p.has_credentials() is True

    def test_models_present(self):
        from providers.qwen import QwenProvider
        p = QwenProvider(api_key="")
        ids = {m["id"] for m in p.get_models()}
        assert {"qwen-plus", "qwen-max", "qwen-vl-plus"}.issubset(ids)


class TestQwenWithKey:
    @pytest.mark.asyncio
    async def test_chat_success(self):
        from providers.qwen import QwenProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200, _qwen_response("杭州 nice", 20, 40)))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = QwenProvider(api_key="sk-qwen")
            resp = await p.chat([{"role": "user", "content": "介绍杭州"}])
        assert resp["success"] is True
        assert "杭州" in resp["content"]
        assert resp["usage"]["total_tokens"] == 60

    @pytest.mark.asyncio
    async def test_chat_vl_plus_capability(self):
        from providers.qwen import QwenProvider
        captured = {}

        async def fake_post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs.get("json") or {})
            return _mock_response(200)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = QwenProvider(api_key="sk-qwen")
            await p.chat(
                [{"role": "user", "content": "描述图片"}],
                model="qwen-vl-plus",
            )
        assert captured.get("model") == "qwen-vl-plus"

    @pytest.mark.asyncio
    async def test_generate_image_uses_wanx_endpoint(self):
        from providers.qwen import QwenProvider
        captured_url = {}

        async def fake_post(url, **kwargs):
            captured_url["url"] = url
            return _mock_response(200, _qwen_image_response())

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = QwenProvider(api_key="sk-qwen")
            r = await p.generate_image("A beautiful cat")
        assert r["success"] is True
        assert len(r["urls"]) == 1
        assert "dashscope" in captured_url["url"]
        assert "/text2image/image-synthesis" in captured_url["url"]

    @pytest.mark.asyncio
    async def test_generate_image_no_key_returns_placeholder(self):
        from providers.qwen import QwenProvider
        p = QwenProvider(api_key="")
        r = await p.generate_image("A cat")
        assert r["success"] is False
        assert r.get("placeholder_url") or "QWEN_API_KEY" in r.get("error", "")

    def test_cost_estimate(self):
        from providers.qwen import QwenProvider
        p = QwenProvider(api_key="sk")
        # 1M + 1M = 0.40 + 1.20 = 1.60
        assert abs(p.cost_estimate_usd(1_000_000, 1_000_000) - 1.60) < 1e-6
        assert p.cost_estimate_usd(0, 0) == 0.0
