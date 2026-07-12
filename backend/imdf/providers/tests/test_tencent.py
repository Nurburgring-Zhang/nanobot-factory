"""P19-A2: Tests for Tencent Hunyuan (混元) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_tencent sync error paths
- call_tencent HTTP success path (mocked)
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
from providers import tencent


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
                "message": {"role": "assistant", "content": "混元回答"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestTencentDescriptor:
    def test_default_descriptor(self):
        tp = tencent.TencentProvider()
        assert tp.id == "tencent"
        assert tp.family == "tencent"
        assert tp.default_model == "hunyuan-pro"
        assert "hunyuan.tencent.com" in tp.api_base
        assert tp.price_per_1k_input == tencent.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        tp = tencent.TencentProvider()
        kw = tp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "tencent"
        assert p.config["protocol"] == "openai-compatible"
        assert "hunyuan-pro" in p.config["models"]
        assert "hunyuan-standard" in p.config["models"]

    def test_sample_providers_includes_tencent(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "tencent" in ids
        t = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "tencent")
        assert t.family == "tencent"
        assert t.config["protocol"] == "openai-compatible"
        assert t.trust_level == "verified"

    def test_provider_family_enum_includes_tencent(self):
        assert reg.ProviderFamily.TENCENT.value == "tencent"

    def test_registry_upserts_tencent(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "tencent" in ids
        t = r.get("tencent")
        assert t is not None
        assert t.default_model == "hunyuan-pro"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestTencentCost:
    def test_zero_tokens(self):
        assert tencent.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0003 + 0.0009 = 0.0012
        cost = tencent.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0012) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.30 + $0.90 = $1.20
        cost = tencent.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 1.20) < 1e-6

    def test_tencent_supports_function_call(self):
        tp = tencent.TencentProvider()
        assert tp.config["supports_function_call"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_tencent sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestTencentCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await tencent.call_tencent({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        res = await tencent.call_tencent(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await tencent.call_tencent(
            {"apiKey": "k", "default_model": "hunyuan-pro"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await tencent.call_tencent(
            {"apiKey": "k", "default_model": "hunyuan-pro"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_tencent HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestTencentCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_hunyuan_pro_chat_success(self):
        provider = {
            "id": "tencent", "apiKey": "sk-tencent-test",
            "api_base": "https://hunyuan.tencent.com/v1",
            "default_model": "hunyuan-pro",
            "config": {"models": ["hunyuan-pro", "hunyuan-standard"]},
        }
        with respx.mock(base_url="https://hunyuan.tencent.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("hunyuan-pro", 12, 18))
            )
            res = await tencent.call_tencent(
                provider,
                {"model": "hunyuan-pro",
                 "messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "hunyuan-pro"
        assert res["data"]["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_hunyuan_standard_chat(self):
        provider = {
            "id": "tencent", "apiKey": "sk-tencent",
            "api_base": "https://hunyuan.tencent.com/v1",
            "default_model": "hunyuan-pro",
        }
        with respx.mock(base_url="https://hunyuan.tencent.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("hunyuan-standard", 100, 200))
            )
            res = await tencent.call_tencent(
                provider,
                {"model": "hunyuan-standard",
                 "messages": [{"role": "user", "content": "test"}]},
            )
        assert res["ok"] is True
        assert res["data"]["usage"]["total_tokens"] == 300

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_hunyuan_http_4xx(self):
        provider = {
            "id": "tencent", "apiKey": "bad",
            "api_base": "https://hunyuan.tencent.com/v1",
            "default_model": "hunyuan-pro",
        }
        with respx.mock(base_url="https://hunyuan.tencent.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(401, json={"error": "unauthorized"})
            )
            res = await tencent.call_tencent(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_hunyuan_http_5xx(self):
        provider = {
            "id": "tencent", "apiKey": "k",
            "api_base": "https://hunyuan.tencent.com/v1",
            "default_model": "hunyuan-pro",
        }
        with respx.mock(base_url="https://hunyuan.tencent.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(503, json={"error": "service unavailable"})
            )
            res = await tencent.call_tencent(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        # 5xx surfaces as api_error via engines layer OR fallback.
        assert res["code"] in ("api_error", "request_failed")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestTencentRouting:
    def test_route_family_tencent(self, tmp_registry_db):
        r = reg.get_registry()
        t = r.route(family="tencent", prefer="cost")
        assert t is not None
        assert t.id == "tencent"

    def test_route_tencent_speed(self, tmp_registry_db):
        r = reg.get_registry()
        t = r.route(family="tencent", prefer="speed")
        assert t.id == "tencent"
        assert t.latency_p50_ms == 600

    def test_route_tencent_trust(self, tmp_registry_db):
        r = reg.get_registry()
        t = r.route(family="tencent", prefer="trust")
        assert t.id == "tencent"
        assert t.trust_level == "verified"

    def test_tencent_supports_vision(self, tmp_registry_db):
        t = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "tencent")
        assert t.config["supports_vision"] is True
        assert "hunyuan-vision" in t.config["vision_models"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. P19-A2 integration: all 13 providers registered
# ═══════════════════════════════════════════════════════════════════════════

class TestP19A2Integration:
    """P19-A2 batch 2 verifies all 5 new providers coexist with batch 1 (p19_a1)."""

    def test_all_18_providers_registered(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        expected = {
            # batch 1 (p19_a1)
            "openai", "claude", "deepseek", "qwen", "doubao", "agnes",
            # batch 2 (p19_a2)
            "gemini", "kimi", "zhipu", "baidu", "tencent",
            # batch 3 (p19_b2)
            "mistral", "cohere", "minimax", "stepfun", "nova",
            # infra
            "comfyui", "mock",
        }
        missing = expected - ids
        assert not missing, f"missing providers: {missing}"
        assert len(ids) == 18

    def test_5_new_providers_in_batch_2(self, tmp_registry_db):
        """P19-A2 batch 2: gemini + kimi + zhipu + baidu + tencent."""
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        batch2 = {"gemini", "kimi", "zhipu", "baidu", "tencent"}
        assert batch2.issubset(ids), f"batch 2 missing: {batch2 - ids}"

    def test_5_new_providers_in_batch_3(self, tmp_registry_db):
        """P19-B2 batch 3: mistral + cohere + minimax + stepfun + nova."""
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        batch3 = {"mistral", "cohere", "minimax", "stepfun", "nova"}
        assert batch3.issubset(ids), f"batch 3 missing: {batch3 - ids}"

    def test_provider_family_count(self):
        """18 ProviderFamily members."""
        # Pre-P19: 7 families (openai/claude/deepseek/qwen/doubao/comfyui/mock)
        # P19-A1 added: agnes (1)
        # P19-A2 added: gemini/kimi/zhipu/baidu/tencent (5)
        # P19-B2 added: mistral/cohere/minimax/stepfun/nova (5)
        # Total: 18
        members = list(reg.ProviderFamily)
        assert len(members) == 18, f"expected 18 families, got {len(members)}: {[m.value for m in members]}"