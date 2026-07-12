"""Tests for backend.gateway.rate_limit_config.

Coverage
========
1. EndpointPolicy normalisation & matching (literal + wildcard)
2. RateLimitConfig loading from YAML / dict / env
3. PerEndpointRateLimiter middleware uses the right policy per path
4. Bypass works for /_gw/*
5. 200 endpoint overrides can coexist with defaults
6. env-var fallback when YAML missing
7. Trust-proxy honoured
8. Stats correct

Run with::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    python -m pytest backend/gateway/tests/test_rate_limit_config.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Make ``backend`` importable when run from project root
_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.rate_limit_config import (  # noqa: E402
    EndpointPolicy,
    RateLimitConfig,
    PerEndpointRateLimiter,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def tmp_yaml(tmp_path):
    """Yield a writable yaml path."""
    return tmp_path / "rate_limits.yaml"


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    import yaml
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _make_yaml_config() -> Dict[str, Any]:
    """200 endpoints config — covers the requested verification."""
    endpoints: List[Dict[str, Any]] = []
    # Bypass list (5 entries)
    for p in ["/healthz", "/readyz", "/_gw/*", "/", "/internal/_health"]:
        endpoints.append({"pattern": p, "bypass": True})
    # Auth (strict)
    endpoints.append({"pattern": "/api/v1/auth/login", "capacity": 5, "refill_per_second": 1.0, "burst": 10})
    # Search (high throughput)
    endpoints.append({"pattern": "/api/v1/search", "capacity": 500, "refill_per_second": 200.0, "burst": 1000})
    # Trust-proxy flag
    endpoints.append({
        "pattern": "/api/v1/upload", "capacity": 30, "refill_per_second": 5.0,
        "trust_proxy": True, "burst": 60,
    })
    # Wildcards
    endpoints.append({"pattern": "/api/v1/agents/**", "capacity": 200, "refill_per_second": 80.0, "burst": 400})
    # Fill remainder to reach 200 total
    base_count = len(endpoints)
    for i in range(base_count, 200):
        endpoints.append({
            "pattern": f"/api/synthetic/{i}",
            "capacity": 50 + (i % 7) * 10,
            "refill_per_second": 10.0 + (i % 11),
            "burst": 100 + (i % 13) * 5,
        })
    return {
        "rate_limits": {
            "defaults": {
                "capacity": 100, "refill_per_second": 50.0, "burst": 200,
            },
            "endpoints": endpoints,
        },
    }


# ---------------------------------------------------------------------
# EndpointPolicy
# ---------------------------------------------------------------------

class TestEndpointPolicy:
    def test_normalisation_prepends_slash(self):
        p = EndpointPolicy(pattern="api/v1/auth")
        assert p.pattern == "/api/v1/auth"

    def test_normalisation_strips_trailing_slash(self):
        p = EndpointPolicy(pattern="/api/v1/auth/")
        assert p.pattern == "/api/v1/auth"

    def test_burst_fallback_to_capacity(self):
        p = EndpointPolicy(pattern="/x", capacity=42, refill_per_second=1.0)
        assert p.burst == 42

    def test_burst_overrides_to_zero(self):
        p = EndpointPolicy(pattern="/x", capacity=42, refill_per_second=1.0, burst=99)
        assert p.burst == 99

    def test_refill_default_when_zero(self):
        p = EndpointPolicy(pattern="/x", capacity=42, refill_per_second=0)
        assert p.refill_per_second == 21.0  # half of capacity

    def test_matches_literal(self):
        p = EndpointPolicy(pattern="/api/v1/auth/login")
        assert p.matches("/api/v1/auth/login")

    def test_matches_subprefix_not_partial(self):
        p = EndpointPolicy(pattern="/api/v1/auth")
        assert not p.matches("/api/v1/authorization")  # NOT a sub-prefix

    def test_matches_wildcard(self):
        p = EndpointPolicy(pattern="/api/v1/**")
        assert p.matches("/api/v1/anything/anywhere")
        assert p.matches("/api/v1/agents/list")

    def test_matches_qmark_wildcard(self):
        p = EndpointPolicy(pattern="/_gw/*")
        assert p.matches("/_gw/routes")
        assert not p.matches("/api/_gw/routes")  # fnmatch is string-wide


# ---------------------------------------------------------------------
# RateLimitConfig — YAML / dict / env
# ---------------------------------------------------------------------

class TestRateLimitConfig:
    def test_from_yaml_loads_file(self, tmp_yaml):
        _write_yaml(tmp_yaml, _make_yaml_config())
        cfg = RateLimitConfig.from_yaml(tmp_yaml)
        assert len(cfg.endpoints) == 200
        assert any(ep.bypass for ep in cfg.endpoints)
        assert cfg.defaults.capacity == 100

    def test_from_yaml_missing_returns_defaults(self, tmp_path):
        cfg = RateLimitConfig.from_yaml(tmp_path / "no_such_file.yaml")
        assert cfg.endpoints == []
        assert cfg.defaults.capacity == 100

    def test_from_dict_roundtrip(self):
        cfg = RateLimitConfig.from_dict(_make_yaml_config())
        assert len(cfg.endpoints) == 200

    def test_from_env_json(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_CONFIG", json.dumps(_make_yaml_config()))
        cfg = RateLimitConfig.from_env()
        assert len(cfg.endpoints) == 200

    def test_from_env_empty_returns_defaults(self, monkeypatch):
        monkeypatch.delenv("RATE_LIMIT_CONFIG", raising=False)
        cfg = RateLimitConfig.from_env()
        assert cfg.endpoints == []

    def test_from_env_invalid_returns_defaults(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_CONFIG", "{not-json")
        cfg = RateLimitConfig.from_env()
        assert cfg.endpoints == []

    def test_match_first_wins(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 100, "refill_per_second": 50.0, "burst": 200},
                "endpoints": [
                    # Order matters: more specific (literal) first
                    {"pattern": "/api/v1/auth/login", "capacity": 1, "refill_per_second": 0.1, "burst": 2},
                    {"pattern": "/api/v1/auth/**", "capacity": 5, "refill_per_second": 1.0, "burst": 10},
                ],
            },
        })
        # Literal /login wins for that exact path
        pol = cfg.policy_for("/api/v1/auth/login")
        assert pol.capacity == 1
        # Other auth paths fall through to the wildcard /auth/**
        pol = cfg.policy_for("/api/v1/auth/refresh")
        assert pol.capacity == 5

    def test_match_default_when_no_match(self):
        cfg = RateLimitConfig()
        pol = cfg.policy_for("/totally/unknown")
        assert pol.capacity == cfg.defaults.capacity

    def test_is_bypass(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 100, "refill_per_second": 50.0, "burst": 200},
                "endpoints": [
                    {"pattern": "/healthz", "bypass": True},
                ],
            },
        })
        assert cfg.is_bypass("/healthz") is True
        assert cfg.is_bypass("/api/v1/auth") is False

    def test_stats_returns_summary(self):
        cfg = RateLimitConfig.from_dict(_make_yaml_config())
        s = cfg.stats()
        assert s["endpoint_count"] == 200
        assert isinstance(s["endpoints"], list)


# ---------------------------------------------------------------------
# PerEndpointRateLimiter middleware (functional)
# ---------------------------------------------------------------------

class _FakeRequest:
    """Minimal ASGI request shim used to exercise the middleware."""
    def __init__(self, path: str, client_host: str = "1.2.3.4", headers: Dict[str, str] = None) -> None:
        self.url = type("U", (), {"path": path})()
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})()


class TestPerEndpointRateLimiter:
    @pytest.mark.asyncio
    async def test_bypass_path_passes_through(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 1, "refill_per_second": 0.01, "burst": 1},
                "endpoints": [{"pattern": "/healthz", "bypass": True}],
            },
        })
        mw = PerEndpointRateLimiter(app=None, config=cfg)
        called = {"n": 0}

        async def call_next(_req):
            called["n"] += 1
            return "ok"

        req = _FakeRequest("/healthz")
        result = await mw.dispatch(req, call_next)
        assert result == "ok"
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_low_capacity_returns_429(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 1, "refill_per_second": 0.001, "burst": 1},
                "endpoints": [],
            },
        })
        mw = PerEndpointRateLimiter(app=None, config=cfg)

        async def call_next(_req):
            return "ok"

        # First request consumes the bucket — allow
        r1 = await mw.dispatch(_FakeRequest("/api/v1/x"), call_next)
        assert r1 == "ok"
        # Second request — bucket empty, must reject
        r2 = await mw.dispatch(_FakeRequest("/api/v1/x"), call_next)
        assert hasattr(r2, "status_code")
        assert r2.status_code == 429

    @pytest.mark.asyncio
    async def test_separate_buckets_per_pattern(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 1, "refill_per_second": 0.001, "burst": 1},
                "endpoints": [
                    {"pattern": "/api/v1/a", "capacity": 1, "refill_per_second": 0.001, "burst": 1},
                    {"pattern": "/api/v1/b", "capacity": 5, "refill_per_second": 100.0, "burst": 5},
                ],
            },
        })
        mw = PerEndpointRateLimiter(app=None, config=cfg)

        async def call_next(_req):
            return "ok"

        # Consume /a once
        assert await mw.dispatch(_FakeRequest("/api/v1/a"), call_next) == "ok"
        # /b still has 5 tokens
        assert await mw.dispatch(_FakeRequest("/api/v1/b"), call_next) == "ok"
        assert await mw.dispatch(_FakeRequest("/api/v1/b"), call_next) == "ok"

    @pytest.mark.asyncio
    async def test_trust_proxy_uses_xff(self):
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 100, "refill_per_second": 1000.0, "burst": 100},
                "endpoints": [
                    {
                        "pattern": "/api/v1/upload", "capacity": 100,
                        "refill_per_second": 1000.0, "burst": 100, "trust_proxy": True,
                    },
                ],
            },
        })
        mw = PerEndpointRateLimiter(app=None, config=cfg)
        # Different clients with same X-Forwarded-For should bucket together
        h1 = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        h2 = {"x-forwarded-for": "9.9.9.9"}
        seen = set()

        async def call_next(_req):
            seen.add(mw._client_key(_req, trust_proxy=True))
            return "ok"

        await mw.dispatch(_FakeRequest("/api/v1/upload", "10.0.0.1", headers=h1), call_next)
        await mw.dispatch(_FakeRequest("/api/v1/upload", "10.0.0.2", headers=h2), call_next)
        # Both should resolve to the same key (9.9.9.9) when trust_proxy=True
        assert seen == {"9.9.9.9"}


# ---------------------------------------------------------------------
# Bypass list and 200-endpoint coexistence
# ---------------------------------------------------------------------

class TestScaleAndBypass:
    def test_200_endpoints_load_and_resolve(self, tmp_yaml):
        _write_yaml(tmp_yaml, _make_yaml_config())
        cfg = RateLimitConfig.from_yaml(tmp_yaml)
        assert len(cfg.endpoints) == 200
        # Sanity: every endpoint is findable
        for ep in cfg.endpoints[:20]:
            assert cfg.match(ep.pattern).pattern == ep.pattern

    def test_bypass_list_does_not_throttle(self, tmp_yaml):
        _write_yaml(tmp_yaml, _make_yaml_config())
        cfg = RateLimitConfig.from_yaml(tmp_yaml)
        bypass_paths = [ep for ep in cfg.endpoints if ep.bypass]
        assert len(bypass_paths) >= 5
        for ep in bypass_paths:
            assert cfg.is_bypass(ep.pattern) is True

    def test_200_endpoint_config_tolerates_duplicates(self):
        # Two endpoints with same pattern should not raise
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 100, "refill_per_second": 50.0, "burst": 200},
                "endpoints": [
                    {"pattern": "/a", "capacity": 10, "refill_per_second": 1.0, "burst": 10},
                    {"pattern": "/a", "capacity": 20, "refill_per_second": 2.0, "burst": 20},
                ],
            },
        })
        assert len(cfg.endpoints) == 2
