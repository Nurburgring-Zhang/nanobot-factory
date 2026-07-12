"""P19-A2: Tests for Baidu ERNIE (文心) provider.

Covers:
- Descriptor + registry upsert
- compute_cost_usd math
- access_token caching + fetch flow (mocked)
- call_baidu sync error paths (missing creds, image/video kind)
- call_baidu HTTP success path (mocked OAuth + chat)
- Family routing
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

try:
    import respx
    from httpx import Response as HttpxResponse
    HAS_RESPX = True
except ImportError:
    HAS_RESPX = False

from providers import registry as reg
from providers import baidu


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


@pytest.fixture(autouse=True)
def _clear_baidu_token_cache():
    baidu.clear_token_cache()
    yield
    baidu.clear_token_cache()


def _oauth_response(token: str = "tok-abc-123", expires_in: int = 2592000) -> dict:
    return {
        "access_token": token,
        "expires_in": expires_in,
        "scope": "ai_custom_all",
        "session_key": "...",
    }


def _ernie_response(text: str = "百度回答", pt: int = 8, ct: int = 12) -> dict:
    return {
        "id": f"ernie-{pt+ct}",
        "object": "chat.completion",
        "created": int(time.time()),
        "result": text,
        "is_truncated": False,
        "need_clear_history": False,
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Descriptor + registry wiring
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduDescriptor:
    def test_default_descriptor(self):
        bp = baidu.BaiduProvider()
        assert bp.id == "baidu"
        assert bp.family == "baidu"
        assert bp.default_model == "ernie-4.0-turbo"
        assert "aip.baidubce.com" in bp.api_base
        assert bp.price_per_1k_input == baidu.PRICE_INPUT_USD_PER_1K

    def test_to_registry_kwargs(self, tmp_registry_db):
        bp = baidu.BaiduProvider()
        kw = bp.to_registry_kwargs()
        p = reg.Provider(**kw)
        assert p.id == "baidu"
        assert p.config["protocol"] == "baidu"
        assert p.config["auth"] == "client_credentials"
        assert "ernie-4.0-turbo" in p.config["models"]

    def test_sample_providers_includes_baidu(self, tmp_registry_db):
        ids = [p.id for p in reg.SAMPLE_PROVIDERS]
        assert "baidu" in ids
        b = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "baidu")
        assert b.family == "baidu"
        assert b.config["protocol"] == "baidu"
        assert b.trust_level == "verified"

    def test_provider_family_enum_includes_baidu(self):
        assert reg.ProviderFamily.BAIDU.value == "baidu"

    def test_registry_upserts_baidu(self, tmp_registry_db):
        r = reg.get_registry()
        ids = {p.id for p in r.list()}
        assert "baidu" in ids
        b = r.get("baidu")
        assert b is not None
        assert b.default_model == "ernie-4.0-turbo"


# ═══════════════════════════════════════════════════════════════════════════
# 2. compute_cost_usd math
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduCost:
    def test_zero_tokens(self):
        assert baidu.compute_cost_usd(0, 0) == 0.0

    def test_basic_cost(self):
        # 1000 in + 1000 out → 0.00035 + 0.001 = 0.00135
        cost = baidu.compute_cost_usd(1000, 1000)
        assert abs(cost - 0.00135) < 1e-9

    def test_uses_per_1k_pricing(self):
        # 1M in + 1M out → $0.35 + $1.00 = $1.35
        cost = baidu.compute_cost_usd(1_000_000, 1_000_000)
        assert abs(cost - 1.35) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# 3. Credential resolution
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduCredentials:
    def test_resolve_explicit_colon_form(self):
        creds = baidu._resolve_credentials("client1:secret1")
        assert creds == {"client_id": "client1", "client_secret": "secret1"}

    def test_resolve_env_vars(self, monkeypatch):
        monkeypatch.setenv("BAIDU_CLIENT_ID", "env-id")
        monkeypatch.setenv("BAIDU_CLIENT_SECRET", "env-secret")
        creds = baidu._resolve_credentials()
        assert creds == {"client_id": "env-id", "client_secret": "env-secret"}

    def test_resolve_env_combined(self, monkeypatch):
        monkeypatch.delenv("BAIDU_CLIENT_ID", raising=False)
        monkeypatch.delenv("BAIDU_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("BAIDU_API_KEY", "id2:sec2")
        creds = baidu._resolve_credentials()
        assert creds == {"client_id": "id2", "client_secret": "sec2"}

    def test_resolve_missing(self):
        creds = baidu._resolve_credentials("")
        assert creds["client_id"] == ""
        assert creds["client_secret"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# 4. access_token caching
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduOAuth:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_oauth_fetch_and_cache(self):
        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                return_value=HttpxResponse(200, json=_oauth_response("tok-first", expires_in=3600))
            )
            r1 = await baidu._fetch_access_token("id1", "sec1")
            assert r1["ok"] is True
            assert r1["access_token"] == "tok-first"
            assert r1["cached"] is False

            # Second call: cache hit (no new HTTP request)
            r2 = await baidu._fetch_access_token("id1", "sec1")
            assert r2["ok"] is True
            assert r2["access_token"] == "tok-first"
            assert r2["cached"] is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_oauth_force_refresh(self):
        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                side_effect=[
                    HttpxResponse(200, json=_oauth_response("tok-1", expires_in=3600)),
                    HttpxResponse(200, json=_oauth_response("tok-2", expires_in=3600)),
                ]
            )
            r1 = await baidu._fetch_access_token("id1", "sec1")
            r2 = await baidu._fetch_access_token("id1", "sec1", force=True)
            assert r1["access_token"] == "tok-1"
            assert r2["access_token"] == "tok-2"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_oauth_error_returns_error(self):
        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                return_value=HttpxResponse(401, json={"error": "invalid_client"})
            )
            r = await baidu._fetch_access_token("bad", "bad")
            assert r["ok"] is False
            assert r["code"] == "oauth_error"

    def test_clear_token_cache_helper(self):
        baidu._TOKEN_CACHE["fake-fp"] = {"token": "x", "expires_at": time.time() + 3600}
        baidu.clear_token_cache()
        assert baidu._TOKEN_CACHE == {}


# ═══════════════════════════════════════════════════════════════════════════
# 5. call_baidu sync error paths
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduCallSync:
    @pytest.mark.asyncio
    async def test_missing_provider(self):
        res = await baidu.call_baidu({}, {"messages": []})
        assert res["ok"] is False
        assert res["code"] == "missing_provider"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        res = await baidu.call_baidu(
            {"api_base": "https://x.test", "config": {}},
            {"messages": [{"role": "user", "content": "hi"}]},
        )
        assert res["ok"] is False
        assert res["code"] == "missing_credentials"

    @pytest.mark.asyncio
    async def test_image_kind_unsupported(self):
        res = await baidu.call_baidu(
            {"apiKey": "id:sec", "default_model": "ernie-4.0-turbo"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="image",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"

    @pytest.mark.asyncio
    async def test_video_kind_unsupported(self):
        res = await baidu.call_baidu(
            {"apiKey": "id:sec", "default_model": "ernie-4.0-turbo"},
            {"messages": [{"role": "user", "content": "hi"}]},
            kind="video",
        )
        assert res["ok"] is False
        assert res["code"] == "unsupported_kind"


# ═══════════════════════════════════════════════════════════════════════════
# 6. call_baidu HTTP mocked (OAuth + chat)
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduCallHTTP:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_baidu_chat_success(self):
        provider = {
            "id": "baidu", "apiKey": "id:secret",
            "api_base": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
            "default_model": "ernie-4.0-turbo",
            "config": {"models": ["ernie-4.0-turbo", "ernie-4.0-8k"]},
        }
        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                return_value=HttpxResponse(200, json=_oauth_response("tok-x"))
            )
            mock.post("/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-turbo").mock(
                return_value=HttpxResponse(200, json=_ernie_response("你好百度", 9, 14))
            )
            res = await baidu.call_baidu(
                provider,
                {"model": "ernie-4.0-turbo",
                 "messages": [{"role": "user", "content": "你好"}]},
            )
        assert res["ok"] is True
        assert res["data"]["choices"][0]["message"]["content"] == "你好百度"
        assert res["data"]["usage"]["total_tokens"] == 23

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_baidu_system_message_passed(self):
        provider = {
            "id": "baidu", "apiKey": "id:secret",
            "api_base": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
            "default_model": "ernie-4.0-turbo",
        }
        captured = {}
        def _capture(request):
            import json as _json
            captured.update(_json.loads(request.content))
            return HttpxResponse(200, json=_ernie_response())

        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                return_value=HttpxResponse(200, json=_oauth_response())
            )
            mock.post("/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-turbo").mock(
                side_effect=_capture
            )
            await baidu.call_baidu(
                provider,
                {"messages": [
                    {"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "hi"},
                ]},
            )
        assert "system" in captured
        assert "Be brief." in captured["system"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_baidu_oauth_failed_aborts(self):
        provider = {
            "id": "baidu", "apiKey": "bad:bad",
            "api_base": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
            "default_model": "ernie-4.0-turbo",
        }
        with respx.mock(base_url="https://aip.baidubce.com") as mock:
            mock.post("/oauth/2.0/token").mock(
                return_value=HttpxResponse(403, json={"error": "forbidden"})
            )
            res = await baidu.call_baidu(
                provider,
                {"messages": [{"role": "user", "content": "hi"}]},
            )
        assert res["ok"] is False
        assert res["code"] in ("oauth_error", "request_failed")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Routing
# ═══════════════════════════════════════════════════════════════════════════

class TestBaiduRouting:
    def test_route_family_baidu(self, tmp_registry_db):
        r = reg.get_registry()
        b = r.route(family="baidu", prefer="cost")
        assert b is not None
        assert b.id == "baidu"

    def test_route_baidu_speed(self, tmp_registry_db):
        r = reg.get_registry()
        b = r.route(family="baidu", prefer="speed")
        assert b.id == "baidu"
        assert b.latency_p50_ms == 800

    def test_route_baidu_trust(self, tmp_registry_db):
        r = reg.get_registry()
        b = r.route(family="baidu", prefer="trust")
        assert b.id == "baidu"
        assert b.trust_level == "verified"

    def test_baidu_oauth_base_in_config(self, tmp_registry_db):
        b = next(p for p in reg.SAMPLE_PROVIDERS if p.id == "baidu")
        assert b.config["oauth_base"] == "https://aip.baidubce.com"
        assert b.config["auth"] == "client_credentials"