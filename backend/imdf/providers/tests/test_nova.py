"""P19-B2: Tests for Nova (零一万物) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_nova sync error paths
- call_nova HTTP success path (mocked)
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
from providers import nova


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
                "message": {"role": "assistant", "content": "你好,我是 yi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestNovaDescriptor:
    def test_default_descriptor(self):
        np = nova.NovaProvider()
        assert np.id == "nova"
        assert np.family == "nova"
        assert np.default_model == "yi-34b"
        assert "lingyiwanwu" in np.api_base
        assert np.price_per_1k_input == nova.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        np = nova.NovaProvider()
        kw = np.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "nova"
        assert p.config["protocol"] == "openai-compatible"
        assert "yi-34b" in p.config["models"]
        assert "yi-6b" in p.config["models"]

    def test_sample_providers_includes_nova(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "nova" in ids
        n = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "nova")
        assert n.family == "nova"
        assert n.config["protocol"] == "openai-compatible"
        assert n.trust_level == "verified"

    def test_provider_family_enum_includes_nova(self):
        assert reg.ProviderFamily.NOVA.value == "nova"

    def test_registry_upserts_nova(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "nova" in ids
        n = r.get("nova")
        assert n is not None
        assert n.default_model == "yi-34b"

    def test_nova_has_long_context(self):
        np = nova.NovaProvider()
        assert np.config["max_context_tokens"] >= 128000
        assert np.config["region"] == "cn"
        assert "yi-vl-6b" in np.config["vision_models"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestNovaCost:
    def test_zero_tokens(self):
        assert nova.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0002 + 0.0006 = 0.0008
        cost = nova.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0008) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.20 + $0.60 = $0.80
        cost = nova.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 0.80) < 1e-6

    def test_nova_cheapest_in_batch(self):
        """Nova ($0.20/$0.60) is the cheapest provider in P19-B2 batch 3."""
        from providers import stepfun as _sf
        from providers import mistral as _ms
        from providers import cohere as _co
        from providers import minimax as _mn
        nv = nova.compute_cost_usd(100_000, 100_000)
        sf = _sf.compute_cost_usd(100_000, 100_000)
        ms = _ms.compute_cost_usd(100_000, 100_000)
        co = _co.compute_cost_usd(100_000, 100_000)
        mn = _mn.compute_cost_usd(100_000, 100_000)
        # Nova is the cheapest in batch 3
        assert nv < sf
        assert nv < ms
        assert nv < co
        assert nv < mn


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_nova sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestNovaCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await nova.call_nova({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("NOVA_API_KEY", raising=False)
        monkeypatch.delenv("YI_API_KEY", raising=False)
        monkeypatch.delenv("LINGYIWANWU_API_KEY", raising=False)
        res = await nova.call_nova(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await nova.call_nova(
            {"apiKey": "k", "default_model": "yi-34b"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await nova.call_nova(
            {"apiKey": "k", "default_model": "yi-34b"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_nova HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestNovaCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_nova_yi_34b_chat_success(self):
        provider = {
            "id": "nova", "apiKey": "sk-nova-test",
            "api_base": "https://api.lingyiwanwu.com/v1",
            "default_model": "yi-34b",
            "config": {"models": ["yi-34b", "yi-6b"]},
        }
        with respx.mock(base_url="https://api.lingyiwanwu.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("yi-34b", 10, 25))
            )
            res = await nova.call_nova(
                provider,
                {"model": "yi-34b",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "yi-34b"
        assert res["data"]["usage"]["total_tokens"] == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_nova_yi_6b(self):
        provider = {
            "id": "nova", "apiKey": "sk-nova",
            "api_base": "https://api.lingyiwanwu.com/v1",
            "default_model": "yi-34b",
        }
        with respx.mock(base_url="https://api.lingyiwanwu.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("yi-6b", 50, 200))
            )
            res = await nova.call_nova(
                provider,
                {"model": "yi-6b",
                 "messages": [{"role": "user", "content": "Short text"}]},
            )
        assert res["ok"] is True
        assert "yi-6b" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_nova_http_5xx_returns_api_error(self):
        provider = {
            "id": "nova", "apiKey": "k",
            "api_base": "https://api.lingyiwanwu.com/v1",
            "default_model": "yi-34b",
        }
        with respx.mock(base_url="https://api.lingyiwanwu.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal"}})
            )
            res = await nova.call_nova(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestNovaRouting:
    def test_route_family_nova(self, tmp_registry_db):
        r = reg.get_registry()
        n = r.route(family="nova", prefer="cost")
        assert n is not None
        assert n.id == "nova"

    def test_route_nova_speed(self, tmp_registry_db):
        r = reg.get_registry()
        n = r.route(family="nova", prefer="speed")
        assert n.id == "nova"
        assert n.latency_p50_ms == 500
