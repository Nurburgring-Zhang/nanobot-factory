"""VDP-2026 R9 — Performance / Cache / Pool / Async.

Adds four performance primitives used across the platform:

  - ``TTLCache`` — in-memory + thread-safe TTL cache with size cap;
    identical (``method+url+params``) responses are served in O(1).
  - ``Pool``     — bounded object pool (DB connections / heavy clients).
  - ``Batch``    — coalesces a stream of small jobs into batched execution
    (useful for score.run / bulk annotation submit).
  - ``AsyncQueue`` — minimal in-process async queue with priority.

None of these require external infrastructure (no Redis / no Celery); the
implementation is intentionally tiny so the platform stays runnable on a
single bare-metal node during R7 deployment validation.
"""
from __future__ import annotations

import heapq
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

logger = __import__("logging").getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# TTL cache — thread-safe, size-bounded LRU with per-entry expiry
# ---------------------------------------------------------------------------


class TTLCache(Generic[T]):
    def __init__(self, max_size: int = 256, default_ttl_seconds: int = 60) -> None:
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self._store: "OrderedDict[str, Tuple[float, T]]" = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if expires_at <= time.time():
                self._store.pop(key, None)
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: T, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = time.time() + ttl
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            # evict LRU entries until size <= max
            while len(self._store) > self.max_size:
                self._store.popitem(last=False) if hasattr(self._store, "popitem") else self._store.pop(next(iter(self._store)))

    def invalidate(self, prefix: Optional[str] = None) -> int:
        with self._lock:
            if prefix is None:
                n = len(self._store)
                self._store.clear()
                return n
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._store),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": (
                    self.hits / (self.hits + self.misses)
                    if (self.hits + self.misses) > 0 else 0.0
                ),
            }


# ---------------------------------------------------------------------------
# Object pool
# ---------------------------------------------------------------------------


class Pool(Generic[T]):
    """Bounded pool of objects; callers can acquire / release items.

    Designed for DB connections / heavy clients. Acquire blocks (up to
    timeout) if the pool is at capacity.
    """

    def __init__(self, factory: Callable[[], T], max_size: int = 16,
                 acquire_timeout: float = 5.0) -> None:
        self._factory = factory
        self._max_size = max_size
        self._acquire_timeout = acquire_timeout
        self._pool: List[T] = []
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._created = 0
        self._in_use = 0
        self._waits = 0

    def acquire(self) -> T:
        with self._cond:
            self._waits += 1
            deadline = time.time() + self._acquire_timeout
            while True:
                if self._pool:
                    obj = self._pool.pop()
                    self._in_use += 1
                    self._waits -= 1
                    return obj
                if self._created < self._max_size:
                    obj = self._factory()
                    self._created += 1
                    self._in_use += 1
                    self._waits -= 1
                    return obj
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._waits -= 1
                    raise TimeoutError("pool acquire timeout")
                self._cond.wait(timeout=remaining)

    def release(self, obj: T) -> None:
        with self._cond:
            self._in_use -= 1
            if self._in_use < 0:
                self._in_use = 0
            self._pool.append(obj)
            self._cond.notify()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "created": self._created,
                "max_size": self._max_size,
                "available": len(self._pool),
                "in_use": self._in_use,
                "waits_total": self._waits,
            }


# ---------------------------------------------------------------------------
# Coalesced batch
# ---------------------------------------------------------------------------


class Batch:
    """Coalesce repeated small jobs into batched execution.

    Use::

        b = Batch(max_batch=32, max_wait_ms=50)
        for item in items:
            b.add(processor, (item,))
        b.flush()

    Or run in flush() mode by calling batch.close() at end.
    """

    def __init__(self, max_batch: int = 32, max_wait_ms: int = 50) -> None:
        self.max_batch = max_batch
        self.max_wait = max_wait_ms / 1000.0
        self._jobs: List[Tuple[Callable, tuple, dict]] = []
        self._lock = threading.RLock()
        self.batches_executed = 0
        self.jobs_executed = 0
        self.jobs_errors = 0

    def add(self, fn: Callable, args: tuple = (), kwargs: Optional[dict] = None) -> None:
        kwargs = kwargs or {}
        with self._lock:
            self._jobs.append((fn, args, kwargs))
            if len(self._jobs) >= self.max_batch:
                self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._jobs:
            return
        batch = self._jobs[:]
        self._jobs.clear()
        self.batches_executed += 1
        # run inline but in a thread-safe manner
        results: List[Any] = []
        for fn, args, kwargs in batch:
            try:
                results.append(fn(*args, **kwargs))
                self.jobs_executed += 1
            except Exception as e:  # noqa: BLE001
                self.jobs_errors += 1
                logger.warning("Batch job failed: %s", e)

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "batches_executed": self.batches_executed,
                "jobs_executed": self.jobs_executed,
                "jobs_errors": self.jobs_errors,
                "error_rate": (
                    self.jobs_errors / self.jobs_executed
                    if self.jobs_executed > 0 else 0.0
                ),
                "pending": len(self._jobs),
            }


# ---------------------------------------------------------------------------
# Priority async queue
# ---------------------------------------------------------------------------


@dataclass(order=True)
class _PQEntry:
    priority: float
    seq: int
    payload: Any = field(compare=False)


class AsyncQueue:
    def __init__(self, max_size: int = 0) -> None:
        self.max_size = max_size
        self._heap: List[_PQEntry] = []
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._seq = 0
        self.enqueued = 0
        self.dequeued = 0

    def push(self, payload: Any, priority: float = 1.0) -> None:
        with self._cond:
            if self.max_size > 0:
                while len(self._heap) >= self.max_size:
                    self._cond.wait(timeout=0.05)
            self._seq += 1
            heapq.heappush(self._heap, _PQEntry(priority, self._seq, payload))
            self.enqueued += 1
            self._cond.notify()

    def pop(self, timeout: Optional[float] = None) -> Any:
        # `if timeout` would treat 0.0 as "block forever" — guard against
        # the falsy-zero bug by checking against None.
        deadline = time.time() + timeout if timeout is not None else None
        with self._cond:
            while not self._heap:
                if deadline is None:
                    self._cond.wait()
                else:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    self._cond.wait(timeout=remaining)
            entry = heapq.heappop(self._heap)
            self.dequeued += 1
            return entry.payload

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._heap),
                "max_size": self.max_size,
                "enqueued": self.enqueued,
                "dequeued": self.dequeued,
            }


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_cache: Optional[TTLCache] = None
_pool: Optional[Pool] = None
_batch: Optional[Batch] = None
_queue: Optional[AsyncQueue] = None


def get_cache(max_size: int = 256, ttl: int = 60) -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache(max_size=max_size, default_ttl_seconds=ttl)
    return _cache


def get_pool(max_size: int = 16) -> Pool:
    global _pool
    if _pool is None:
        # generic factory — substitute with real DB engine for prod
        _pool = Pool(factory=dict, max_size=max_size)
    return _pool


def get_batch() -> Batch:
    global _batch
    if _batch is None:
        _batch = Batch()
    return _batch


def get_queue(max_size: int = 0) -> AsyncQueue:
    global _queue
    if _queue is None:
        _queue = AsyncQueue(max_size=max_size)
    return _queue


def reset_for_test() -> None:
    global _cache, _pool, _batch, _queue
    _cache = _pool = _batch = _queue = None


def configure_db(path) -> None:  # noqa: ANN001
    """No-op DB configuration — perf primitives are pure in-memory.

    Provided so that R10 / parallel test fixtures can configure every module
    uniformly (e.g. ``from perf_r9 import configure_db as perf_db``) without
    having to special-case R9.
    """
    return None
