"""P19-B2: Tests for MiniMax (MiniMax abab) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_minimax sync error paths
- call_minimax HTTP success path (mocked)
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
from providers import minimax


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
                "message": {"role": "assistant", "content": "你好,我是 abab"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestMiniMaxDescriptor:
    def test_default_descriptor(self):
        mp = minimax.MiniMaxProvider()
        assert mp.id == "minimax"
        assert mp.family == "minimax"
        assert mp.default_model == "abab-6.5s"
        assert "minimax.chat" in mp.api_base
        assert mp.price_per_1k_input == minimax.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        mp = minimax.MiniMaxProvider()
        kw = mp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "minimax"
        assert p.config["protocol"] == "openai-compatible"
        assert "abab-6.5s" in p.config["models"]
        assert "abab-6.5-chat" in p.config["models"]

    def test_sample_providers_includes_minimax(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "minimax" in ids
        m = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "minimax")
        assert m.family == "minimax"
        assert m.config["protocol"] == "openai-compatible"
        assert m.trust_level == "verified"

    def test_provider_family_enum_includes_minimax(self):
        assert reg.ProviderFamily.MINIMAX.value == "minimax"

    def test_registry_upserts_minimax(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "minimax" in ids
        m = r.get("minimax")
        assert m is not None
        assert m.default_model == "abab-6.5s"

    def test_minimax_has_long_context(self):
        mp = minimax.MiniMaxProvider()
        assert mp.config["max_context_tokens"] >= 128000
        assert mp.config["region"] == "cn"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestMiniMaxCost:
    def test_zero_tokens(self):
        assert minimax.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0006 + 0.0018 = 0.0024
        cost = minimax.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0024) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.60 + $1.80 = $2.40
        cost = minimax.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 2.40) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_minimax sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestMiniMaxCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await minimax.call_minimax({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.delenv("ABAB_API_KEY", raising=False)
        res = await minimax.call_minimax(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await minimax.call_minimax(
            {"apiKey": "k", "default_model": "abab-6.5s"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await minimax.call_minimax(
            {"apiKey": "k", "default_model": "abab-6.5s"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_minimax HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestMiniMaxCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_minimax_abab_6_5s_chat_success(self):
        provider = {
            "id": "minimax", "apiKey": "sk-minimax-test",
            "api_base": "https://api.minimax.chat/v1",
            "default_model": "abab-6.5s",
            "config": {"models": ["abab-6.5s", "abab-6.5-chat"]},
        }
        with respx.mock(base_url="https://api.minimax.chat") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("abab-6.5s", 10, 25))
            )
            res = await minimax.call_minimax(
                provider,
                {"model": "abab-6.5s",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "abab-6.5s"
        assert res["data"]["usage"]["total_tokens"] == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_minimax_abab_6_5_chat(self):
        provider = {
            "id": "minimax", "apiKey": "sk-minimax",
            "api_base": "https://api.minimax.chat/v1",
            "default_model": "abab-6.5s",
        }
        with respx.mock(base_url="https://api.minimax.chat") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("abab-6.5-chat", 50, 200))
            )
            res = await minimax.call_minimax(
                provider,
                {"model": "abab-6.5-chat",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert "abab-6.5-chat" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_minimax_http_5xx_returns_api_error(self):
        provider = {
            "id": "minimax", "apiKey": "k",
            "api_base": "https://api.minimax.chat/v1",
            "default_model": "abab-6.5s",
        }
        with respx.mock(base_url="https://api.minimax.chat") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal"}})
            )
            res = await minimax.call_minimax(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestMiniMaxRouting:
    def test_route_family_minimax(self, tmp_registry_db):
        r = reg.get_registry()
        m = r.route(family="minimax", prefer="cost")
        assert m is not None
        assert m.id == "minimax"

    def test_route_minimax_speed(self, tmp_registry_db):
        r = reg.get_registry()
        m = r.route(family="minimax", prefer="speed")
        assert m.id == "minimax"
        assert m.latency_p50_ms == 600
