"""P19-B2: Tests for Stepfun (阶跃星辰) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_stepfun sync error paths
- call_stepfun HTTP success path (mocked)
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
from providers import stepfun


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
                "message": {"role": "assistant", "content": "你好,我是 step"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestStepfunDescriptor:
    def test_default_descriptor(self):
        sp = stepfun.StepfunProvider()
        assert sp.id == "stepfun"
        assert sp.family == "stepfun"
        assert sp.default_model == "step-1-8k"
        assert "stepfun.com" in sp.api_base
        assert sp.price_per_1k_input == stepfun.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        sp = stepfun.StepfunProvider()
        kw = sp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "stepfun"
        assert p.config["protocol"] == "openai-compatible"
        assert "step-1-8k" in p.config["models"]
        assert "step-1-32k" in p.config["models"]

    def test_sample_providers_includes_stepfun(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "stepfun" in ids
        s = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "stepfun")
        assert s.family == "stepfun"
        assert s.config["protocol"] == "openai-compatible"
        assert s.trust_level == "verified"

    def test_provider_family_enum_includes_stepfun(self):
        assert reg.ProviderFamily.STEPFUN.value == "stepfun"

    def test_registry_upserts_stepfun(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "stepfun" in ids
        s = r.get("stepfun")
        assert s is not None
        assert s.default_model == "step-1-8k"

    def test_stepfun_has_vision_models(self):
        sp = stepfun.StepfunProvider()
        assert "step-1v-8k" in sp.config["vision_models"]
        assert sp.config["supports_vision"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestStepfunCost:
    def test_zero_tokens(self):
        assert stepfun.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.00025 + 0.00075 = 0.001
        cost = stepfun.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.001) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.25 + $0.75 = $1.00
        cost = stepfun.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 1.00) < 1e-6

    def test_stepfun_cheapest_in_batch(self):
        """Stepfun is the second-cheapest in P19-B2 batch 3
        (nova $0.20/$0.60 < stepfun $0.25/$0.75, but stepfun still beats
        minimax, mistral, cohere)."""
        from providers import mistral as _ms
        from providers import cohere as _co
        from providers import minimax as _mn
        from providers import nova as _nv
        sf = stepfun.compute_cost_usd(100_000, 100_000)
        ms = _ms.compute_cost_usd(100_000, 100_000)
        co = _co.compute_cost_usd(100_000, 100_000)
        mn = _mn.compute_cost_usd(100_000, 100_000)
        nv = _nv.compute_cost_usd(100_000, 100_000)
        assert sf < ms
        assert sf < co
        assert sf < mn
        # Nova ($0.20/$0.60) is cheaper than stepfun ($0.25/$0.75)
        assert sf > nv


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_stepfun sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestStepfunCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await stepfun.call_stepfun({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("STEPFUN_API_KEY", raising=False)
        monkeypatch.delenv("STEP_API_KEY", raising=False)
        res = await stepfun.call_stepfun(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await stepfun.call_stepfun(
            {"apiKey": "k", "default_model": "step-1-8k"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await stepfun.call_stepfun(
            {"apiKey": "k", "default_model": "step-1-8k"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_stepfun HTTP mocked
# ═══════════════════════════════════════════════════════════════════════════

class TestStepfunCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_stepfun_step_1_8k_chat_success(self):
        provider = {
            "id": "stepfun", "apiKey": "sk-stepfun-test",
            "api_base": "https://api.stepfun.com/v1",
            "default_model": "step-1-8k",
            "config": {"models": ["step-1-8k", "step-1-32k"]},
        }
        with respx.mock(base_url="https://api.stepfun.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("step-1-8k", 10, 25))
            )
            res = await stepfun.call_stepfun(
                provider,
                {"model": "step-1-8k",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "step-1-8k"
        assert res["data"]["usage"]["total_tokens"] == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_stepfun_step_1_32k(self):
        provider = {
            "id": "stepfun", "apiKey": "sk-stepfun",
            "api_base": "https://api.stepfun.com/v1",
            "default_model": "step-1-8k",
        }
        with respx.mock(base_url="https://api.stepfun.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("step-1-32k", 50, 200))
            )
            res = await stepfun.call_stepfun(
                provider,
                {"model": "step-1-32k",
                 "messages": [{"role": "user", "content": "Long text"}]},
            )
        assert res["ok"] is True
        assert "step-1-32k" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_stepfun_http_5xx_returns_api_error(self):
        provider = {
            "id": "stepfun", "apiKey": "k",
            "api_base": "https://api.stepfun.com/v1",
            "default_model": "step-1-8k",
        }
        with respx.mock(base_url="https://api.stepfun.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal"}})
            )
            res = await stepfun.call_stepfun(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestStepfunRouting:
    def test_route_family_stepfun(self, tmp_registry_db):
        r = reg.get_registry()
        s = r.route(family="stepfun", prefer="cost")
        assert s is not None
        assert s.id == "stepfun"

    def test_route_stepfun_speed(self, tmp_registry_db):
        r = reg.get_registry()
        s = r.route(family="stepfun", prefer="speed")
        assert s.id == "stepfun"
        assert s.latency_p50_ms == 500
