"""P19-A2: Tests for Moonshot Kimi provider.

Covers:
- Descriptor + registry upsert + sample providers list
- compute_cost_usd math sanity check
- call_kimi sync error paths (missing key, image/video kind rejected)
- call_kimi HTTP success path (mocked)
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
from providers import kimi


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
                "message": {"role": "assistant", "content": "你好,我是 Kimi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestKimiDescriptor:
    def test_default_descriptor(self):
        kp = kimi.KimiProvider()
        assert kp.id == "kimi"
        assert kp.family == "kimi"
        assert kp.default_model == "kimi-k2.7"
        assert "moonshot.cn" in kp.api_base
        assert kp.price_per_1k_input == kimi.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        kp = kimi.KimiProvider()
        kw = kp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "kimi"
        assert p.config["protocol"] == "openai-compatible"
        assert "kimi-k2.7" in p.config["models"]
        assert "moonshot-v1-128k" in p.config["models"]

    def test_sample_providers_includes_kimi(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "kimi" in ids
        k = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "kimi")
        assert k.family == "kimi"
        assert k.config["protocol"] == "openai-compatible"
        assert k.trust_level == "verified"

    def test_provider_family_enum_includes_kimi(self):
        assert reg.ProviderFamily.KIMI.value == "kimi"

    def test_registry_upserts_kimi(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "kimi" in ids
        k = r.get("kimi")
        assert k is not None
        assert k.default_model == "kimi-k2.7"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestKimiCost:
    def test_zero_tokens(self):
        assert kimi.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0003 + 0.0009 = 0.0012
        cost = kimi.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0012) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.30 + $0.90 = $1.20
        cost = kimi.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 1.20) < 1e-6

    def test_kimi_is_cheaper_than_gemini(self):
        # Sanity: kimi's price is $0.30/$0.90 vs gemini $0.70/$2.10
        from providers import gemini as _gemini
        ki = kimi.compute_cost_usd(100_000, 100_000)
        ge = _gemini.compute_cost_usd(100_000, 100_000)
        assert ki < ge


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_kimi sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestKimiCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await kimi.call_kimi({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        # Clear env vars so resolution from environment can't fill in a key.
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        res = await kimi.call_kimi(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await kimi.call_kimi(
            {"apiKey": "k", "default_model": "kimi-k2.7"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await kimi.call_kimi(
            {"apiKey": "k", "default_model": "kimi-k2.7"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_kimi HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestKimiCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_kimi_chat_success(self):
        provider = {
            "id": "kimi", "apiKey": "sk-kimi-test",
            "api_base": "https://api.moonshot.cn/v1",
            "default_model": "kimi-k2.7",
            "config": {"models": ["kimi-k2.7", "moonshot-v1-128k"]},
        }
        with respx.mock(base_url="https://api.moonshot.cn") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("kimi-k2.7", 9, 14))
            )
            res = await kimi.call_kimi(
                provider,
                {"model": "kimi-k2.7",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "kimi-k2.7"
        assert res["data"]["usage"]["total_tokens"] == 23

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_kimi_moonshot_v1_128k(self):
        provider = {
            "id": "kimi", "apiKey": "sk-kimi",
            "api_base": "https://api.moonshot.cn/v1",
            "default_model": "kimi-k2.7",
        }
        with respx.mock(base_url="https://api.moonshot.cn") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("moonshot-v1-128k", 50, 200))
            )
            res = await kimi.call_kimi(
                provider,
                {"model": "moonshot-v1-128k",
                 "messages": [{"role": "user", "content": "Long text"}]},
            )
        assert res["ok"] is True
        assert "moonshot-v1-128k" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_kimi_http_5xx_returns_api_error(self):
        provider = {
            "id": "kimi", "apiKey": "k",
            "api_base": "https://api.moonshot.cn/v1",
            "default_model": "kimi-k2.7",
        }
        with respx.mock(base_url="https://api.moonshot.cn") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal"}})
            )
            res = await kimi.call_kimi(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestKimiRouting:
    def test_route_family_kimi(self, tmp_registry_db):
        r = reg.get_registry()
        k = r.route(family="kimi", prefer="cost")
        assert k is not None
        assert k.id == "kimi"

    def test_route_cost_kimi_vs_other(self, tmp_registry_db):
        """Within chat-providers (openai/claude/etc), kimi is competitive on cost.
        Across all families the cheapest route should pick a low-cost family.
        """
        r = reg.get_registry()
        # Route per-family, just verify kimi family picks kimi.
        k = r.route(family="kimi", prefer="cost")
        assert k.id == "kimi"
        assert k.price_per_1k_input + k.price_per_1k_output < 0.01

    def test_route_kimi_speed(self, tmp_registry_db):
        r = reg.get_registry()
        k = r.route(family="kimi", prefer="speed")
        assert k.id == "kimi"
        assert k.latency_p50_ms == 700

    def test_route_kimi_trust(self, tmp_registry_db):
        r = reg.get_registry()
        k = r.route(family="kimi", prefer="trust")
        assert k.id == "kimi"
        assert k.trust_level == "verified"