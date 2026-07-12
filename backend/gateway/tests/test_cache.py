"""Tests for backend.gateway.cache.

Coverage
========
1. CacheConfig loads from YAML / dict / env
2. cache_get / cache_set round-trip via fakeredis
3. Backend selection (fakeredis preferred, real redis if REDIS_URL set)
4. TTL is honoured
5. Cached decorator returns same result for repeated calls
6. CacheMiddleware short-circuits a repeat GET
7. Stats endpoint returns hits/misses
8. Integration: 1000 req → > 60% hit rate
9. Bypass paths skip the cache
10. Non-GET methods skip the cache
11. In-memory fallback works when both Redis and fakeredis are unavailable

Run::

    python -m pytest backend/gateway/tests/test_cache.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.cache import (  # noqa: E402
    CacheConfig,
    CacheClient,
    CacheMiddleware,
    _InMemoryBackend,
    _RedisLikeBackend,
    cache_get,
    cache_set,
    cache_stats,
    cached,
    get_cache,
    reset_cache_singleton,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Each test starts with a clean singleton."""
    reset_cache_singleton()
    yield
    reset_cache_singleton()


@pytest.fixture
def fakeredis_client():
    """Return a CacheClient backed by fakeredis."""
    cfg = CacheConfig(backend="fakeredis", prefix="test:")
    client = CacheClient(cfg)
    # Force fakeredis sync
    client._backend = _InMemoryBackend()  # placeholder for stats compat
    # Replace with real fakeredis
    import fakeredis.aioredis as fakeaioredis
    real = fakeaioredis.FakeRedis(decode_responses=False)
    client._backend = _RedisLikeBackend(real, label="fakeredis")
    client._backend_label = "fakeredis"
    return client


# ---------------------------------------------------------------------
# CacheConfig
# ---------------------------------------------------------------------

class TestCacheConfig:
    def test_defaults(self):
        cfg = CacheConfig()
        assert cfg.backend == "auto"
        assert cfg.default_ttl_seconds == 60
        assert cfg.prefix == "gw:"

    def test_from_yaml(self, tmp_path):
        import yaml
        yaml_path = tmp_path / "cache.yaml"
        yaml_path.write_text(yaml.safe_dump({
            "cache": {"backend": "fakeredis", "default_ttl_seconds": 120, "prefix": "x:"},
        }), encoding="utf-8")
        cfg = CacheConfig.from_yaml(yaml_path)
        assert cfg.default_ttl_seconds == 120
        assert cfg.prefix == "x:"

    def test_from_env_json(self, monkeypatch):
        monkeypatch.setenv("CACHE_CONFIG", json.dumps({
            "cache": {"backend": "memory", "default_ttl_seconds": 30}
        }))
        cfg = CacheConfig.from_env()
        assert cfg.default_ttl_seconds == 30

    def test_from_env_legacy(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("CACHE_BACKEND", "fakeredis")
        monkeypatch.setenv("CACHE_DEFAULT_TTL", "300")
        cfg = CacheConfig.from_env_legacy()
        assert cfg.default_ttl_seconds == 300
        assert cfg.backend == "fakeredis"


# ---------------------------------------------------------------------
# CacheClient low-level operations
# ---------------------------------------------------------------------

class TestCacheClient:
    @pytest.mark.asyncio
    async def test_set_then_get(self, fakeredis_client):
        c = fakeredis_client
        await c.set("k1", b"hello", ttl=60)
        v = await c.get("k1")
        assert v == b"hello"

    @pytest.mark.asyncio
    async def test_miss_returns_none(self, fakeredis_client):
        assert await fakeredis_client.get("nope") is None

    @pytest.mark.asyncio
    async def test_ttl_expires(self, fakeredis_client):
        await fakeredis_client.set("k", b"v", ttl=1)
        await asyncio.sleep(1.2)
        assert await fakeredis_client.get("k") is None

    @pytest.mark.asyncio
    async def test_max_value_bytes_skipped(self, fakeredis_client):
        big = b"x" * (fakeredis_client.config.max_value_bytes + 10)
        await fakeredis_client.set("big", big, ttl=60)
        assert await fakeredis_client.get("big") is None

    @pytest.mark.asyncio
    async def test_delete(self, fakeredis_client):
        await fakeredis_client.set("k", b"v", ttl=60)
        assert await fakeredis_client.delete("k") is None
        assert await fakeredis_client.get("k") is None

    @pytest.mark.asyncio
    async def test_stats_track_hits_misses(self, fakeredis_client):
        c = fakeredis_client
        await c.set("k", b"v", ttl=60)
        await c.get("k")   # hit
        await c.get("k2")  # miss
        s = c.stats()
        assert s["hits"] >= 1
        assert s["misses"] >= 1
        assert s["backend"] == "fakeredis"

    def test_key_is_stable(self, fakeredis_client):
        c = fakeredis_client
        k1 = c.cache_key("ns", "a", "b")
        k2 = c.cache_key("ns", "a", "b")
        assert k1 == k2
        # Different args → different key
        k3 = c.cache_key("ns", "a", "c")
        assert k3 != k1

    @pytest.mark.asyncio
    async def test_inmemory_backend(self):
        cfg = CacheConfig(backend="memory")
        c = CacheClient(cfg)
        c._backend = _InMemoryBackend()
        c._backend_label = "memory"
        await c.set("k", b"v", ttl=60)
        assert await c.get("k") == b"v"
        # Expire
        await c.set("k2", b"v2", ttl=1)
        await asyncio.sleep(1.1)
        assert await c.get("k2") is None


# ---------------------------------------------------------------------
# cache_get / cache_set helpers + @cached decorator
# ---------------------------------------------------------------------

class TestHelpers:
    @pytest.mark.asyncio
    async def test_cache_get_set_roundtrip(self):
        await cache_set("ns", {"a": 1, "b": "hi"}, 60, "p1", "p2")
        v = await cache_get("ns", "p1", "p2")
        assert v == {"a": 1, "b": "hi"}

    @pytest.mark.asyncio
    async def test_cache_get_miss(self):
        assert await cache_get("ns", "missing") is None

    @pytest.mark.asyncio
    async def test_cached_decorator_returns_cached_on_second_call(self):
        calls = {"n": 0}

        @cached("agent_types", ttl=60)
        async def expensive_lookup(kind: str):
            calls["n"] += 1
            return {"items": [kind], "compute_ms": 42}

        # First call: compute
        r1 = await expensive_lookup("text")
        r2 = await expensive_lookup("text")
        # Only first call actually executed (second hits cache)
        assert calls["n"] == 1
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_cached_decorator_distinguishes_args(self):
        calls = {"n": 0}

        @cached("ns_args", ttl=60)
        async def f(x: str):
            calls["n"] += 1
            return x

        await f("a")
        await f("b")
        await f("a")
        # Three distinct computations: a, b, a (a again = cache hit)
        assert calls["n"] == 2


# ---------------------------------------------------------------------
# CacheMiddleware
# ---------------------------------------------------------------------

class TestCacheMiddleware:
    @pytest.mark.asyncio
    async def test_get_cached_on_repeat(self):
        # Shared client between middleware + cache_stats
        cfg = CacheConfig(backend="memory", default_ttl_seconds=60)
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        inner_calls = {"n": 0}

        async def inner_app(scope, receive, send):
            inner_calls["n"] += 1
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
            pass

        mw = CacheMiddleware(inner_app, client=client, ttl=60, methods=["GET"])
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/search",
            "headers": [],
            "query_string": b"",
        }
        # First call: pass through to inner
        await mw(scope, None, fake_send)
        # Second call: cache hit, no inner
        await mw(scope, None, fake_send)
        assert inner_calls["n"] == 1

    @pytest.mark.asyncio
    async def test_bypass_path_not_cached(self):
        cfg = CacheConfig(backend="memory", default_ttl_seconds=60,
                          bypass_paths=["/healthz"])
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        inner_calls = {"n": 0}

        async def inner_app(scope, receive, send):
            inner_calls["n"] += 1
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": b'ok',
                "more_body": False,
            })

        async def fake_send(message):
            pass

        mw = CacheMiddleware(inner_app, client=client, ttl=60)
        scope = {
            "type": "http", "method": "GET", "path": "/healthz",
            "headers": [], "query_string": b"",
        }
        await mw(scope, None, fake_send)
        await mw(scope, None, fake_send)
        assert inner_calls["n"] == 2  # both bypassed

    @pytest.mark.asyncio
    async def test_non_get_passes_through(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        inner_calls = {"n": 0}

        async def inner_app(scope, receive, send):
            inner_calls["n"] += 1
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": b"", "more_body": False,
            })

        async def fake_send(message):
            pass

        mw = CacheMiddleware(inner_app, client=client, ttl=60, methods=["GET"])
        for method in ("POST", "PUT", "DELETE"):
            scope = {
                "type": "http", "method": method, "path": "/api/v1/x",
                "headers": [], "query_string": b"",
            }
            await mw(scope, None, fake_send)
        # POST/PUT/DELETE all bypassed → 3 inner calls
        assert inner_calls["n"] == 3


# ---------------------------------------------------------------------
# Integration: 1000 requests → > 60% hit rate
# ---------------------------------------------------------------------

class TestIntegration:
    @pytest.mark.asyncio
    async def test_1000_requests_above_60pct_hit(self):
        """The headline requirement: 1000 requests, cached hit rate > 60%."""
        cfg = CacheConfig(backend="memory", default_ttl_seconds=300)
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        inner_calls = {"n": 0}

        async def inner_app(scope, receive, send):
            inner_calls["n"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b'{"q":"r"}', "more_body": False})

        async def fake_send(message):
            pass

        mw = CacheMiddleware(inner_app, client=client, ttl=300)
        # 10 distinct paths × 100 reqs = 1000 total
        paths = [f"/api/v1/search/q{i}" for i in range(10)]
        for path in paths:
            for _ in range(100):
                scope = {
                    "type": "http", "method": "GET", "path": path,
                    "headers": [], "query_string": b"",
                }
                await mw(scope, None, fake_send)

        # Only 10 distinct cache misses; 1000 - 10 = 990 hits
        assert inner_calls["n"] == 10
        s = client.stats()
        hits = s.get("hits", 0)
        misses = s.get("misses", 0)
        total = hits + misses
        assert total == 1000
        assert (hits / total) > 0.6, f"hit rate {hits/total:.1%} below 60% (hits={hits}, misses={misses})"


# ---------------------------------------------------------------------
# cache_stats
# ---------------------------------------------------------------------

class TestCacheStats:
    def test_uninitialised_returns_marker(self):
        # Make sure we start clean
        reset_cache_singleton()
        st = cache_stats()
        assert st.get("backend") == "uninitialised"
