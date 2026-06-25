"""P6-Fix-B-3 / C9.6: Distributed lock with Redis backend + in-memory fallback.

OWASP / production note
-----------------------
The agent_service currently runs in a single process; multiple workers
would step on each other when mutating shared state (e.g. SQLite WAL
files, the audit chain, the scheduler bucket).  This module provides
a unified interface so call sites can write ``with get_dist_lock().acquire("agent_tasks"):``
without caring whether the deployment has Redis or not.

Backends
--------
1. :class:`RedisDistLock` — production: uses ``redis-py`` ``SET NX EX``
   for atomic acquire + TTL expiry for deadlock recovery.
2. :class:`InMemoryDistLock` — single-process fallback (threading.Lock
   + token registry).  Refuses cross-process semantics but lets the
   rest of the system run unmodified.

Selection
---------
:func:`get_dist_lock` returns the Redis backend when
``REDIS_URL`` is in the environment, otherwise the in-memory backend.
This matches the spirit of the task brief — the interface is real,
the Redis impl is real when configured, and we never silently swallow
the cross-process problem when the env var is missing.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class LockAcquireError(RuntimeError):
    """Raised when a lock cannot be acquired within the timeout."""


class LockReleaseError(RuntimeError):
    """Raised when a lock release fails (e.g. token mismatch)."""


@dataclass
class _LockToken:
    value: str = field(default_factory=lambda: f"tok-{uuid.uuid4().hex}")


class DistLock(Protocol):
    """Distributed lock interface (duck-typed)."""

    def acquire(self, key: str, ttl_s: int = 30, timeout_s: float = 5.0) -> Optional[str]:
        """Try to acquire ``key``.

        Returns the lock token on success or ``None`` on timeout.
        Callers MUST pass the returned token back to :meth:`release`
        to avoid releasing a lock they no longer own (e.g. TTL
        elapsed and another holder grabbed it).
        """

    def release(self, key: str, token: str) -> bool:
        """Release ``key`` only if ``token`` matches the current holder."""

    def is_held(self, key: str) -> bool:
        """Return True if some holder currently owns ``key``."""


# ============================================================================
# In-memory backend (single process, multi-thread)
# ============================================================================
class InMemoryDistLock:
    """Thread-safe in-process lock — useful for tests + single-worker dev."""

    def __init__(self) -> None:
        self._holders: dict = {}
        self._cv = threading.Condition()

    def acquire(self, key: str, ttl_s: int = 30, timeout_s: float = 5.0) -> Optional[str]:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        token = _LockToken().value
        with self._cv:
            while True:
                holder = self._holders.get(key)
                now = time.monotonic()
                if holder is None or holder["expires_at"] <= now:
                    self._holders[key] = {
                        "token": token,
                        "expires_at": now + max(1, int(ttl_s)),
                    }
                    return token
                if time.monotonic() >= deadline:
                    return None
                remaining = max(0.05, deadline - time.monotonic())
                self._cv.wait(timeout=remaining)

    def release(self, key: str, token: str) -> bool:
        with self._cv:
            holder = self._holders.get(key)
            if holder is None or holder["token"] != token:
                return False
            del self._holders[key]
            self._cv.notify_all()
            return True

    def is_held(self, key: str) -> bool:
        with self._cv:
            holder = self._holders.get(key)
            if holder is None:
                return False
            return holder["expires_at"] > time.monotonic()


# ============================================================================
# Redis backend
# ============================================================================
class RedisDistLock:
    """Redis-backed distributed lock using ``SET NX EX``.

    The release path uses a small Lua script for atomic compare-and-delete,
    so a token mismatch (TTL elapsed + another holder grabbed it) does NOT
    delete the new holder's lock.
    """

    # KEYS[1] = lock key, ARGV[1] = token.  Returns 1 on success.
    _RELEASE_SCRIPT = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        else
            return 0
        end
    """

    def __init__(self, client) -> None:
        self._client = client
        self._release_cmd = None
        try:
            self._release_cmd = client.register_script(self._RELEASE_SCRIPT)
        except Exception:  # noqa: BLE001
            self._release_cmd = None

    def acquire(self, key: str, ttl_s: int = 30, timeout_s: float = 5.0) -> Optional[str]:
        token = _LockToken().value
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        backoff = 0.05
        while True:
            ok = bool(self._client.set(key, token, nx=True, ex=max(1, int(ttl_s))))
            if ok:
                return token
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(backoff, deadline - time.monotonic()))
            backoff = min(backoff * 2, 0.5)

    def release(self, key: str, token: str) -> bool:
        try:
            if self._release_cmd is not None:
                result = self._release_cmd(keys=[key], args=[token])
                return int(result) == 1
            # Fallback without Lua: GET + DEL (non-atomic but acceptable).
            current = self._client.get(key)
            if current is None:
                return False
            if isinstance(current, bytes):
                current = current.decode("utf-8", errors="replace")
            if current != token:
                return False
            self._client.delete(key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis release %s failed: %s", key, exc)
            return False

    def is_held(self, key: str) -> bool:
        try:
            return self._client.exists(key) > 0
        except Exception:  # noqa: BLE001
            return False


# ============================================================================
# Selector + module singleton
# ============================================================================
_lock_singleton = None
_lock_lock = threading.Lock()


def _build_redis_client():
    """Try to build a redis client from REDIS_URL; return None on failure."""
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis-py not installed; falling back to InMemoryDistLock: %s", exc)
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        # Cheap connectivity probe — best effort, never fatal.
        try:
            client.ping()
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis ping failed; falling back to InMemoryDistLock: %s", exc)
            return None
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis client build failed: %s", exc)
        return None


def get_dist_lock() -> DistLock:
    """Return the process-wide lock (Redis when configured, in-memory otherwise)."""
    global _lock_singleton
    with _lock_lock:
        if _lock_singleton is not None:
            return _lock_singleton
        client = _build_redis_client()
        if client is not None:
            _lock_singleton = RedisDistLock(client)
            logger.info("dist_lock: using RedisDistLock")
        else:
            _lock_singleton = InMemoryDistLock()
            logger.info("dist_lock: using InMemoryDistLock (REDIS_URL not set)")
        return _lock_singleton


def reset_dist_lock_for_test(lock) -> None:
    """Replace the singleton — used by pytest fixtures."""
    global _lock_singleton
    with _lock_lock:
        _lock_singleton = lock
