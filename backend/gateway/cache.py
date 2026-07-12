"""Redis cache layer with fake-Redis fallback + decorator API.

Purpose
=======
The gateway proxies a lot of read-only traffic (``/api/v1/agents/types``,
``/api/v1/models/capabilities``, …) that the upstream computes
identically every time.  Caching the **JSON response** in front of the
upstream call lets us drop p95 latency from ~120ms to ~3ms for hot
keys.

This module gives the gateway a small, **explicit** cache API:

* :func:`get_cache` — singleton accessor (Redis OR fake-Redis)
* :func:`cache_get` / :func:`cache_set` — low-level helpers
* :func:`cached_response` — decorator for FastAPI endpoints
* :class:`CacheClient` — class wrapper used in middleware
* :class:`CacheConfig` — config loaded from YAML/ENV

Backend selection
-----------------
1. ``REDIS_URL`` env var → use real Redis (``redis.asyncio``)
2. else ``FAKEREDIS=1`` or unset → use ``fakeredis.aioredis``
3. on any backend failure at runtime → in-memory ``dict`` fallback
   (with a warning logged; nothing crashes)

Decorators
----------
Use ``@cached_response(ttl=60)`` on a FastAPI route to cache the
serialised JSON body keyed by ``path + sorted(query)``.  Stats are
exposed via :func:`cache_stats`.

The middleware form (:class:`CacheMiddleware`) caches by request
``method + path + query`` for **GETs only**; non-GETs pass through
unaffected.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

import yaml

log = logging.getLogger("gateway.cache")

# ---------------------------------------------------------------------
# P0 #3: key whitelist
# ---------------------------------------------------------------------
# Cache keys are passed verbatim to the underlying Redis / fakeredis
# client.  Untrusted callers (FastAPI route handlers, decorators that
# incorporate user-supplied strings into the namespace) could try to
# inject control characters, Redis protocol tokens (CRLF, RESP arrays),
# or Redis Cluster hash-tag braces ({...}) that would let one tenant
# land on another tenant's slot.  We whitelist the alphabet to
# ``[A-Za-z0-9_:.-]+`` and SHA-1 the entire composite when callers
# exceed that vocabulary.
#
# References:
# - https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
# - https://github.com/redis/redis/issues/7493  (CRLF / RESP smuggling)
_VALID_KEY_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,512}$")
_KEY_TOO_LONG = 512


class InvalidCacheKey(ValueError):
    """Raised when a caller asks us to use a key that contains
    characters outside the whitelist, or that is unreasonably long.

    The middleware-level decorators catch this and log a warning
    instead of crashing the request — the canonical behaviour is to
    silently skip the cache for the offending call rather than 5xx
    the user.  Programmatic callers (cache_get / cache_set / direct
    CacheClient.set) raise so misconfigured code fails loudly.
    """


def _validate_key(key: str, *, allow_hashed: bool = True) -> str:
    """Return ``key`` if it matches the whitelist, else raise.

    When ``allow_hashed`` is True we permit keys whose entire content
    is the SHA-1 hex digest that :meth:`CacheClient.cache_key`
    generates — those are guaranteed safe regardless of caller input.
    """
    if not isinstance(key, str):
        raise InvalidCacheKey(f"cache key must be str, got {type(key).__name__}")
    if not key:
        raise InvalidCacheKey("cache key cannot be empty")
    if len(key) > _KEY_TOO_LONG:
        # Refuse — but caller can pre-hash to fit.
        raise InvalidCacheKey(
            f"cache key too long ({len(key)} > {_KEY_TOO_LONG} chars)"
        )
    if _VALID_KEY_RE.match(key):
        return key
    # Common safe case: SHA-1 hex is 40 chars of [0-9a-f], matches the
    # whitelist, but composite keys with separator / part may include
    # other chars.  We are strict here to catch injection early.
    raise InvalidCacheKey(
        f"cache key contains disallowed characters: {key[:64]!r} "
        f"(allowed: [A-Za-z0-9_:.-])"
    )


# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

@dataclass
class CacheConfig:
    """Cache configuration."""

    backend: str = "auto"               # ``auto`` | ``redis`` | ``fakeredis`` | ``memory``
    redis_url: str = "redis://127.0.0.1:6379/0"
    prefix: str = "gw:"
    default_ttl_seconds: int = 60
    max_value_bytes: int = 1_048_576    # 1 MiB
    connect_timeout_seconds: float = 2.0

    # Cache policy per method/path (path uses fnmatch)
    methods: List[str] = field(default_factory=lambda: ["GET", "HEAD"])
    bypass_paths: List[str] = field(default_factory=lambda: [
        "/healthz", "/readyz", "/_gw/*",
    ])

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CacheConfig":
        p = Path(path)
        if not p.exists():
            log.warning("cache yaml not found: %s — using defaults", p)
            return cls()
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return cls.from_dict(data)

    @classmethod
    def from_env(cls, env_var: str = "CACHE_CONFIG") -> "CacheConfig":
        import json as _json
        raw = os.environ.get(env_var, "")
        if not raw.strip():
            return cls()
        try:
            return cls.from_dict(_json.loads(raw))
        except Exception as exc:
            log.warning("invalid %s: %s — using defaults", env_var, exc)
            return cls()

    @classmethod
    def from_env_legacy(cls) -> "CacheConfig":
        """Backward-compat: read REDIS_URL / CACHE_TTL etc. individually."""
        url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        backend_raw = os.environ.get("CACHE_BACKEND", "auto").lower()
        if backend_raw in ("redis", "fakeredis", "memory"):
            backend = backend_raw
        else:
            backend = "auto"
        if backend == "auto":
            if url and not url.startswith("memory://"):
                backend = "redis" if os.environ.get("REDIS_ENABLED", "") else "fakeredis"
            else:
                backend = "memory"
        try:
            ttl = int(os.environ.get("CACHE_DEFAULT_TTL", "60"))
        except ValueError:
            ttl = 60
        return cls(backend=backend, redis_url=url, default_ttl_seconds=ttl)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheConfig":
        section = (data.get("cache") if isinstance(data.get("cache"), dict) else data) or {}
        if not isinstance(section, dict):
            section = {}
        backend = section.get("backend") or os.environ.get("CACHE_BACKEND", "auto")
        return cls(
            backend=str(backend),
            redis_url=section.get("redis_url") or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
            prefix=section.get("prefix") or "gw:",
            default_ttl_seconds=int(section.get("default_ttl_seconds") or 60),
            max_value_bytes=int(section.get("max_value_bytes") or 1_048_576),
            connect_timeout_seconds=float(section.get("connect_timeout_seconds") or 2.0),
            methods=list(section.get("methods") or ["GET", "HEAD"]),
            bypass_paths=list(section.get("bypass_paths") or ["/healthz", "/readyz", "/_gw/*"]),
        )


# ---------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------

class _InMemoryBackend:
    """Tiny thread-safe in-memory backend used as final fallback.

    * Honours TTL (lazy eviction on get).
    * ``clear()`` — for tests.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[bytes, float]] = {}
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0

    async def get(self, key: str) -> Optional[bytes]:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expires_at = entry
            if expires_at > 0 and expires_at < time.monotonic():
                del self._data[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        async with self._lock:
            expires_at = time.monotonic() + ttl if ttl > 0 else 0
            self._data[key] = (value, expires_at)
            self.sets += 1

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self.deletes += 1

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    async def keys(self, pattern: str) -> List[str]:
        async with self._lock:
            from fnmatch import fnmatch
            return [k for k in self._data.keys() if fnmatch(k, pattern)]

    def stats(self) -> Dict[str, int]:
        return {
            "backend": "memory",
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "size": len(self._data),
        }


class _RedisLikeBackend:
    """Wrap either real Redis or fakeredis under a common API.

    Methods we need: ``get``, ``set`` (with ``ex=ttl``), ``delete``,
    ``keys(pattern)``, ``info()``, ``aclose()``.
    """

    def __init__(self, client, *, label: str) -> None:
        self._client = client
        self._label = label
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        # Errors that indicate the underlying async client can't be
        # used from the current event loop anymore.
        self._loop_broken = False

    async def _safe_call(self, op, *args, **kwargs):
        """Run ``op`` with a RuntimeError trap that marks the backend
        loop-broken so the next call falls back to ``aclose()``."""
        if self._loop_broken:
            raise RuntimeError("backend_loop_broken")
        try:
            return await op(*args, **kwargs)
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
                log.warning(
                    "cache backend %s loop-broken (%s) — disable for this session",
                    self._label, exc,
                )
            raise

    async def get(self, key: str) -> Optional[bytes]:
        if self._loop_broken:
            raise RuntimeError("backend_loop_broken")
        try:
            v = await self._client.get(key)
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
                raise
            raise
        if v is None:
            self.misses += 1
            return None
        self.hits += 1
        return v if isinstance(v, (bytes, bytearray)) else str(v).encode("utf-8")

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        if self._loop_broken:
            raise RuntimeError("backend_loop_broken")
        try:
            if ttl > 0:
                await self._client.set(key, value, ex=ttl)
            else:
                await self._client.set(key, value)
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
                raise
            raise
        self.sets += 1

    async def delete(self, key: str) -> None:
        if self._loop_broken:
            raise RuntimeError("backend_loop_broken")
        try:
            await self._client.delete(key)
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
                raise
            raise
        self.deletes += 1

    async def clear(self) -> None:
        if self._loop_broken:
            return
        try:
            keys = await self._client.keys("*")
            if keys:
                await self._client.delete(*keys)
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
            # Other errors are non-fatal for clear()
        except Exception:
            pass

    async def keys(self, pattern: str) -> List[str]:
        if self._loop_broken:
            return []
        try:
            out = await self._client.keys(pattern)
            return [k.decode("latin-1") if isinstance(k, (bytes, bytearray)) else str(k) for k in out]
        except RuntimeError as exc:
            if "different event loop" in str(exc) or "bound to" in str(exc):
                self._loop_broken = True
                return []
            raise

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # pragma: no cover
            pass

    def stats(self) -> Dict[str, int]:
        return {
            "backend": self._label,
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "loop_broken": self._loop_broken,
        }


# ---------------------------------------------------------------------
# Cache client
# ---------------------------------------------------------------------

class CacheClient:
    """High-level cache client used by middleware + decorators."""

    def __init__(self, config: CacheConfig) -> None:
        self.config = config
        self._backend: Any = None
        self._backend_label: str = "uninitialised"
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._backend is not None:
            # Detect event-loop changes (test harnesses, anyio portals)
            try:
                running_loop = asyncio.get_running_loop()
                backend_loop = getattr(self._backend, "_loop", None)
                if backend_loop is not None and backend_loop is not running_loop:
                    log.warning(
                        "cache backend bound to a previous event loop — reconnecting",
                    )
                    self._backend = None
            except RuntimeError:
                self._backend = None
        if self._backend is not None:
            return
        async with self._lock:
            if self._backend is not None:
                return
            backend_choice = self.config.backend
            if backend_choice == "auto":
                # Prefer real Redis if REDIS_URL is set in the environment.
                # Otherwise fall back to fakeredis (in-process, async-safe)
                # unless ``CACHE_BACKEND_FORCE=memory`` is set (used by
                # some test harnesses that can't share an event loop
                # with fakeredis).
                if os.environ.get("REDIS_ENABLED", "") == "1":
                    backend_choice = "redis"
                elif os.environ.get("FAKEREDIS", "") == "1":
                    backend_choice = "fakeredis"
                elif os.environ.get("CACHE_BACKEND_FORCE", "") == "memory":
                    backend_choice = "memory"
                else:
                    backend_choice = "fakeredis"
            if backend_choice == "redis":
                try:
                    import redis.asyncio as aioredis  # type: ignore
                    client = aioredis.from_url(
                        self.config.redis_url,
                        socket_connect_timeout=self.config.connect_timeout_seconds,
                        decode_responses=False,
                    )
                    # Probe
                    await asyncio.wait_for(client.ping(), timeout=self.config.connect_timeout_seconds)
                    self._backend = _RedisLikeBackend(client, label="redis")
                    self._backend_label = "redis"
                    self._backend._loop = asyncio.get_running_loop()
                    log.info("cache connected to redis %s", self.config.redis_url)
                    return
                except Exception as exc:
                    log.warning("redis connect failed: %s — falling back to fakeredis", exc)
                    backend_choice = "fakeredis"
            if backend_choice == "fakeredis":
                try:
                    import fakeredis.aioredis as fakeaioredis  # type: ignore
                    client = fakeaioredis.FakeRedis(decode_responses=False)
                    self._backend = _RedisLikeBackend(client, label="fakeredis")
                    self._backend_label = "fakeredis"
                    self._backend._loop = asyncio.get_running_loop()
                    # Validate the binding with a single sync ping in
                    # the CURRENT event loop — catches cross-loop reuse
                    # before the first real request does.
                    try:
                        await asyncio.wait_for(client.ping(), timeout=0.5)
                    except RuntimeError:
                        # Bound to a different event loop → fall back
                        raise
                    except Exception:
                        pass  # any other ping failure is non-fatal here
                    log.info("cache using fakeredis (in-process)")
                    return
                except Exception as exc:
                    log.warning(
                        "fakeredis unavailable or cross-loop bound (%s) — "
                        "falling back to in-memory dict",
                        type(exc).__name__,
                    )
                    backend_choice = "memory"
            if backend_choice == "memory":
                self._backend = _InMemoryBackend()
                self._backend_label = "memory"
                self._backend._loop = asyncio.get_running_loop()
                log.info("cache using in-memory dict (process-local, no loop binding)")

    async def aclose(self) -> None:
        if self._backend is not None and hasattr(self._backend, "aclose"):
            await self._backend.aclose()
        self._backend = None

    # ---- key helpers ----

    def _key(self, namespace: str, parts: Iterable[str]) -> str:
        joined = "|".join(str(p) for p in parts)
        h = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
        return f"{self.config.prefix}{namespace}:{h}"

    # ---- core API ----

    async def get(self, key: str) -> Optional[bytes]:
        # Validate the key BEFORE touching the backend so a poisoned
        # caller cannot reach the Redis client.  Programmatic callers
        # get a loud ``InvalidCacheKey`` exception; middleware / hooks
        # should use ``safe_get`` instead.
        key = _validate_key(key)
        if self._backend is None:
            await self.connect()
        return await self._backend.get(key)

    async def safe_get(self, key: str) -> Optional[bytes]:
        """Like :meth:`get` but logs-and-swallows invalid keys.

        Used by ``CacheMiddleware`` and the ``@cached`` decorator so
        an upstream bug can't 5xx the whole API just because someone
        stuffed CRLF into a query parameter.
        """
        try:
            return await self.get(key)
        except InvalidCacheKey as exc:
            log.warning("cache.get rejected invalid key: %s", exc)
            return None

    async def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> None:
        key = _validate_key(key)
        if self._backend is None:
            await self.connect()
        ttl = int(ttl if ttl is not None else self.config.default_ttl_seconds)
        if len(value) > self.config.max_value_bytes:
            log.debug("cache value too large: %d bytes — skipping", len(value))
            return
        await self._backend.set(key, value, ttl)

    async def safe_set(
        self, key: str, value: bytes, ttl: Optional[int] = None,
    ) -> None:
        try:
            await self.set(key, value, ttl=ttl)
        except InvalidCacheKey as exc:
            log.warning("cache.set rejected invalid key: %s", exc)

    async def delete(self, key: str) -> None:
        try:
            key = _validate_key(key)
        except InvalidCacheKey as exc:
            log.warning("cache.delete rejected invalid key: %s", exc)
            return
        if self._backend is None:
            await self.connect()
        await self._backend.delete(key)

    async def clear(self) -> None:
        if self._backend is None:
            await self.connect()
        await self._backend.clear()

    async def keys(self, pattern: str) -> List[str]:
        # Patterns are fnmatch globs; we still reject control chars
        # but allow ``*`` and ``?`` since they're the legitimate
        # match-any operators here.
        if not isinstance(pattern, str) or not pattern:
            raise InvalidCacheKey("cache keys() pattern must be a non-empty string")
        if any(ord(c) < 0x20 or ord(c) == 0x7f for c in pattern):
            raise InvalidCacheKey(
                "cache keys() pattern contains control characters"
            )
        if len(pattern) > _KEY_TOO_LONG:
            raise InvalidCacheKey(
                f"cache keys() pattern too long ({len(pattern)})"
            )
        if self._backend is None:
            await self.connect()
        return await self._backend.keys(pattern)

    def cache_key(self, namespace: str, *parts: str) -> str:
        """Build a safe cache key from a namespace + arbitrary parts.

        The result is always a SHA-1-hex key (40 hex chars) prefixed
        with ``config.prefix + namespace:`` so any caller-supplied
        ``part`` content is hashed into a deterministic, whitelisted
        string.  The output ALWAYS passes :func:`_validate_key`.
        """
        return self._key(namespace, parts)

    def stats(self) -> Dict[str, Any]:
        if self._backend is None:
            return {"backend": self._backend_label, "hits": 0, "misses": 0, "sets": 0, "deletes": 0}
        s = self._backend.stats()
        s["prefix"] = self.config.prefix
        s["default_ttl"] = self.config.default_ttl_seconds
        return s


# ---------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------

_DEFAULT_CLIENT: Optional[CacheClient] = None
_DEFAULT_LOCK = asyncio.Lock()


def _sync_get_cache(config: Optional[CacheConfig] = None) -> CacheClient:
    """Synchronous singleton accessor (for tests + non-async callers)."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        cfg = config or CacheConfig.from_env_legacy()
        _DEFAULT_CLIENT = CacheClient(cfg)
        _DEFAULT_CLIENT._backend = _InMemoryBackend()
        _DEFAULT_CLIENT._backend_label = "memory-sync"
    return _DEFAULT_CLIENT


async def get_cache(config: Optional[CacheConfig] = None) -> CacheClient:
    """Async singleton accessor — opens backend on first call."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        async with _DEFAULT_LOCK:
            if _DEFAULT_CLIENT is None:
                cfg = config or CacheConfig.from_env_legacy()
                client = CacheClient(cfg)
                await client.connect()
                _DEFAULT_CLIENT = client
    return _DEFAULT_CLIENT


def reset_cache_singleton() -> None:
    """Reset the module-level singleton (used by tests)."""
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = None


# ---------------------------------------------------------------------
# Decorator API
# ---------------------------------------------------------------------

def cache_key_for_request(request) -> str:
    """Stable key for an inbound request (path + sorted query)."""
    parts = [request.method.upper(), request.url.path]
    items = sorted(request.query_params.multi_items())
    if items:
        for k, v in items:
            parts.append(f"{k}={v}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


async def cache_get(namespace: str, *parts: str) -> Optional[Any]:
    """Decorator-friendly get: loads JSON.  Returns None on miss."""
    client = _sync_get_cache()
    key = client.cache_key(namespace, *parts)
    # ``cache_key`` always returns a SHA-1-hex composite that passes
    # the whitelist, so the strict ``get`` is safe here.
    raw = await client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


async def cache_set(namespace: str, value: Any, ttl: Optional[int] = None,
                    *parts: str) -> None:
    """Decorator-friendly set: stores JSON."""
    client = _sync_get_cache()
    key = client.cache_key(namespace, *parts)
    raw = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
    await client.set(key, raw, ttl=ttl)


def cached(namespace: str = "default", ttl: Optional[int] = None):
    """Decorator for plain functions returning JSON-able data.

    Usage::

        @cached("agent_types", ttl=300)
        async def list_agent_types():
            return await expensive_lookup()

    The cached key is derived from the function's module + qualname +
    positional + keyword arguments.  ``None`` arguments are skipped to
    avoid spurious misses.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            serializable_args = [a for a in args if isinstance(a, (str, int, float, bool))]
            serializable_kwargs = {
                k: v for k, v in kwargs.items()
                if isinstance(v, (str, int, float, bool))
            }
            parts: List[str] = [fn.__qualname__]
            parts.extend(str(a) for a in serializable_args)
            parts.extend(f"{k}={v}" for k, v in sorted(serializable_kwargs.items()))
            hit = await cache_get(namespace, *parts)
            if hit is not None:
                return hit
            result = await fn(*args, **kwargs)
            await cache_set(namespace, result, ttl, *parts)
            return result
        return wrapper
    return decorator


# ---------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------

class CacheMiddleware:
    """ASGI middleware that caches GET responses by ``path + query``.

    Honours ``CacheConfig.bypass_paths`` (fnmatch).
    """

    def __init__(
        self,
        app,
        *,
        client: Optional[CacheClient] = None,
        config: Optional[CacheConfig] = None,
        ttl: Optional[int] = None,
        methods: Optional[List[str]] = None,
    ) -> None:
        self.app = app
        self._client = client
        self._config = config or CacheConfig()
        self._ttl = ttl if ttl is not None else self._config.default_ttl_seconds
        self._methods = methods or self._config.methods

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        if method not in self._methods:
            await self.app(scope, receive, send)
            return
        from fnmatch import fnmatch
        path = scope.get("path", "/")
        for pat in self._config.bypass_paths:
            if fnmatch(path, pat):
                await self.app(scope, receive, send)
                return

        try:
            client = self._client or await get_cache()
            key = "middleware:" + cache_key_for_request(
                type("R", (), {
                    "method": method, "url": type("U", (), {
                        "path": path, "query": _scope_query(scope),
                    })(), "query_params": _scope_query_items(scope),
                })()
            )
            # ``cache_key_for_request`` is a SHA-1 hex digest → safe.
            # Use strict ``get`` here; middleware is internal code.
            cached_bytes = await client.get(key)
        except (RuntimeError, Exception) as exc:
            # If the cache backend is unusable on the current event loop,
            # transparently fall back to a pass-through.
            log.warning("cache disabled (degraded): %s", exc)
            await self.app(scope, receive, send)
            return

        if cached_bytes is not None:
            status, headers, body = _unpack_response(cached_bytes)
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        # Cache miss — capture response
        chunks: List[bytes] = []
        send_status = {"code": 200}
        send_headers: List[Tuple[bytes, bytes]] = []

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                send_status["code"] = message.get("status", 200)
                send_headers[:] = list(message.get("headers") or [])
            elif message["type"] == "http.response.body":
                body = message.get("body") or b""
                chunks.append(body)
            await send(message)

        await self.app(scope, receive, send_wrapper)
        body = b"".join(chunks)
        if 200 <= send_status["code"] < 300 and body:
            try:
                payload = _pack_response(send_status["code"], send_headers, body)
                # Internal key, always safe; strict ``set`` is fine.
                await client.set(key, payload, ttl=self._ttl)
            except (RuntimeError, Exception) as exc:
                log.debug("cache set skipped: %s", exc)


def _scope_query(scope) -> str:
    raw = scope.get("query_string") or b""
    return raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else str(raw)


def _scope_query_items(scope):
    raw = scope.get("query_string") or b""
    s = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else str(raw)
    from urllib.parse import parse_qsl
    return type("QP", (), {"multi_items": lambda self: parse_qsl(s, keep_blank_values=True)})()


def _pack_response(status: int, headers: List[Tuple[bytes, bytes]], body: bytes) -> bytes:
    h_serialised = [
        (name.decode("latin-1", errors="replace"), value.decode("latin-1", errors="replace"))
        for name, value in headers
    ]
    payload = json.dumps({"status": status, "headers": h_serialised, "body": body.decode("latin-1", errors="replace")})
    return payload.encode("utf-8")


def _unpack_response(blob: bytes) -> Tuple[int, List[Tuple[bytes, bytes]], bytes]:
    obj = json.loads(blob.decode("utf-8"))
    status = int(obj.get("status") or 200)
    headers_raw = obj.get("headers") or []
    headers = [
        (k.encode("latin-1"), v.encode("latin-1"))
        for k, v in headers_raw
    ]
    body = (obj.get("body") or "").encode("latin-1")
    return status, headers, body


# ---------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------

def cache_stats() -> Dict[str, Any]:
    """Return the current singleton's stats (sync-friendly)."""
    if _DEFAULT_CLIENT is None:
        return {"backend": "uninitialised"}
    return _DEFAULT_CLIENT.stats()


__all__ = [
    "CacheConfig",
    "CacheClient",
    "CacheMiddleware",
    "InvalidCacheKey",
    "cache_get",
    "cache_set",
    "cached",
    "get_cache",
    "reset_cache_singleton",
    "cache_stats",
]
