"""Tests for backend.gateway.api_version.

Coverage
========
1. ApiVersion parsing + comparison
2. VersionNegotiator resolves v1, v2 from URL / Accept / X-API-Version
3. Both /api/v1 and /api/v2 routes resolve independently
4. ApiVersionMiddleware injects X-API-Version response header
5. Deprecation headers (Deprecation / Sunset / Link) on v1
6. Config loading from dict / YAML / env
7. Unknown version falls back to default
8. ASGI smoke test through full middleware stack

Run::

    python -m pytest backend/gateway/tests/test_api_version.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.api_version import (  # noqa: E402
    ApiVersion,
    ApiVersionConfig,
    DeprecationPolicy,
    VersionNegotiator,
    ApiVersionMiddleware,
    negotiate,
    api_version_from_url,
)


# ---------------------------------------------------------------------
# ApiVersion parsing
# ---------------------------------------------------------------------

class TestApiVersion:
    def test_from_string_major_only(self):
        v = ApiVersion.from_string("v1")
        assert v.major == 1 and v.minor == 0
        assert v.to_string() == "v1"

    def test_from_string_with_minor(self):
        v = ApiVersion.from_string("v2.3")
        assert v.major == 2 and v.minor == 3
        assert v.to_string() == "v2.3"

    def test_from_string_case_insensitive(self):
        v = ApiVersion.from_string("V1")
        assert v.major == 1

    def test_from_string_strips_prefix(self):
        v = ApiVersion.from_string("1")
        assert v.to_string() == "v1"

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError):
            ApiVersion.from_string("not-a-version")

    def test_from_string_negative_rejected(self):
        with pytest.raises(ValueError):
            ApiVersion(-1, 0)

    def test_comparison(self):
        assert ApiVersion(1, 0) < ApiVersion(2, 0)
        assert ApiVersion(1, 5) < ApiVersion(2, 0)
        assert ApiVersion(2, 0) == ApiVersion(2, 0)

    def test_hashable(self):
        s = {ApiVersion(1, 0), ApiVersion(2, 0), ApiVersion(1, 0)}
        assert len(s) == 2


# ---------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------

class TestApiVersionConfig:
    def test_from_dict_defaults(self):
        cfg = ApiVersionConfig.from_dict({})
        assert cfg.supported_versions == ["v1", "v2"]
        assert cfg.default_version == "v1"

    def test_from_dict_custom(self):
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v3"],
                "default_version": "v3",
            },
        })
        assert cfg.supported_versions == ["v3"]

    def test_from_dict_invalid_default_raises(self):
        with pytest.raises(ValueError):
            cfg = ApiVersionConfig.from_dict({
                "api_version": {"supported_versions": ["v1"], "default_version": "v99"},
            })

    def test_from_env_json(self, monkeypatch):
        monkeypatch.setenv("API_VERSION_CONFIG", json.dumps({
            "api_version": {"supported_versions": ["v1", "v2", "v3"], "default_version": "v2"}
        }))
        cfg = ApiVersionConfig.from_env()
        assert cfg.default_version == "v2"

    def test_from_env_empty_returns_defaults(self, monkeypatch):
        monkeypatch.delenv("API_VERSION_CONFIG", raising=False)
        cfg = ApiVersionConfig.from_env()
        assert cfg.default_version == "v1"

    def test_from_yaml(self, tmp_path):
        import yaml
        yaml_path = tmp_path / "api_version.yaml"
        yaml_path.write_text(yaml.safe_dump({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v1",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-12-31",
                    "successor_version": "v2",
                    "docs_url": "https://docs.example.com/v1-deprecation",
                },
            },
        }, allow_unicode=True), encoding="utf-8")
        cfg = ApiVersionConfig.from_yaml(yaml_path)
        assert "v2" in cfg.supported_versions
        assert cfg.deprecation.sunset_date == "2026-12-31"
        assert cfg.deprecation.successor_version == "v2"


# ---------------------------------------------------------------------
# DeprecationPolicy
# ---------------------------------------------------------------------

class TestDeprecationPolicy:
    def test_is_deprecated(self):
        dep = DeprecationPolicy(deprecated_versions=["v1"], sunset_date="2026-12-31")
        assert dep.is_deprecated(ApiVersion.from_string("v1")) is True
        assert dep.is_deprecated(ApiVersion.from_string("v2")) is False

    def test_headers_basic(self):
        dep = DeprecationPolicy(deprecated_versions=["v1"], sunset_date="2026-12-31")
        h = dep.headers(ApiVersion.from_string("v1"))
        assert h["Deprecation"] == "true"
        assert "Sunset" in h
        assert "GMT" in h["Sunset"]

    def test_headers_with_successor(self):
        dep = DeprecationPolicy(deprecated_versions=["v1"], successor_version="v2")
        h = dep.headers(ApiVersion.from_string("v1"))
        assert h["Deprecation-Version"] == "v2"

    def test_headers_with_docs_link(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            successor_version="v2",
            docs_url="https://docs.example.com/v1-deprecation",
        )
        h = dep.headers(ApiVersion.from_string("v1"))
        assert "Link" in h
        assert "rel=\"deprecation\"" in h["Link"]

    def test_non_deprecated_no_headers(self):
        dep = DeprecationPolicy(deprecated_versions=["v1"], sunset_date="2026-12-31")
        h = dep.headers(ApiVersion.from_string("v2"))
        assert h == {}


# ---------------------------------------------------------------------
# VersionNegotiator
# ---------------------------------------------------------------------

class TestNegotiator:
    def _cfg(self) -> ApiVersionConfig:
        return ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v1",
                "deprecation": {"deprecated_versions": ["v1"]},
            },
        })

    def test_url_v1(self):
        n = VersionNegotiator(self._cfg())
        assert n.negotiate("/api/v1/auth/login") == ApiVersion.from_string("v1")

    def test_url_v2_independent(self):
        n = VersionNegotiator(self._cfg())
        assert n.negotiate("/api/v2/auth/login") == ApiVersion.from_string("v2")

    def test_url_v2_shadows_v1(self):
        """v2 prefix does NOT match v1 path."""
        n = VersionNegotiator(self._cfg())
        assert n.negotiate("/api/v2/users") == ApiVersion.from_string("v2")
        assert n.negotiate("/api/v1/users") == ApiVersion.from_string("v1")

    def test_accept_header(self):
        n = VersionNegotiator(self._cfg())
        v = n.negotiate("/foo", accept="application/vnd.imdf.v2+json")
        assert v == ApiVersion.from_string("v2")

    def test_x_api_version_header(self):
        n = VersionNegotiator(self._cfg())
        v = n.negotiate("/foo", x_version="v2")
        assert v == ApiVersion.from_string("v2")

    def test_unknown_version_falls_back(self):
        n = VersionNegotiator(self._cfg())
        # /foo has no /api/v* prefix, no Accept, no X-API-Version
        assert n.negotiate("/foo") == ApiVersion.from_string("v1")

    def test_precedence_url_over_accept(self):
        n = VersionNegotiator(self._cfg())
        # URL says v1, Accept says v2 → URL wins
        v = n.negotiate("/api/v1/users", accept="application/vnd.imdf.v2+json")
        assert v == ApiVersion.from_string("v1")

    def test_helper_negotiate(self):
        v = negotiate("/api/v2/anything")
        assert v == ApiVersion.from_string("v2")

    def test_helper_api_version_from_url(self):
        assert api_version_from_url("/api/v2/foo") == ApiVersion.from_string("v2")
        assert api_version_from_url("/nope") is None


# ---------------------------------------------------------------------
# ApiVersionMiddleware (ASGI)
# ---------------------------------------------------------------------

class TestMiddleware:
    @pytest.mark.asyncio
    async def test_injects_x_api_version_header(self):
        cfg = ApiVersionConfig()
        inner_called = {"n": 0}
        response_started = {"status": None, "headers": []}

        async def inner_app(scope, receive, send):
            inner_called["n"] += 1
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"ok":true}',
                "more_body": False,
            })

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_started["status"] = message.get("status")
                response_started["headers"] = list(message.get("headers") or [])

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users",
            "headers": [],
            "query_string": b"",
        }
        await mw(scope, None, fake_send)

        assert inner_called["n"] == 1
        # The middleware should have added x-api-version header
        header_names = {h[0].lower() for h in response_started["headers"]}
        assert b"x-api-version" in header_names
        version_val = next(
            v for n, v in response_started["headers"]
            if n.lower() == b"x-api-version"
        )
        assert version_val == b"v1"

    @pytest.mark.asyncio
    async def test_deprecation_headers_for_v1(self):
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v1",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-12-31",
                    "successor_version": "v2",
                },
            },
        })
        response_headers: list = []

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_headers[:] = list(message.get("headers") or [])

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users",
            "headers": [],
            "query_string": b"",
        }
        await mw(scope, None, fake_send)

        # Should carry Deprecation + Sunset headers
        header_names = {n.lower(): v for n, v in response_headers}
        assert b"deprecation" in header_names
        assert b"sunset" in header_names
        assert header_names[b"deprecation"] == b"true"

    @pytest.mark.asyncio
    async def test_passthrough_for_non_http(self):
        """Lifespan / websocket should pass through unchanged."""
        called = {"n": 0}

        async def inner_app(scope, receive, send):
            called["n"] += 1

        async def fake_send(message):
            pass

        cfg = ApiVersionConfig()
        mw = ApiVersionMiddleware(inner_app, config=cfg)
        await mw({"type": "lifespan"}, None, fake_send)
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_store_api_version_in_scope_state(self):
        cfg = ApiVersionConfig()
        state_seen = {}

        async def inner_app(scope, receive, send):
            state_seen.update(scope.get("state") or {})
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def fake_send(message):
            pass

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v2/users",
            "headers": [],
            "query_string": b"",
        }
        await mw(scope, None, fake_send)
        assert state_seen.get("api_version") == ApiVersion.from_string("v2")
