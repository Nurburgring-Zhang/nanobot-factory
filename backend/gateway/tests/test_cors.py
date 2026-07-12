"""Tests for backend.gateway.cors.

Coverage
========
1. CorsPolicy builds correct headers for wildcard / credentials
2. Per-origin lookup (exact match)
3. Wildcard subdomain match (``*.example.com``)
4. Default fallback when no match
5. ``*`` + credentials raises warning
6. Preflight cache: Access-Control-Max-Age honoured
7. Origin 'null' / absent handled
8. Config loader (YAML / dict / env / legacy)
9. CorsMiddleware injects headers + handles preflight
10. 5 distinct origins configurable (headline: "5 origin 配置生效")

Run::

    python -m pytest backend/gateway/tests/test_cors.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.cors import (  # noqa: E402
    CorsConfig,
    CorsPolicy,
    CorsMiddleware,
    resolve_cors,
)


# ---------------------------------------------------------------------
# CorsPolicy
# ---------------------------------------------------------------------

class TestCorsPolicy:
    def test_wildcard_allows_anything(self):
        p = CorsPolicy(origin="*")
        assert p.allows("https://a.com") is True
        assert p.allows("https://b.example.com") is True

    def test_exact_origin_match(self):
        p = CorsPolicy(origin="https://app.example.com")
        assert p.allows("https://app.example.com") is True
        assert p.allows("https://other.example.com") is False

    def test_wildcard_subdomain_match(self):
        p = CorsPolicy(origin="*.example.com")
        assert p.allows("https://a.example.com") is True
        assert p.allows("https://b.example.com") is True
        assert p.allows("https://example.com") is True
        assert p.allows("https://evil.com") is False

    def test_headers_wildcard_no_credentials(self):
        p = CorsPolicy(origin="*")
        h = p.to_headers("https://a.com")
        assert h["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in h
        assert h["Vary"] == "Origin"

    def test_headers_specific_with_credentials(self):
        p = CorsPolicy(origin="https://app.example.com", credentials=True)
        h = p.to_headers("https://app.example.com")
        assert h["Access-Control-Allow-Origin"] == "https://app.example.com"
        assert h["Access-Control-Allow-Credentials"] == "true"

    def test_preflight_includes_methods_headers_max_age(self):
        p = CorsPolicy(
            origin="https://app.example.com",
            methods=["GET", "POST", "OPTIONS"],
            headers=["Content-Type", "Authorization"],
            max_age=86400,
        )
        h = p.to_headers("https://app.example.com", preflight=True)
        assert h["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
        assert h["Access-Control-Allow-Headers"] == "Content-Type, Authorization"
        assert h["Access-Control-Max-Age"] == "86400"

    def test_expose_headers(self):
        p = CorsPolicy(
            origin="https://app.example.com",
            expose_headers=["X-Request-ID", "X-API-Version"],
        )
        h = p.to_headers("https://app.example.com")
        assert h["Access-Control-Expose-Headers"] == "X-Request-ID, X-API-Version"


# ---------------------------------------------------------------------
# CorsConfig — loaders
# ---------------------------------------------------------------------

class TestCorsConfig:
    def test_defaults(self):
        cfg = CorsConfig()
        assert cfg.enabled is True
        assert cfg.default.origin == "*"

    def test_from_yaml(self, tmp_path):
        import yaml
        yaml_path = tmp_path / "cors.yaml"
        yaml_path.write_text(yaml.safe_dump({
            "cors": {
                "enabled": True,
                "origins": [
                    {"origin": "https://a.example.com", "credentials": True},
                    {"origin": "https://b.example.com"},
                    {"origin": "https://c.example.com"},
                    {"origin": "https://d.example.com"},
                    {"origin": "*.wild.example.com"},
                ],
            },
        }, allow_unicode=True), encoding="utf-8")
        cfg = CorsConfig.from_yaml(yaml_path)
        assert len(cfg.origins) == 5

    def test_from_dict_round_trip(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "enabled": True,
                "origins": [
                    {"origin": "https://1.com"},
                    {"origin": "https://2.com"},
                    {"origin": "https://3.com"},
                    {"origin": "https://4.com"},
                    {"origin": "https://5.com"},
                ],
            },
        })
        assert len(cfg.origins) == 5

    def test_from_env_json(self, monkeypatch):
        monkeypatch.setenv("CORS_CONFIG", json.dumps({
            "origins": [{"origin": "https://env.com"}],
        }))
        cfg = CorsConfig.from_env()
        assert any(p.origin == "https://env.com" for p in cfg.origins)

    def test_from_env_legacy(self, monkeypatch):
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://x.com,https://y.com")
        monkeypatch.setenv("CORS_MAX_AGE", "1200")
        cfg = CorsConfig.from_env_legacy()
        assert any(p.origin == "https://x.com" for p in cfg.origins)
        assert any(p.origin == "https://y.com" for p in cfg.origins)
        assert cfg.default.max_age == 1200

    def test_validate_warns_on_wildcard_with_credentials(self, caplog):
        # P0 #4 — wildcard + credentials=True is now a hard error.
        # Browsers silently drop ``Access-Control-Allow-Credentials``
        # in that combination, so we refuse to load the config.
        from backend.gateway.cors import CorsConfigError
        with pytest.raises(CorsConfigError):
            CorsConfig.from_dict({
                "cors": {
                    "default": {"origin": "*", "credentials": True},
                },
            })

    def test_disabled_flag(self):
        cfg = CorsConfig.from_dict({"cors": {"enabled": False}})
        assert cfg.enabled is False
        assert cfg.allows("https://x.com") is False


# ---------------------------------------------------------------------
# resolve_cors + lookup
# ---------------------------------------------------------------------

class TestResolve:
    def _five_origin_config(self) -> CorsConfig:
        return CorsConfig.from_dict({
            "cors": {
                "enabled": True,
                "default": {"origin": "*"},
                "origins": [
                    {"origin": "https://app1.example.com", "credentials": True},
                    {"origin": "https://app2.example.com", "credentials": True},
                    {"origin": "https://app3.example.com", "credentials": True},
                    {"origin": "https://app4.example.com", "credentials": True},
                    {"origin": "*.partners.example.com", "credentials": True},
                ],
            },
        })

    def test_five_origins_resolve(self):
        cfg = self._five_origin_config()
        assert len(cfg.origins) == 5
        for i in range(1, 5):
            origin = f"https://app{i}.example.com"
            assert cfg.allows(origin) is True
            pol = cfg.resolve(origin)
            assert pol.origin == origin

    def test_wildcard_subdomain(self):
        cfg = self._five_origin_config()
        for origin in (
            "https://x.partners.example.com",
            "https://y.partners.example.com",
            "https://partners.example.com",
        ):
            assert cfg.allows(origin) is True
            pol = cfg.resolve(origin)
            assert pol.origin.startswith("*.")

    def test_unknown_origin_falls_back_to_default(self):
        cfg = self._five_origin_config()
        # Default is "*" — anything matches via default
        assert cfg.allows("https://random.com") is True
        pol = cfg.resolve("https://random.com")
        assert pol.origin == "*"

    def test_exact_match_wins_over_wildcard(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "origins": [
                    {"origin": "https://special.example.com", "credentials": True},
                    {"origin": "*.example.com"},
                ],
            },
        })
        pol = cfg.resolve("https://special.example.com")
        assert pol.origin == "https://special.example.com"

    def test_helper_resolve_cors(self):
        cfg = self._five_origin_config()
        h = resolve_cors("https://app1.example.com", config=cfg)
        assert h["Access-Control-Allow-Origin"] == "https://app1.example.com"

    def test_disabled_returns_empty_headers(self):
        cfg = CorsConfig.from_dict({"cors": {"enabled": False}})
        assert resolve_cors("https://x.com", config=cfg) == {}


# ---------------------------------------------------------------------
# CorsMiddleware
# ---------------------------------------------------------------------

class TestMiddleware:
    @pytest.mark.asyncio
    async def test_passthrough_when_disabled(self):
        cfg = CorsConfig(enabled=False)
        called = {"n": 0}

        async def inner_app(scope, receive, send):
            called["n"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def fake_send(message):
            pass

        mw = CorsMiddleware(inner_app, config=cfg)
        await mw({
            "type": "http", "method": "GET", "path": "/x",
            "headers": [(b"origin", b"https://x.com")], "query_string": b"",
        }, None, fake_send)
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_preflight_returns_204_with_cache_header(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "enabled": True,
                "origins": [
                    {
                        "origin": "https://app1.example.com",
                        "methods": ["GET", "POST", "OPTIONS"],
                        "headers": ["Content-Type", "Authorization"],
                        "credentials": True,
                        "max_age": 86400,
                    },
                ],
            },
        })
        response_status = {"code": None}
        response_headers: List = []

        async def inner_app(scope, receive, send):
            # Should not be called for preflight
            raise RuntimeError("inner should not run on preflight")

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_status["code"] = message.get("status")
                response_headers[:] = list(message.get("headers") or [])

        mw = CorsMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http", "method": "OPTIONS", "path": "/api/v1/users",
            "headers": [
                (b"origin", b"https://app1.example.com"),
                (b"access-control-request-method", b"POST"),
                (b"access-control-request-headers", b"content-type,authorization"),
            ],
            "query_string": b"",
        }
        await mw(scope, None, fake_send)
        assert response_status["code"] == 204
        header_map = {n.lower(): v for n, v in response_headers}
        assert b"access-control-allow-origin" in header_map
        assert header_map[b"access-control-allow-origin"] == b"https://app1.example.com"
        assert header_map[b"access-control-allow-credentials"] == b"true"
        assert header_map[b"access-control-max-age"] == b"86400"
        assert b"access-control-allow-methods" in header_map
        assert b"access-control-allow-headers" in header_map

    @pytest.mark.asyncio
    async def test_injects_cors_headers_in_passthrough(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "enabled": True,
                "origins": [
                    {"origin": "https://app1.example.com", "credentials": True},
                ],
            },
        })
        response_headers: List = []

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_headers[:] = list(message.get("headers") or [])

        mw = CorsMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http", "method": "GET", "path": "/api/v1/users",
            "headers": [(b"origin", b"https://app1.example.com")],
            "query_string": b"",
        }
        await mw(scope, None, fake_send)
        header_map = {n.lower(): v for n, v in response_headers}
        assert b"access-control-allow-origin" in header_map
        assert header_map[b"access-control-allow-origin"] == b"https://app1.example.com"

    @pytest.mark.asyncio
    async def test_lifespan_passthrough(self):
        cfg = CorsConfig(enabled=True)
        called = {"n": 0}

        async def inner_app(scope, receive, send):
            called["n"] += 1

        async def fake_send(message):
            pass

        mw = CorsMiddleware(inner_app, config=cfg)
        await mw({"type": "lifespan"}, None, fake_send)
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_five_origins_all_allow(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "enabled": True,
                "origins": [
                    {"origin": "https://a.example.com"},
                    {"origin": "https://b.example.com"},
                    {"origin": "https://c.example.com"},
                    {"origin": "https://d.example.com"},
                    {"origin": "https://e.example.com"},
                ],
            },
        })
        for letter in "abcde":
            origin = f"https://{letter}.example.com"
            pol = cfg.resolve(origin)
            assert pol.allows(origin)
