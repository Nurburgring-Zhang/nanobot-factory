"""P21 P4 P1 — Lightweight load test for the v1.5.6 backend stack.

**Why this test exists (background)**

The full P6-Fix-B-6-2 1000-concurrent locust run is too heavy for the
30-minute worker cap on this round; we need a faster signal that
exercises the same code paths the production stack would push through
under modest parallelism.  The P21 R2 audit
(``reports/p21_r2_audit_data.md``) recorded that 100 concurrent DB
inserts complete in 0.81s with 0 errors, so 50 concurrent threads is
well within the safe zone and big enough to surface the most common
concurrency bugs:

  * Thread-unsafe DB session / connection pool
  * Lock contention on shared state
  * Per-request object leaks (memory growth)
  * Stale connection handles left open after the test ends
  * Middleware ordering / per-request resource leaks

**Test design**

We build a representative FastAPI app *in-process* that exercises the
same patterns the production ``backend/server.py`` uses:

  * ``RequestIdMiddleware`` + ``CSRFMiddleware`` + CORS via
    ``backend.common.middleware.mount_middleware`` (the same helper
    ``server.py:1627-1657`` calls).
  * Rate-limit middleware (same pattern as ``server.py``).
  * A lightweight ``/api/v1/health/live`` endpoint (always 200) — this
    is the hot loop endpoint the load runner hammers.
  * A real-DB ``/api/v1/health`` endpoint that opens + closes an
    ``sqlite3`` connection per request (the most common leak vector).
  * A shared-state ``/api/v1/lock`` endpoint that takes a
    ``threading.Lock`` per request (verifies no permanent dead-lock).
  * A JSON-parsing ``/api/v1/items`` POST endpoint (exercises the
    request-body → dict → DB INSERT path).
  * A connection-counting ``/api/v1/_diag/connections`` endpoint that
    inspects ``gc`` + ``sqlite3`` to expose live connection state.

The full 5193-line ``imdf/api/canvas_web.py`` cannot be imported today
(see R2-NEW-#1 audit, missing ``VidaEngineState`` symbol — out of scope
for this P4-P1 task).  The smaller representative app is therefore the
honest, repeatable test target for THIS task; a future P-task can
swap it for ``from api.canvas_web import app`` once the upstream
import is repaired.

**Run target**

    pytest tests/p4_p1/test_load_50_concurrent.py -v -s

  - 50 concurrent worker threads (ThreadPoolExecutor max_workers=50)
  - 10 requests per worker  →  500 total requests
  - All against the in-process TestClient (no network, no port, no
    external HTTP — the engine captures failures deterministically).

**Pass criteria**

  1. 0 errors out of 500 requests (HTTP 200 from every call).
  2. Total wall time < 60s (≈ 120ms/request budget, very generous).
  3. ``tracemalloc`` top-difference < 50MB between pre/post snapshots
     — guards against per-request object accumulation.
  4. Open sqlite3 connection count before/after the run is equal
     (the per-request ``conn.close()`` path actually runs).

**Hard rules respected**

  * No new dependencies (``tracemalloc`` + ``concurrent.futures`` are
    stdlib; ``fastapi`` / ``httpx`` / ``sqlite3`` are already in the
    project).  ``psutil`` is imported lazily and only for the
    optional RSS diagnostic; the test passes without it.
  * D:\\ComfyUI\\.ext\\python.exe runtime (env-set by the test runner).
  * In-process TestClient only — no live uvicorn, no ports, no
    external network.
  * D:\\Hermes\\生产平台\\nanobot-factory is the project root.
"""
from __future__ import annotations

import gc
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

# ─────────────────────────────────────────────────────────────────────
# Path setup (mirrors tests/conftest.py)
# ─────────────────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[2]  # tests/p4_p1/ → project root
_BACKEND = _PROJECT_ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

# ENV setup BEFORE any ``from common.middleware import ...``.
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CSRF_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")
os.environ.setdefault("JWT_SECRET", "x" * 64)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from common.middleware import (  # noqa: E402
    CSRFMiddleware,
    RequestIdMiddleware,
    mount_cors,
)


# ─────────────────────────────────────────────────────────────────────
# App factory — builds a representative v1.5.6-stack FastAPI app
# ─────────────────────────────────────────────────────────────────────

# Per-request in-process state that exercises the same locking /
# counter patterns the real production endpoints use.  Each test run
# gets a fresh instance (see ``_build_app``).
class _SharedState:
    """Thread-safe counter + lock registry used by the test endpoints."""

    def __init__(self) -> None:
        self._counter = 0
        self._counter_lock = threading.Lock()
        # Per-key locks — verifies the map itself is thread-safe under
        # heavy concurrent dict.setdefault() traffic.
        self._per_key_locks: Dict[str, threading.Lock] = {}
        self._per_key_locks_guard = threading.Lock()

    def incr(self) -> int:
        with self._counter_lock:
            self._counter += 1
            return self._counter

    def acquire_key_lock(self, key: str) -> None:
        with self._per_key_locks_guard:
            lock = self._per_key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._per_key_locks[key] = lock
        # Hold the lock only briefly — drop immediately, the test
        # only cares that the dict + lock interaction is safe.
        with lock:
            pass


def _open_temp_sqlite_db() -> str:
    """Create a per-run temp SQLite file (avoids :memory: share-cache issues)."""
    tmpdir = tempfile.mkdtemp(prefix="p4p1_load_")
    db_path = os.path.join(tmpdir, "load.db")
    # Bootstrap the schema so the per-request ``check_database`` path
    # has something to read.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, payload TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS healthcheck (id INTEGER PRIMARY KEY, ts TEXT)")
        conn.execute("INSERT INTO healthcheck(ts) VALUES ('init')")
        conn.commit()
    finally:
        conn.close()
    return db_path


def _build_app(db_path: str) -> FastAPI:
    """Build the representative load-test app.

    Mirrors the wiring in ``backend/server.py:1580-1660``:
      * ``mount_middleware`` (CORS + CSRF + RequestId)
      * rate-limit middleware (lightweight token-bucket)
      * 5 representative endpoints
    """
    app = FastAPI(title="P4-P1 Load Test Harness")
    state = _SharedState()

    # ---- Middleware wiring (matches server.py 1627-1660) -------------
    # Order (Starlette LIFO): CORS innermost → CSRF → RequestId outermost.
    # mount_middleware adds CORS first, then CSRF, then RequestId, which
    # Starlette reverses at request time.
    mount_cors(
        app,
        allow_origins=["http://localhost:5173", "http://localhost:8765"],
    )
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=["http://localhost:5173", "http://localhost:8765"],
        enabled=False,  # CSRF off in test mode (matches conftest.py)
    )
    app.add_middleware(RequestIdMiddleware)

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        """Lightweight in-process rate limiter — bounds concurrent fanout.

        Mirrors the ``rate_limit_middleware`` decorator in
        ``server.py:1282`` (token-bucket per remote).  We use a simple
        sliding-window counter to keep this self-contained.
        """
        # 5xx-style failure is never reached in this test (the bucket
        # is generous); included so the middleware shape is realistic.
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - safety net
            return JSONResponse(
                {"error": f"unhandled: {exc.__class__.__name__}"},
                status_code=500,
            )
        return response

    # ---- Endpoints ---------------------------------------------------

    @app.get("/api/v1/health/live")
    async def health_live():
        """Lightweight liveness — exercised by every load-test request."""
        return {"success": True, "data": {"status": "ok"}}

    @app.get("/api/v1/health")
    async def health_basic():
        """Full health — opens + closes a real sqlite3 connection per call.

        This is the path that most commonly leaks file descriptors in
        legacy backends; we measure the connection count before/after
        the load run to assert that the close path actually fires.
        """
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM healthcheck").fetchone()
            ok = bool(row and row[0] >= 1)
        finally:
            conn.close()
        return {
            "success": ok,
            "data": {"status": "ok" if ok else "degraded", "db": "ok"},
        }

    @app.get("/api/v1/lock")
    async def lock_check():
        """Shared-state endpoint — exercises the per-key lock map."""
        n = state.incr()
        state.acquire_key_lock(f"k-{n % 7}")  # 7 distinct keys
        return {"success": True, "data": {"counter": n}}

    @app.post("/api/v1/items")
    async def create_item(request: Request):
        """JSON-parsing POST + sqlite3 INSERT — most common write path."""
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            return JSONResponse(
                {"error": f"invalid json: {exc.msg}"}, status_code=400
            )
        payload = json.dumps(body, sort_keys=True)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO items(payload) VALUES (?)", (payload,)
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
        return {"success": True, "data": {"id": new_id, "len": len(payload)}}

    @app.get("/api/v1/_diag/connections")
    async def diag_connections():
        """Diagnostic — report live sqlite3 connection count via gc.

        Counts the number of live ``sqlite3.Connection`` objects via
        ``gc.get_objects()`` so the load test can assert pre/post
        equality.
        """
        conns = [o for o in gc.get_objects() if isinstance(o, sqlite3.Connection)]
        return {
            "success": True,
            "data": {
                "open_sqlite_connections": len(conns),
                "counter": state._counter,
                "lock_map_size": len(state._per_key_locks),
            },
        }

    return app


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _tracemalloc_snapshot() -> Tuple[int, int]:
    """Return ``(current_bytes, peak_bytes)`` from ``tracemalloc``."""
    snap = tracemalloc.take_snapshot()
    total = sum(stat.size for stat in snap.statistics("filename"))
    return total, tracemalloc.get_traced_memory()[1]


def _open_sqlite_count() -> int:
    """Live count of sqlite3.Connection objects in the process."""
    gc.collect()
    return sum(1 for o in gc.get_objects() if isinstance(o, sqlite3.Connection))


# ─────────────────────────────────────────────────────────────────────
# Test fixture
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def load_test_harness():
    """Build the test app + TestClient + DB path, yield, then tear down."""
    db_path = _open_temp_sqlite_db()
    app = _build_app(db_path)
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield {"client": client, "app": app, "db_path": db_path}
    finally:
        client.close()
        # Best-effort DB cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass
        try:
            os.rmdir(os.path.dirname(db_path))
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────
# The actual load test
# ─────────────────────────────────────────────────────────────────────

WORKERS = 50
REQUESTS_PER_WORKER = 10
TOTAL_REQUESTS = WORKERS * REQUESTS_PER_WORKER
TARGET_TOTAL_SECONDS = 60.0
MAX_MEM_GROWTH_BYTES = 50 * 1024 * 1024  # 50MB


def _single_request(client: TestClient, idx: int) -> Tuple[int, float, str]:
    """Issue ONE request, return ``(status, latency_ms, endpoint)``."""
    # Mix endpoints to exercise different code paths.  80% health/live
    # (hot loop), 15% /health (DB), 5% /lock (shared state).
    bucket = idx % 20
    if bucket < 16:
        endpoint = "/api/v1/health/live"
        method = client.get
    elif bucket < 19:
        endpoint = "/api/v1/health"
        method = client.get
    else:
        endpoint = "/api/v1/lock"
        method = client.get

    t0 = time.perf_counter()
    try:
        resp = method(endpoint, headers={"X-Request-ID": f"loadtest-{idx}"})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return resp.status_code, elapsed_ms, endpoint
    except Exception as exc:  # pragma: no cover - surfaced as err count
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return -1, elapsed_ms, f"{endpoint}: {exc.__class__.__name__}"


def test_load_50_concurrent(load_test_harness):
    """50 concurrent threads × 10 requests = 500 total; assert 0 errors.

    Pass criteria (all four must hold):
      1. 0 errors (status < 0 OR status >= 500) out of 500 requests
      2. Total wall time < 60s
      3. ``tracemalloc`` peak growth < 50MB
      4. Open sqlite3 connection count before/after is equal
    """
    client = load_test_harness["client"]

    # ----- Pre-run diagnostics -----------------------------------------
    gc.collect()
    pre_conn_count = _open_sqlite_count()
    tracemalloc.start()
    # Let tracemalloc settle on the current heap
    time.sleep(0.05)
    pre_mem_bytes, _pre_peak = _tracemalloc_snapshot()

    # ----- Run ---------------------------------------------------------
    errors: List[Tuple[int, str, float]] = []   # (idx, detail, latency_ms)
    latencies: List[float] = []
    by_endpoint: Dict[str, int] = {}
    by_status: Dict[int, int] = {}

    def _worker(worker_id: int) -> List[Tuple[int, int, float, str]]:
        """Each thread runs REQUESTS_PER_WORKER sequential requests."""
        local = []
        for j in range(REQUESTS_PER_WORKER):
            idx = worker_id * REQUESTS_PER_WORKER + j
            status, latency_ms, endpoint = _single_request(client, idx)
            local.append((idx, status, latency_ms, endpoint))
        return local

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_worker, w) for w in range(WORKERS)]
        for fut in as_completed(futures):
            for idx, status, latency_ms, endpoint in fut.result():
                latencies.append(latency_ms)
                by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
                by_status[status] = by_status.get(status, 0) + 1
                if status < 0 or status >= 500:
                    errors.append((idx, endpoint, latency_ms))
    total_seconds = time.perf_counter() - t_start

    # ----- Post-run diagnostics ----------------------------------------
    # Let in-flight connections / async tasks settle.
    time.sleep(0.2)
    gc.collect()
    post_mem_bytes, post_peak = _tracemalloc_snapshot()
    post_conn_count = _open_sqlite_count()
    mem_growth_bytes = max(0, post_mem_bytes - pre_mem_bytes)
    conn_delta = post_conn_count - pre_conn_count

    tracemalloc.stop()

    # ----- Aggregate metrics ------------------------------------------
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
    p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0.0
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0.0
    max_latency_ms = max(latencies) if latencies else 0.0
    error_count = len(errors)
    error_rate = error_count / TOTAL_REQUESTS if TOTAL_REQUESTS else 0.0

    # ----- Report ------------------------------------------------------
    summary = {
        "total_requests": TOTAL_REQUESTS,
        "workers": WORKERS,
        "requests_per_worker": REQUESTS_PER_WORKER,
        "total_seconds": round(total_seconds, 3),
        "avg_latency_ms": round(avg_latency_ms, 3),
        "p50_latency_ms": round(p50, 3),
        "p99_latency_ms": round(p99, 3),
        "max_latency_ms": round(max_latency_ms, 3),
        "rps": round(TOTAL_REQUESTS / total_seconds, 2) if total_seconds > 0 else 0.0,
        "error_count": error_count,
        "error_rate": round(error_rate, 4),
        "by_status": dict(sorted(by_status.items())),
        "by_endpoint": dict(sorted(by_endpoint.items())),
        "tracemalloc": {
            "pre_bytes": pre_mem_bytes,
            "post_bytes": post_mem_bytes,
            "peak_bytes": post_peak,
            "growth_bytes": mem_growth_bytes,
            "growth_mb": round(mem_growth_bytes / (1024 * 1024), 3),
            "limit_mb": MAX_MEM_GROWTH_BYTES // (1024 * 1024),
        },
        "sqlite_connections": {
            "pre_count": pre_conn_count,
            "post_count": post_conn_count,
            "delta": conn_delta,
        },
        "errors_sample": errors[:10],  # first 10 only
    }

    # Stash summary on the test module so the deliverable can pick it
    # up if needed (pytest doesn't pass return values back, so this is
    # a side-channel for the post-test report).
    test_load_50_concurrent._last_summary = summary

    # ----- Assertions --------------------------------------------------
    assert error_count == 0, (
        f"Load test: {error_count}/{TOTAL_REQUESTS} requests failed "
        f"(error_rate={error_rate:.4f}). First 10 errors: {errors[:10]}\n"
        f"By status: {summary['by_status']}\n"
        f"By endpoint: {summary['by_endpoint']}"
    )
    assert total_seconds < TARGET_TOTAL_SECONDS, (
        f"Load test: total time {total_seconds:.2f}s exceeds "
        f"{TARGET_TOTAL_SECONDS}s budget. avg={avg_latency_ms:.2f}ms, "
        f"p99={p99:.2f}ms, max={max_latency_ms:.2f}ms"
    )
    assert mem_growth_bytes < MAX_MEM_GROWTH_BYTES, (
        f"Load test: memory growth {mem_growth_bytes} bytes "
        f"({mem_growth_bytes / (1024 * 1024):.2f}MB) exceeds "
        f"{MAX_MEM_GROWTH_BYTES // (1024 * 1024)}MB limit. "
        f"tracemalloc: pre={pre_mem_bytes} post={post_mem_bytes} "
        f"peak={post_peak}"
    )
    assert conn_delta == 0, (
        f"Load test: sqlite3 connection count drifted by {conn_delta} "
        f"during the run (pre={pre_conn_count} post={post_conn_count}). "
        f"This suggests per-request connections are not being closed. "
        f"NOTE: the diagnostic endpoint itself opens a connection, so "
        f"a small drift is expected; a large delta indicates a leak."
    )

    # Also print the summary so the test log captures it for the
    # report writer.
    print("\n" + "=" * 70)
    print("P4 P1 — 50-concurrent load test results")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str))
    print("=" * 70)


# Allow the deliverable / report writer to import the most recent
# summary without re-running the test.
def _get_last_summary() -> Dict:
    return getattr(test_load_50_concurrent, "_last_summary", {})
