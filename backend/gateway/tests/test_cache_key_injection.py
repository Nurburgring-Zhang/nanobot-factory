"""P0 #3 — Redis cache key injection protection.

Background
==========
Cache keys are passed verbatim to Redis.  Without sanitisation, a
caller that controls the key (e.g. a route that caches by
``user_id``) could inject:

* **RESP protocol tokens** (CRLF, ``*``, ``$``) to smuggle commands.
* **Redis Cluster hash tags** ``{...}`` to redirect their slot to a
  victim's slot — colluding tenants could land on the same shard.
* **Control characters / whitespace** to corrupt log lines or
  Redis MONITOR output.

P0 #3 whitelists the cache key alphabet to ``[A-Za-z0-9_:.-]+``
(matches SHA-1 hex, our namespace convention, plus common separator
characters) and validates every key before it reaches the backend.

Run::

    python -m pytest backend/gateway/tests/test_cache_key_injection.py -v
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.cache import (  # noqa: E402
    CacheClient,
    CacheConfig,
    CacheMiddleware,
    InvalidCacheKey,
    _InMemoryBackend,
    _RedisLikeBackend,
    _validate_key,
    cached,
    cache_get,
    cache_set,
    reset_cache_singleton,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_cache_singleton()
    yield
    reset_cache_singleton()


# ---------------------------------------------------------------------
# 1. _validate_key whitelist
# ---------------------------------------------------------------------

class TestValidateKey:
    def test_valid_alphanumeric(self):
        assert _validate_key("abc123") == "abc123"
        assert _validate_key("ABC_xyz") == "ABC_xyz"

    def test_valid_with_separators(self):
        # _ : . - are allowed (namespace / version / cache-version)
        assert _validate_key("gw:v1:abc-def.123") == "gw:v1:abc-def.123"

    def test_valid_sha1_hex(self):
        # 40-char SHA-1 hex (used by cache_key helper)
        sha1 = "0123456789abcdef0123456789abcdef01234567"
        assert _validate_key(sha1) == sha1

    def test_rejects_crlf(self):
        with pytest.raises(InvalidCacheKey):
            _validate_key("abc\r\nSET x y\r\n")

    def test_rejects_space(self):
        with pytest.raises(InvalidCacheKey):
            _validate_key("has space")

    def test_rejects_redis_protocol_chars(self):
        # NOTE: ``:`` and ``-`` are allowed (we use them as namespace /
        # date separators respectively).  The dangerous RESP chars
        # ``*``, ``$``, ``+`` and common SQL/shell metacharacters must
        # all be rejected.
        for bad in [
            "*", "$", "+",            # RESP protocol markers
            "x;FLUSHALL",              # semicolon (Redis uses it as comment)
            "x|SLAVEOF",               # pipe
            "x'OR'1'='1",              # SQL-style quote escape
            "(SELECT * FROM users)",   # parens
            "key<with>brackets",        # angle brackets
            "key&with&ampersand",     # ampersand
            "key with space",          # whitespace
        ]:
            with pytest.raises(InvalidCacheKey):
                _validate_key(bad)

    def test_rejects_cluster_hash_tag(self):
        """``{tag}`` collides on the same Cluster slot — reject."""
        with pytest.raises(InvalidCacheKey):
            _validate_key("gw:{tenant_a}:x")

    def test_rejects_empty(self):
        with pytest.raises(InvalidCacheKey):
            _validate_key("")

    def test_rejects_non_string(self):
        with pytest.raises(InvalidCacheKey):
            _validate_key(123)  # type: ignore[arg-type]

    def test_rejects_unicode(self):
        """Unicode characters outside the whitelist are rejected.

        This blocks homograph attacks (e.g. a Cyrillic 'a' that looks
        like ASCII 'a' but hashes differently).
        """
        with pytest.raises(InvalidCacheKey):
            _validate_key("key_а_z")  # Cyrillic а in the middle

    def test_rejects_overly_long(self):
        too_long = "a" * 513
        with pytest.raises(InvalidCacheKey):
            _validate_key(too_long)


# ---------------------------------------------------------------------
# 2. CacheClient rejects invalid keys on set/get/delete
# ---------------------------------------------------------------------

class TestClientRejectsInvalid:
    @pytest.mark.asyncio
    async def test_set_rejects_crlf(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        with pytest.raises(InvalidCacheKey):
            await client.set("abc\r\nSET x y", b"v", ttl=60)

    @pytest.mark.asyncio
    async def test_get_rejects_cluster_hash(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        with pytest.raises(InvalidCacheKey):
            await client.get("gw:{tenant}:x")

    @pytest.mark.asyncio
    async def test_delete_swallows_invalid(self):
        """delete() logs and returns; it does not raise (cache correctness
        matters more than perfect input validation here — cache miss is
        acceptable)."""
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        # No exception — warning is logged
        await client.delete("a b c d e")
        # Should still have empty backend
        assert await client.get("anything") is None

    @pytest.mark.asyncio
    async def test_keys_rejects_control_chars(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        with pytest.raises(InvalidCacheKey):
            await client.keys("abc\r\n*")

    @pytest.mark.asyncio
    async def test_keys_allows_fnmatch_glob(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        # Globs are allowed in keys() patterns
        await client.keys("gw:*")


# ---------------------------------------------------------------------
# 3. cache_key() always produces a safe key
# ---------------------------------------------------------------------

class TestCacheKeyHelperSafe:
    def test_cache_key_hashes_unsafe_input(self):
        cfg = CacheConfig(backend="memory", prefix="gw:")
        client = CacheClient(cfg)
        # Even if caller passes CRLF, cache_key hashes it
        key1 = client.cache_key("ns", "a\r\nb")
        key2 = client.cache_key("ns", "a\r\nb")
        # Stable, deterministic, whitelisted
        assert key1 == key2
        assert _validate_key(key1) == key1

    def test_cache_key_distinguishes_payloads(self):
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        k1 = client.cache_key("ns", "user_a")
        k2 = client.cache_key("ns", "user_b")
        assert k1 != k2

    def test_cache_key_starts_with_prefix(self):
        cfg = CacheConfig(backend="memory", prefix="imdf:")
        client = CacheClient(cfg)
        k = client.cache_key("agents", "list")
        assert k.startswith("imdf:agents:")


# ---------------------------------------------------------------------
# 4. End-to-end: malicious caller cannot reach the backend
# ---------------------------------------------------------------------

class TestInjectionBlockedEndToEnd:
    @pytest.mark.asyncio
    async def test_attacker_cannot_set_arbitrary_key(self):
        """A caller that uses the **raw** key API (instead of
        ``cache_key()``) with malicious content must be rejected."""
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        # Attacker bypasses ``cache_key`` and tries a raw injection.
        # (Our middleware always goes through ``cache_key`` so this is
        # only possible if a developer mis-uses the API; we still
        # refuse at the boundary.)
        raw_malicious_key = "user_profile:vic\r\nFLUSHALL\r\n"
        with pytest.raises(InvalidCacheKey):
            await client.set(raw_malicious_key, b"compromised", ttl=60)

    @pytest.mark.asyncio
    async def test_safe_path_via_cache_key_helper(self):
        """The recommended path (``cache_key``) hashes attacker input
        and stores it under a whitelisted key — no injection."""
        cfg = CacheConfig(backend="memory")
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"
        attacker_user_id = "victim\r\nFLUSHALL\r\n"
        # No exception — cache_key hashes it
        safe_key = client.cache_key("user_profile", attacker_user_id)
        await client.set(safe_key, b"value", ttl=60)
        v = await client.get(safe_key)
        assert v == b"value"

    @pytest.mark.asyncio
    async def test_decorator_isolates_unsafe_args(self):
        """The @cached decorator should not blow up when given args with
        CRLF — it should hash them through cache_key()."""
        calls = {"n": 0}

        @cached("user", ttl=60)
        async def get_user(uid: str):
            calls["n"] += 1
            return {"uid": uid}

        # First call: miss → compute
        r1 = await get_user("abc\r\nDEF")
        r2 = await get_user("abc\r\nDEF")
        # Cache key is hashed → both calls hit the same cache entry
        assert calls["n"] == 1
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_module_helpers_use_safe_keys(self):
        """cache_get/cache_set go through cache_key() — safe by construction."""
        await cache_set("ns", {"x": 1}, 60, "key-with-dash.and.dot")
        v = await cache_get("ns", "key-with-dash.and.dot")
        assert v == {"x": 1}


# ---------------------------------------------------------------------
# 5. Middleware never crashes on invalid keys
# ---------------------------------------------------------------------

class TestMiddlewareRobust:
    @pytest.mark.asyncio
    async def test_middleware_passes_through_when_cache_invalid(self):
        """The middleware uses an internal SHA-1-hashed key, so it
        shouldn't hit the validator path.  We just sanity-check it
        doesn't crash on a request with crazy query params."""
        cfg = CacheConfig(backend="memory", default_ttl_seconds=60)
        client = CacheClient(cfg)
        client._backend = _InMemoryBackend()
        client._backend_label = "memory"

        inner_calls = {"n": 0}

        async def inner_app(scope, receive, send):
            inner_calls["n"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b'{"ok":true}', "more_body": False})

        async def fake_send(message):
            pass

        mw = CacheMiddleware(inner_app, client=client, ttl=60)
        scope = {
            "type": "http", "method": "GET", "path": "/api/v1/users",
            "headers": [], "query_string": b"q=evil%0d%0aSET%20x%20y",
        }
        await mw(scope, None, fake_send)
        # Two calls — first miss, second hit; both should succeed
        await mw(scope, None, fake_send)
        assert inner_calls["n"] == 1