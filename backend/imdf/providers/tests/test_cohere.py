"""P19-B2: Tests for Cohere provider (native REST, RAG-optimized).

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- call_cohere sync error paths
- call_cohere HTTP success path (mocked, native /v1/chat format)
- Message conversion OpenAI-style → Cohere style
- Embed kind routed to /v1/embed
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
from providers import cohere


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


def _cohere_chat_response(model: str, input_tokens: int = 8, output_tokens: int = 12) -> dict:
    return {
        "response_id": f"cohere-{model}",
        "text": "Hello from Cohere",
        "generation_id": "abc-123",
        "chat_history": [
            {"role": "USER", "message": "hi"},
            {"role": "CHATBOT", "message": "Hello from Cohere"},
        ],
        "finish_reason": "COMPLETE",
        "meta": {
            "api_version": {"version": "1"},
            "billed_units": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


def _cohere_embed_response(model: str, n_texts: int = 2) -> dict:
    return {
        "id": f"embed-{model}",
        "embeddings": [[0.01] * 1024 for _ in range(n_texts)],
        "texts": ["text-a", "text-b"][:n_texts],
        "meta": {"api_version": {"version": "1"}},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereDescriptor:
    def test_default_descriptor(self):
        cp = cohere.CohereProvider()
        assert cp.id == "cohere"
        assert cp.family == "cohere"
        assert cp.default_model == "command-r-plus"
        assert "cohere.ai" in cp.api_base
        assert cp.price_per_1k_input == cohere.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        cp = cohere.CohereProvider()
        kw = cp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "cohere"
        assert p.config["protocol"] == "cohere"
        assert "command-r-plus" in p.config["models"]
        assert "embed-english-v3.0" in p.config["embed_models"]

    def test_sample_providers_includes_cohere(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "cohere" in ids
        c = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "cohere")
        assert c.family == "cohere"
        assert c.config["protocol"] == "cohere"
        assert c.trust_level == "official"

    def test_provider_family_enum_includes_cohere(self):
        assert reg.ProviderFamily.COHERE.value == "cohere"

    def test_registry_upserts_cohere(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "cohere" in ids
        c = r.get("cohere")
        assert c is not None
        assert c.default_model == "command-r-plus"

    def test_cohere_supports_rag_embed_rerank(self):
        cp = cohere.CohereProvider()
        cfg = cp.config
        assert cfg["supports_rag"] is True
        assert cfg["supports_embed"] is True
        assert cfg["supports_rerank"] is True
        assert cfg["supports_function_call"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereCost:
    def test_zero_tokens(self):
        assert cohere.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.0025 + 0.01 = 0.0125
        cost = cohere.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.0125) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $2.50 + $10.00 = $12.50
        cost = cohere.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 12.50) < 1e-6

    def test_cohere_most_expensive_in_batch(self):
        """Cohere is the most expensive in P19-B2 batch 3."""
        from providers import mistral as _ms
        from providers import stepfun as _sf
        co = cohere.compute_cost_usd(100_000, 100_000)
        ms = _ms.compute_cost_usd(100_000, 100_000)
        sf = _sf.compute_cost_usd(100_000, 100_000)
        assert co > ms
        assert co > sf


# ═══════════════════════════════════════════════════════════════════════════
# 3. call_cohere sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await cohere.call_cohere({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        monkeypatch.delenv("CO_API_KEY", raising=False)
        res = await cohere.call_cohere(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await cohere.call_cohere(
            {"apiKey": "k", "default_model": "command-r-plus"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await cohere.call_cohere(
            {"apiKey": "k", "default_model": "command-r-plus"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Message format conversion
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereMessageConversion:
    def test_simple_user_message(self):
        body = cohere._convert_messages_to_cohere(
            [{"role": "user", "content": "hello"}]
        )
        assert body["message"] == "hello"
        assert body["chat_history"] == []
        assert "preamble" not in body

    def test_system_message_becomes_preamble(self):
        body = cohere._convert_messages_to_cohere([
            {"role": "system", "content": "you are a poet"},
            {"role": "user", "content": "write a haiku"},
        ])
        assert body["preamble"] == "you are a poet"
        assert body["message"] == "write a haiku"
        assert body["chat_history"] == []

    def test_multi_turn_conversation(self):
        body = cohere._convert_messages_to_cohere([
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "what is 1+1?"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "and 2+2?"},
        ])
        assert body["preamble"] == "be helpful"
        assert body["message"] == "and 2+2?"
        # chat_history contains the prior user+assistant turns
        history = body["chat_history"]
        assert len(history) == 2
        assert history[0] == {"role": "user", "message": "what is 1+1?"}
        assert history[1] == {"role": "assistant", "message": "2"}

    def test_multiple_system_messages_concatenated(self):
        body = cohere._convert_messages_to_cohere([
            {"role": "system", "content": "be brief"},
            {"role": "system", "content": "be friendly"},
            {"role": "user", "content": "hi"},
        ])
        assert "be brief" in body["preamble"]
        assert "be friendly" in body["preamble"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. call_cohere HTTP mocked (chat path — native /v1/chat)
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_cohere_command_r_plus_chat_success(self):
        provider = {
            "id": "cohere", "apiKey": "co-test-key",
            "api_base": "https://api.cohere.ai/v1",
            "default_model": "command-r-plus",
            "config": {"models": ["command-r-plus", "command-r"]},
        }
        with respx.mock(base_url="https://api.cohere.ai") as mock:
            mock.post("/v1/chat").mock(
                return_value=HttpxResponse(200, json=_cohere_chat_response("command-r-plus", 10, 25))
            )
            res = await cohere.call_cohere(
                provider,
                {"model": "command-r-plus",
                 "messages": [{"role": "user", "content": "Hello"}]},
            )
        assert res["ok"] is True
        # Verify normalized OpenAI shape
        assert res["data"]["model"] == "command-r-plus"
        assert res["data"]["usage"]["prompt_tokens"] == 10
        assert res["data"]["usage"]["completion_tokens"] == 25
        assert res["data"]["choices"][0]["message"]["content"] == "Hello from Cohere"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_cohere_command_r_chat(self):
        provider = {
            "id": "cohere", "apiKey": "k",
            "api_base": "https://api.cohere.ai/v1",
            "default_model": "command-r-plus",
        }
        with respx.mock(base_url="https://api.cohere.ai") as mock:
            mock.post("/v1/chat").mock(
                return_value=HttpxResponse(200, json=_cohere_chat_response("command-r", 50, 100))
            )
            res = await cohere.call_cohere(
                provider,
                {"model": "command-r",
                 "messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is True
        assert "command-r" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_cohere_http_4xx_returns_api_error(self):
        provider = {
            "id": "cohere", "apiKey": "k",
            "api_base": "https://api.cohere.ai/v1",
            "default_model": "command-r-plus",
        }
        with respx.mock(base_url="https://api.cohere.ai") as mock:
            mock.post("/v1/chat").mock(
                return_value=HttpxResponse(401, json={"message": "invalid api key"})
            )
            res = await cohere.call_cohere(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_cohere_embed_kind(self):
        """embed kind should hit /v1/embed."""
        provider = {
            "id": "cohere", "apiKey": "k",
            "api_base": "https://api.cohere.ai/v1",
            "default_model": "command-r-plus",
            "config": {"embed_models": ["embed-english-v3.0"]},
        }
        with respx.mock(base_url="https://api.cohere.ai") as mock:
            mock.post("/v1/embed").mock(
                return_value=HttpxResponse(200, json=_cohere_embed_response("embed-english-v3.0", 2))
            )
            res = await cohere.call_cohere(
                provider,
                {"texts": ["text-a", "text-b"]},
                kind="embed",
            )
        assert res["ok"] is True
        assert "embeddings" in res["data"]
        assert len(res["data"]["embeddings"]) == 2

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_cohere_passes_temperature_and_max_tokens(self):
        """Verify temperature + max_tokens pass-through to Cohere /v1/chat body."""
        provider = {
            "id": "cohere", "apiKey": "k",
            "api_base": "https://api.cohere.ai/v1",
            "default_model": "command-r-plus",
        }
        captured_body = {}
        def capture(request):
            import json as _json
            captured_body.update(_json.loads(request.content))
            return HttpxResponse(200, json=_cohere_chat_response("command-r-plus"))
        with respx.mock(base_url="https://api.cohere.ai") as mock:
            mock.post("/v1/chat").mock(side_effect=capture)
            res = await cohere.call_cohere(
                provider,
                {"model": "command-r-plus", "temperature": 0.3, "max_tokens": 100,
                 "messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is True
        assert captured_body.get("temperature") == 0.3
        assert captured_body.get("max_tokens") == 100
        assert captured_body.get("model") == "command-r-plus"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestCohereRouting:
    def test_route_family_cohere(self, tmp_registry_db):
        r = reg.get_registry()
        c = r.route(family="cohere", prefer="cost")
        assert c is not None
        assert c.id == "cohere"

    def test_route_cohere_trust(self, tmp_registry_db):
        r = reg.get_registry()
        c = r.route(family="cohere", prefer="trust")
        assert c.id == "cohere"
        assert c.trust_level == "official"
