"""P19-A2: Tests for ZhipuAI (智谱) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_zhipu sync error paths
- call_zhipu HTTP success path (mocked)
- Family routing
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

try:
    import respx
    from httpx import Response as HttpxResponse
    HAS_RESPX = True
except ImportError:
    HAS_RESPX = False

from providers import registry as reg
from providers import zhipu


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_registry_db(tmp_path, monkeypatch):
    db = tmp_path / "providers.db"
    monkeypatch.setattr(reg, "_DB_PATH", db)
    try:
        reg.reset_registry_for_test()
    except Exception:
        pass
    try:
        reg._init_db()
    except Exception:
        pass
    yield reg
    try:
        reg.reset_registry_for_test()
    except Exception:
        pass


def _openai_chat_response(model: str, pt: int = 8, ct: int = 12) -> dict:
    return {
        "id": f"chatcmpl-{model}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "智谱回答"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestZhipuDescriptor:
    def test_default_descriptor(self):
        zp = zhipu.ZhipuProvider()
        assert zp.id == "zhipu"
        assert zp.family == "zhipu"
        assert zp.default_model == "glm-4-plus"
        assert "bigmodel.cn" in zp.api_base
        assert zp.price_per_1k_input == zhipu.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        zp = zhipu.ZhipuProvider()
        kw = zp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "zhipu"
        assert p.config["protocol"] == "openai-compatible"
        assert "glm-4-plus" in p.config["models"]
        assert "glm-4v-plus" in p.config["models"]

    def test_sample_providers_includes_zhipu(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "zhipu" in ids
        z = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "zhipu")
        assert z.family == "zhipu"
        assert z.config["protocol"] == "openai-compatible"
        assert z.trust_level == "verified"

    def test_provider_family_enum_includes_zhipu(self):
        assert reg.ProviderFamily.ZHIPU.value == "zhipu"

    def test_registry_upserts_zhipu(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "zhipu" in ids
        z = r.get("zhipu")
        assert z is not None
        assert z.default_model == "glm-4-plus"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestZhipuCost:
    def test_zero_tokens(self):
        assert zhipu.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0004 + 0.0012 = 0.0016
        cost = zhipu.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0016) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.40 + $1.20 = $1.60
        cost = zhipu.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 1.60) < 1e-6

    def test_zhipu_supports_function_call(self):
        zp = zhipu.ZhipuProvider()
        assert zp.config["supports_function_call"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_zhipu sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestZhipuCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await zhipu.call_zhipu({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        res = await zhipu.call_zhipu(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await zhipu.call_zhipu(
            {"apiKey": "k", "default_model": "glm-4-plus"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await zhipu.call_zhipu(
            {"apiKey": "k", "default_model": "glm-4-plus"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_zhipu HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestZhipuCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_zhipu_glm4_chat_success(self):
        provider = {
            "id": "zhipu", "apiKey": "sk-zhipu-test",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "glm-4-plus",
            "config": {"models": ["glm-4-plus", "glm-4v-plus"]},
        }
        with respx.mock(base_url="https://open.bigmodel.cn") as mock:
            mock.post("/api/paas/v4/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("glm-4-plus", 10, 25))
            )
            res = await zhipu.call_zhipu(
                provider,
                {"model": "glm-4-plus",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "glm-4-plus"
        assert res["data"]["usage"]["total_tokens"] == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_zhipu_glm4v_vision_request(self):
        provider = {
            "id": "zhipu", "apiKey": "sk-zhipu",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "glm-4-plus",
        }
        with respx.mock(base_url="https://open.bigmodel.cn") as mock:
            mock.post("/api/paas/v4/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("glm-4v-plus", 100, 50))
            )
            res = await zhipu.call_zhipu(
                provider,
                {"model": "glm-4v-plus",
                 "messages": [{"role": "user", "content": "描述图"}]},
            )
        assert res["ok"] is True
        assert "glm-4v-plus" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_zhipu_http_4xx(self):
        provider = {
            "id": "zhipu", "apiKey": "bad",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "default_model": "glm-4-plus",
        }
        with respx.mock(base_url="https://open.bigmodel.cn") as mock:
            mock.post("/api/paas/v4/chat/completions").mock(
                return_value=HttpxResponse(401, json={"error": {"message": "invalid key"}})
            )
            res = await zhipu.call_zhipu(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"
        # Error text comes through (status_code may be in error string via
        # engines layer wrapping).
        assert res.get("error")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestZhipuRouting:
    def test_route_family_zhipu(self, tmp_registry_db):
        r = reg.get_registry()
        z = r.route(family="zhipu", prefer="cost")
        assert z is not None
        assert z.id == "zhipu"

    def test_route_zhipu_speed(self, tmp_registry_db):
        r = reg.get_registry()
        z = r.route(family="zhipu", prefer="speed")
        assert z.id == "zhipu"
        assert z.latency_p50_ms == 500

    def test_route_zhipu_trust(self, tmp_registry_db):
        r = reg.get_registry()
        z = r.route(family="zhipu", prefer="trust")
        assert z.id == "zhipu"
        assert z.trust_level == "verified"

    def test_zhipu_supports_vision(self, tmp_registry_db):
        z = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "zhipu")
        assert z.config["supports_vision"] is True
        assert "glm-4v-plus" in z.config["vision_models"]