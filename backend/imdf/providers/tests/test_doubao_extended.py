"""P19-A1: DoubaoProvider 扩展测试 (mock httpx).

覆盖 P19-A1 增强:
- 新增 seed-1-6 默认模型
- 新增 1-5-vision-pro 模型
- chat / image / video 三种能力都覆盖
- 多环境变量名 (DOUBAO_API_KEY / ARK_API_KEY / VOLCENGINE_API_KEY)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_API_KEY", raising=False)


def _chat_response(content: str = "豆包答",
                     prompt_tokens: int = 6,
                     completion_tokens: int = 12) -> dict:
    return {
        "id": "chatcmpl-doubao-001",
        "object": "chat.completion",
        "model": "doubao-seed-1-6-250615",
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


def _image_response(url: str = "https://ark.oss/test.png") -> dict:
    return {
        "created": 1700000000,
        "model": "doubao-seedream-4-0-250828",
        "data": [{"url": url}],
    }


def _video_response(task_id: str = "cgt-task-abc") -> dict:
    return {"id": task_id, "status": "queued", "model": "doubao-seedance-2-0-260128"}


def _mock_response(status: int = 200, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or _chat_response()
    resp.text = str(json_data)[:500]
    return resp


class TestDoubaoNoKey:
    @pytest.mark.asyncio
    async def test_chat_placeholder(self):
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="")
        resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is False
        assert "DOUBAO_API_KEY" in resp["error"]

    def test_models_include_new_seed_and_vision(self):
        """P19-A1 增强: 必须包含 seed-1-6 + 1-5-vision-pro."""
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="")
        ids = {m["id"] for m in p.get_models()}
        assert "doubao-seed-1-6-250615" in ids, "seed-1-6 缺失"
        assert "doubao-1-5-vision-pro-250328" in ids, "1-5-vision-pro 缺失"

    def test_default_model_is_seed_1_6(self):
        """P19-A1 增强: 默认模型应为 seed-1-6, 不是旧的 pro-32k."""
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="")
        default = next((m for m in p.get_models() if m.get("default")), None)
        assert default is not None
        assert default["id"] == "doubao-seed-1-6-250615"

    def test_alt_env_vars(self, monkeypatch):
        from providers.doubao_extended import DoubaoProvider
        # ARK_API_KEY 替代 DOUBAO_API_KEY
        monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
        p = DoubaoProvider()
        assert p.has_credentials() is True


class TestDoubaoWithKey:
    @pytest.mark.asyncio
    async def test_chat_success(self):
        from providers.doubao_extended import DoubaoProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200, _chat_response("OK", 5, 8)))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DoubaoProvider(api_key="volc-test")
            resp = await p.chat([{"role": "user", "content": "hi"}])
        assert resp["success"] is True
        assert resp["content"] == "OK"

    @pytest.mark.asyncio
    async def test_chat_vision_pro(self):
        from providers.doubao_extended import DoubaoProvider
        captured = {}

        async def fake_post(url, **kwargs):
            captured.update(kwargs.get("json") or {})
            return _mock_response(200)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DoubaoProvider(api_key="volc-test")
            await p.chat(
                [{"role": "user", "content": "describe image"}],
                model="doubao-1-5-vision-pro-250328",
            )
        assert captured["model"] == "doubao-1-5-vision-pro-250328"

    @pytest.mark.asyncio
    async def test_generate_image(self):
        from providers.doubao_extended import DoubaoProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200, _image_response("https://ark.oss/cat.png")))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DoubaoProvider(api_key="volc-test")
            r = await p.generate_image("A dancing cat")
        assert r["success"] is True
        assert "cat.png" in r["urls"][0]

    @pytest.mark.asyncio
    async def test_generate_video_async_submit(self):
        from providers.doubao_extended import DoubaoProvider
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_mock_response(200, _video_response("cgt-seedance-001")))

        with patch("httpx.AsyncClient", return_value=mock_client):
            p = DoubaoProvider(api_key="volc-test")
            r = await p.generate_video("A sunset")
        assert r["success"] is True
        assert r["task_id"] == "cgt-seedance-001"

    @pytest.mark.asyncio
    async def test_generate_video_no_key_placeholder(self):
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="")
        r = await p.generate_video("cat")
        assert r["success"] is False
        assert r.get("placeholder_url") or "DOUBAO_API_KEY" in r.get("error", "")

    def test_cost_estimate(self):
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="volc")
        # 1M + 1M = 0.80 + 2.00 = 2.80
        assert abs(p.cost_estimate_usd(1_000_000, 1_000_000) - 2.80) < 1e-6
