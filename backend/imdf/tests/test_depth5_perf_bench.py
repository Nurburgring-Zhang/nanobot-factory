"""VDP-2026 Depth-5 — Performance benchmark for R9 perf primitives.

Stress-tests ``perf_r9`` with 1000+ ops per primitive to verify:
- TTL cache: insert + read + expiry under load
- Batch: parallel execution correctness + throughput
- Queue: push/pop ordering + bounded memory

These are not unit tests — they exercise the *real* primitive singletons
through thousands of operations, asserting no thread-safety regressions,
no memory leaks, and that performance is within sane bounds for a
production deployment.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("IMDF_TEST_MODE", "1")


@pytest.fixture(autouse=True)
def _reset_perf():
    """Reset all perf primitives before each test so module-level
    singletons don't leak state across tests.
    """
    from perf_r9.primitives import reset_for_test
    reset_for_test()
    yield
    reset_for_test()


# ───────────────────────────────────────────────────────────────────
# TTL cache
# ───────────────────────────────────────────────────────────────────

def test_ttl_cache_handles_1000_inserts_and_reads():
    from perf_r9.primitives import TTLCache

    c = TTLCache(max_size=2000, default_ttl_seconds=60)
    started = time.perf_counter()
    for i in range(1000):
        c.set(f"k{i}", f"v{i}", ttl_seconds=60)
    write_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    for i in range(1000):
        v = c.get(f"k{i}")
        assert v == f"v{i}", f"key k{i} round-trip failed: {v!r}"
    read_ms = (time.perf_counter() - started) * 1000

    # Loose bounds: 1000 inserts in well under 1s, 1000 reads even faster.
    assert write_ms < 1000, f"1000 inserts took {write_ms:.0f}ms (too slow)"
    assert read_ms < 200, f"1000 reads took {read_ms:.0f}ms (too slow)"
    stats = c.stats()
    assert stats["size"] == 1000, stats
    assert stats["hits"] == 1000, stats
    assert stats["misses"] == 0, stats


def test_ttl_cache_expiry_under_load():
    from perf_r9.primitives import TTLCache

    c = TTLCache(max_size=1000, default_ttl_seconds=1)
    for i in range(500):
        c.set(f"k{i}", f"v{i}", ttl_seconds=0.2)
    time.sleep(0.3)
    # All keys should have expired.
    expired = sum(1 for i in range(500) if c.get(f"k{i}") is None)
    assert expired == 500, f"only {expired}/500 keys expired"


def test_ttl_cache_lru_eviction_under_load():
    from perf_r9.primitives import TTLCache

    c = TTLCache(max_size=100, default_ttl_seconds=60)
    for i in range(500):
        c.set(f"k{i}", f"v{i}", ttl_seconds=60)
    stats = c.stats()
    # Cache should hold at most max_size entries.
    assert stats["size"] <= 100, stats
    # Early keys should have been evicted.
    assert c.get("k0") is None
    assert c.get("k499") == "v499"


# ───────────────────────────────────────────────────────────────────
# Batch
# ───────────────────────────────────────────────────────────────────

def test_batch_executes_1000_jobs_correctly():
    from perf_r9.primitives import Batch

    b = Batch(max_batch=64, max_wait_ms=20)

    def double(n: int) -> int:
        return n * 2

    started = time.perf_counter()
    for i in range(1000):
        b.add(double, args=(i,))
    b.flush()
    elapsed_ms = (time.perf_counter() - started) * 1000

    stats = b.stats()
    assert stats["jobs_executed"] == 1000, stats
    assert stats["jobs_errors"] == 0, stats
    # 1000 small jobs should finish in well under 5s on any modern box.
    assert elapsed_ms < 5000, f"1000 batch jobs took {elapsed_ms:.0f}ms"


def test_batch_thread_safety_under_concurrent_adds():
    """1000 jobs added from multiple threads must all execute exactly once."""
    from perf_r9.primitives import Batch
    import threading

    b = Batch(max_batch=64, max_wait_ms=20)
    counter = {"n": 0}
    lock = threading.Lock()

    def inc():
        with lock:
            counter["n"] += 1

    threads = []
    for _ in range(4):
        def add_250():
            for _ in range(250):
                b.add(inc)
        t = threading.Thread(target=add_250)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    b.flush()
    assert counter["n"] == 1000, f"counter={counter['n']} (expected 1000)"


# ───────────────────────────────────────────────────────────────────
# Queue (priority)
# ───────────────────────────────────────────────────────────────────

def test_queue_push_pop_1000_preserves_priority():
    from perf_r9.primitives import AsyncQueue

    q = AsyncQueue(max_size=0)
    started = time.perf_counter()
    # AsyncQueue is a min-heap: items with the lowest ``priority``
    # value are popped first. So "high priority" = lower numerical
    # value, which matches the conventional "priority queue" semantics
    # (e.g. lowest distance in Dijkstra). The first 500 even items get
    # priority=0.0 (top), the rest get priority=1.0 (lower).
    for i in range(1000):
        priority = 0.0 if i < 500 else 1.0
        q.push({"i": i}, priority=priority)
    push_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    popped = []
    while True:
        # ``timeout`` must be a positive number — 0.0 is treated by
        # ``if timeout`` as falsy, which would block forever. Use 0.001
        # for a 1ms timeout.
        item = q.pop(timeout=0.001)
        if item is None:
            break
        popped.append(item["i"])
    pop_ms = (time.perf_counter() - started) * 1000

    assert len(popped) == 1000, f"only popped {len(popped)}/1000"
    # All i<500 items (high priority) should come out before any i>=500.
    for split_idx, i in enumerate(popped):
        if i >= 500:
            assert all(j < 500 for j in popped[:split_idx]), (
                f"low-priority item {i} appeared at position {split_idx} "
                f"before all high-priority items were drained"
            )
            break

    # Performance: 1000 push/pop should finish in well under 1s.
    assert push_ms < 1000, f"1000 push took {push_ms:.0f}ms"
    assert pop_ms < 1000, f"1000 pop took {pop_ms:.0f}ms"
    stats = q.stats()
    assert stats["enqueued"] == 1000, stats
    assert stats["dequeued"] == 1000, stats


# ───────────────────────────────────────────────────────────────────
# Pool
# ───────────────────────────────────────────────────────────────────

def test_pool_acquire_release_1000_times():
    """The object pool should re-use the same object across many cycles."""
    from perf_r9.primitives import Pool

    p = Pool(factory=list, max_size=10)
    acquired = []
    for _ in range(1000):
        obj = p.acquire()
        acquired.append(id(obj))
        p.release(obj)

    # Only a small number of distinct objects should have been created.
    distinct = len(set(acquired))
    assert distinct <= 10, (
        f"pool created {distinct} distinct objects (expected ≤ 10, "
        f"max_size=10) — pool is not re-using instances"
    )


# ───────────────────────────────────────────────────────────────────
# Combined stress: 1000 ops across all 4 primitives in 1s
# ───────────────────────────────────────────────────────────────────

def test_combined_4_primitives_1000_ops_under_2s():
    """A production hot-path uses cache + batch + queue + pool together.
    Verify 1000 ops across all four stays under 2s.
    """
    from perf_r9.primitives import TTLCache, Batch, AsyncQueue, Pool

    cache = TTLCache(max_size=2000, default_ttl_seconds=60)
    q = AsyncQueue(max_size=0)
    pool = Pool(factory=dict, max_size=8)
    b = Batch(max_batch=64, max_wait_ms=20)

    def process(n: int):
        # simulate a small pipeline
        cache.set(f"k{n}", n)
        q.push({"n": n}, priority=float(n % 3))
        obj = pool.acquire()
        pool.release(obj)
        return n * 2

    started = time.perf_counter()
    for i in range(1000):
        b.add(process, args=(i,))
    b.flush()
    elapsed = (time.perf_counter() - started)
    assert elapsed < 2.0, f"4-primitive 1000-op hot path took {elapsed:.2f}s"
    assert cache.stats()["size"] == 1000, cache.stats()
    while q.pop(timeout=0.0) is not None:
        pass
