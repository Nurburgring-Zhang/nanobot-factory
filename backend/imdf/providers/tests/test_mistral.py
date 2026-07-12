"""P19-B2: Tests for Mistral AI provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_mistral sync error paths
- call_mistral HTTP success path (mocked)
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
from providers import mistral


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
                "message": {"role": "assistant", "content": "Bonjour, je suis Mistral"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestMistralDescriptor:
    def test_default_descriptor(self):
        mp = mistral.MistralProvider()
        assert mp.id == "mistral"
        assert mp.family == "mistral"
        assert mp.default_model == "mistral-large-latest"
        assert "mistral.ai" in mp.api_base
        assert mp.price_per_1k_input == mistral.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        mp = mistral.MistralProvider()
        kw = mp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "mistral"
        assert p.config["protocol"] == "openai-compatible"
        assert "mistral-large-latest" in p.config["models"]
        assert "mixtral-8x7b" in p.config["models"]

    def test_sample_providers_includes_mistral(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "mistral" in ids
        m = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "mistral")
        assert m.family == "mistral"
        assert m.config["protocol"] == "openai-compatible"
        assert m.trust_level == "official"

    def test_provider_family_enum_includes_mistral(self):
        assert reg.ProviderFamily.MISTRAL.value == "mistral"

    def test_registry_upserts_mistral(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "mistral" in ids
        m = r.get("mistral")
        assert m is not None
        assert m.default_model == "mistral-large-latest"

    def test_mistral_has_vision_models(self):
        """Mistral pixtral models should be in vision_models config."""
        mp = mistral.MistralProvider()
        assert "pixtral-12b-2409" in mp.config["vision_models"]
        assert mp.config["supports_vision"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestMistralCost:
    def test_zero_tokens(self):
        assert mistral.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.002 + 0.006 = 0.008
        cost = mistral.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.008) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $2.00 + $6.00 = $8.00
        cost = mistral.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 8.00) < 1e-6

    def test_mistral_more_expensive_than_deepseek(self):
        """Compare via in-memory SAMPLE_PROVIDERS list — mistral is the most
        expensive in batch 3 so it must be more expensive than deepseek
        (cheapest in P19-A1)."""
        from providers import registry as reg
        mistral_row = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "mistral")
        deepseek_row = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "deepseek")
        mistral_total = mistral_row.price_per_1k_input + mistral_row.price_per_1k_output
        deepseek_total = deepseek_row.price_per_1k_input + deepseek_row.price_per_1k_output
        assert mistral_total > deepseek_total


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_mistral sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestMistralCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await mistral.call_mistral({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        res = await mistral.call_mistral(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await mistral.call_mistral(
            {"apiKey": "k", "default_model": "mistral-large-latest"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await mistral.call_mistral(
            {"apiKey": "k", "default_model": "mistral-large-latest"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_mistral HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestMistralCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_mistral_large_chat_success(self):
        provider = {
            "id": "mistral", "apiKey": "sk-mistral-test",
            "api_base": "https://api.mistral.ai/v1",
            "default_model": "mistral-large-latest",
            "config": {"models": ["mistral-large-latest", "mixtral-8x7b"]},
        }
        with respx.mock(base_url="https://api.mistral.ai") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("mistral-large-latest", 10, 25))
            )
            res = await mistral.call_mistral(
                provider,
                {"model": "mistral-large-latest",
                 "messages": [{"role": "user", "content": "Bonjour"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "mistral-large-latest"
        assert res["data"]["usage"]["total_tokens"] == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_mistral_mixtral_8x7b(self):
        provider = {
            "id": "mistral", "apiKey": "sk-mistral",
            "api_base": "https://api.mistral.ai/v1",
            "default_model": "mistral-large-latest",
        }
        with respx.mock(base_url="https://api.mistral.ai") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("mixtral-8x7b", 50, 200))
            )
            res = await mistral.call_mistral(
                provider,
                {"model": "mixtral-8x7b",
                 "messages": [{"role": "user", "content": "Long text"}]},
            )
        assert res["ok"] is True
        assert "mixtral-8x7b" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_mistral_http_5xx_returns_api_error(self):
        provider = {
            "id": "mistral", "apiKey": "k",
            "api_base": "https://api.mistral.ai/v1",
            "default_model": "mistral-large-latest",
        }
        with respx.mock(base_url="https://api.mistral.ai") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal"}})
            )
            res = await mistral.call_mistral(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestMistralRouting:
    def test_route_family_mistral(self, tmp_registry_db):
        r = reg.get_registry()
        m = r.route(family="mistral", prefer="cost")
        assert m is not None
        assert m.id == "mistral"

    def test_route_mistral_speed(self, tmp_registry_db):
        r = reg.get_registry()
        m = r.route(family="mistral", prefer="speed")
        assert m.id == "mistral"
        assert m.latency_p50_ms == 700

    def test_route_mistral_trust(self, tmp_registry_db):
        r = reg.get_registry()
        m = r.route(family="mistral", prefer="trust")
        assert m.id == "mistral"
        assert m.trust_level == "official"
