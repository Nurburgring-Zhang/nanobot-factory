"""P19-A2: Tests for Google Gemini provider.

Covers:
- Descriptor ``GeminiProvider.to_registry_kwargs`` produces kwargs the
  ``ProviderRegistry`` accepts.
- ``SAMPLE_PROVIDERS`` includes a gemini entry with expected pricing
  and config protocol tag.
- ``compute_cost_usd`` math sanity check.
- ``call_gemini`` short-circuits cleanly when ``apiKey`` is missing.
- ``call_gemini`` issues a real REST POST when an api key is provided
  (mocked via respx).
- Family routing picks gemini by ``family=gemini`` and excludes mock.
"""
from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, patch

import pytest

# Optional respx (httpx mocking) — same pattern as tests/test_provider_registry.py
try:
    import respx
    from httpx import Response as HttpxResponse
    HAS_RESPX = True
except ImportError:
    HAS_RESPX = False

from providers import registry as reg
from providers import gemini


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_registry_db(tmp_path, monkeypatch):
    """Isolated sqlite DB for the registry."""
    db = tmp_path / "providers.db"
    monkeypatch.setattr(reg, "_DB_PATH", db)
    try:
        reg.reset_registry_for_test()
    except Exception:
        pass
    # Initialize schema on the tmp DB (get_db_path skips auto-init when
    # _DB_PATH is set explicitly).
    try:
        reg._init_db()
    except Exception:
        pass
    yield reg
    try:
        reg.reset_registry_for_test()
    except Exception:
        pass


def _gemini_response(text: str = "Hi from Gemini",
                    pt: int = 8, ct: int = 12) -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": pt,
            "candidatesTokenCount": ct,
            "totalTokenCount": pt + ct,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiDescriptor:
    def test_default_descriptor(self):
        gp = gemini.GeminiProvider()
        assert gp.id == "gemini"
        assert gp.family == "gemini"
        assert gp.default_model == "gemini-2.0-flash"
        assert "generativelanguage.googleapis.com" in gp.api_base
        assert gp.price_per_1k_input == gemini.PRICE_INPUT_USD_PER_1K
        assert gp.price_per_1k_output == gemini.PRICE_OUTPUT_USD_PER_1K

    def test_to_registry_kwargs_compatible(self, tmp_registry_db):
        gp = gemini.GeminiProvider()
        kw = gp.to_registry_kwargs()
        # Must contain all fields the Provider dataclass requires.
        p = reg.Provider(**kw)
        assert p.id == "gemini"
        assert p.family == "gemini"
        assert p.config["protocol"] == "gemini"

    def test_sample_providers_includes_gemini(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "gemini" in ids
        gem = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "gemini")
        assert gem.family == "gemini"
        assert gem.config["protocol"] == "gemini"
        # Three default models present
        assert set(gem.config["models"]) >= {
            "gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.0-flash-vision"
        }

    def test_provider_family_enum_includes_gemini(self):
        assert reg.ProviderFamily.GEMINI.value == "gemini"

    def test_registry_upserts_gemini(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "gemini" in ids
        # Re-fetch by id
        gem = r.get("gemini")
        assert gem is not None
        assert gem.default_model == "gemini-2.0-flash"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiCost:
    def test_zero_tokens(self):
        assert gemini.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0007 + 0.0021 = 0.0028 USD
        cost = gemini.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0028) < 1e-9

    def test_input_only(self):
        cost = gemini.compute_cost_usd(10_000, 0)
        assert abs(cost - 10 * 0.0007) < 1e-9

    def test_output_dominates(self):
        cost = gemini.compute_cost_usd(100, 10_000)
        # 0.0001 * 0.0007 + 10 * 0.0021 ≈ 0.02107
        assert cost > 0.02

    def test_uses_per_1k_pricing(self):
        # 1M tokens in + 1M tokens out → $0.70 + $2.10 = $2.80
        cost = gemini.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 2.8) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_gemini — pure logic (no HTTP)
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await gemini.call_gemini({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        res = await gemini.call_gemini(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_unsupported_kind(self):
        res = await gemini.call_gemini(
            {"apiKey": "k", "api_base": "https://x.test",
             "default_model": "gemini-2.0-flash"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "invalid_kind"

    @pytest.mark.asyncio
    async def test_env_api_key_resolution(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("GOOGLE_API_KEY", "env-key-123")
        res = await gemini.call_gemini(
            {"api_base": "https://x.test"},
            {"messages": []},
        )
        # Should reach httpx path, fail with request_failed (no real server).
        # The test is "apiKey resolved from env, did not short-circuit on missing_api_key".
        assert res["code"] != "missing_api_key"


# ═══════════════════════════════════════════════════════════════════════════
# 4. call_gemini — HTTP mocked via respx
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_gemini_chat_success(self):
        provider = {
            "id": "gemini",
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "apiKey": "AIza-test",
            "default_model": "gemini-2.0-flash",
            "config": {"models": ["gemini-2.0-flash"]},
        }
        with respx.mock(base_url="https://generativelanguage.googleapis.com") as mock:
            mock.post("/v1beta/models/gemini-2.0-flash:generateContent").mock(
                return_value=HttpxResponse(200, json=_gemini_response("Hello!", 9, 14))
            )
            res = await gemini.call_gemini(
                provider,
                {"model": "gemini-2.0-flash",
                 "messages": [{"role": "user", "content": "Hi"}]},
            )
        assert res["ok"] is True
        assert res["data"]["choices"][0]["message"]["content"] == "Hello!"
        assert res["data"]["usage"]["total_tokens"] == 23
        assert res["provider_id"] == "gemini"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_gemini_system_message_prefixed(self):
        """Gemini v1beta has no system role — system message must prefix first user turn."""
        provider = {
            "id": "gemini", "apiKey": "k",
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.0-flash",
        }
        captured = {}
        def _capture(request):
            import json as _json
            captured.update(_json.loads(request.content))
            return HttpxResponse(200, json=_gemini_response())

        with respx.mock(base_url="https://generativelanguage.googleapis.com") as mock:
            mock.post("/v1beta/models/gemini-2.0-flash:generateContent").mock(
                side_effect=_capture
            )
            await gemini.call_gemini(
                provider,
                {"messages": [
                    {"role": "system", "content": "You are concise."},
                    {"role": "user", "content": "Hi"},
                ]},
            )
        # First content should be system + user merged
        first_text = captured["contents"][0]["parts"][0]["text"]
        assert "You are concise." in first_text
        assert "Hi" in first_text

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_gemini_http_4xx_returns_api_error(self):
        provider = {
            "id": "gemini", "apiKey": "bad",
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.0-flash",
        }
        with respx.mock(base_url="https://generativelanguage.googleapis.com") as mock:
            mock.post("/v1beta/models/gemini-2.0-flash:generateContent").mock(
                return_value=HttpxResponse(403, json={"error": {"message": "key invalid"}})
            )
            res = await gemini.call_gemini(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"
        assert res["status_code"] == 403

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_gemini_timeout_returns_request_failed(self):
        import asyncio as _aio
        provider = {
            "id": "gemini", "apiKey": "k",
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.0-flash",
        }
        with respx.mock(base_url="https://generativelanguage.googleapis.com") as mock:
            mock.post("/v1beta/models/gemini-2.0-flash:generateContent").mock(
                side_effect=_aio.TimeoutError("simulated")
            )
            res = await gemini.call_gemini(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "request_failed"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_gemini_generation_config_passed(self):
        provider = {
            "id": "gemini", "apiKey": "k",
            "api_base": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.0-flash",
        }
        captured = {}
        def _capture(request):
            import json as _json
            captured.update(_json.loads(request.content))
            return HttpxResponse(200, json=_gemini_response())

        with respx.mock(base_url="https://generativelanguage.googleapis.com") as mock:
            mock.post("/v1beta/models/gemini-2.0-flash:generateContent").mock(
                side_effect=_capture
            )
            await gemini.call_gemini(
                provider,
                {"model": "gemini-2.0-flash",
                 "messages": [{"role": "user", "content": "hi"}],
                 "temperature": 0.7, "max_tokens": 256, "top_p": 0.9,
                 "stop": ["END"]},
            )
        gc = captured.get("generationConfig", {})
        assert gc.get("temperature") == 0.7
        assert gc.get("maxOutputTokens") == 256
        assert gc.get("topP") == 0.9
        assert gc.get("stopSequences") == ["END"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Routing — family + cost/speed/trust preferences
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiRouting:
    def test_route_family_gemini_picks_gemini(self, tmp_registry_db):
        r = reg.get_registry()
        # Should find at least one gemini (the only one)
        gem = r.route(family="gemini", prefer="cost")
        assert gem is not None
        assert gem.id == "gemini"

    def test_route_speed_prefers_low_latency(self, tmp_registry_db):
        r = reg.get_registry()
        # Within gemini family only one entry, but verify it returns the right one.
        gem = r.route(family="gemini", prefer="speed")
        assert gem is not None
        assert gem.id == "gemini"
        assert gem.latency_p50_ms == 600  # as configured

    def test_route_trust_prefers_official(self, tmp_registry_db):
        r = reg.get_registry()
        gem = r.route(family="gemini", prefer="trust")
        assert gem is not None
        assert gem.trust_level == "official"
        assert gem.id == "gemini"

    def test_route_fallback_to_mock_when_family_missing(self, tmp_registry_db):
        r = reg.get_registry()
        mock = r.route(family="nonsense-no-such-family")
        assert mock is not None
        assert mock.id == "mock"