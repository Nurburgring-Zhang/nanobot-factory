"""R8-Worker-2 — factory fixtures + single-request p95 baseline.

§3 of the task:
  * factory_boy-style fixtures: 50 users + 100 projects + 200 tasks
  * performance baseline: single-request p95 latency

The "p95" is computed locally on 50 sequential ``/healthz`` calls (the
cheapest live endpoint). Real load testing belongs to a separate tool
(e.g. wrk, k6); here we just record the order-of-magnitude so a future
regression has something to compare against.
"""
from __future__ import annotations

import sqlite3
import statistics
import time
from pathlib import Path

import pytest

# Make the factories module importable when pytest is run from project root.
import sys
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from factories import UserFactory, ProjectFactory, TaskFactory  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures — factory_boy-style seed data
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    """Create 50 users + 100 projects + 200 tasks in an isolated sqlite file.

    Returns a (path, counts) tuple so the test can assert row counts and
    so the perf baseline can read from the same shape of data.
    """
    db_file = tmp_path_factory.mktemp("factory") / "factory.db"
    conn = sqlite3.connect(str(db_file), timeout=5.0)
    try:
        users = UserFactory.create_batch(conn, 50)
        projects = ProjectFactory.create_batch(conn, 100)
        tasks = TaskFactory.create_batch(conn, 200)

        # Verify counts
        u_count = conn.execute("SELECT COUNT(*) FROM factory_users").fetchone()[0]
        p_count = conn.execute("SELECT COUNT(*) FROM factory_projects").fetchone()[0]
        t_count = conn.execute("SELECT COUNT(*) FROM factory_tasks").fetchone()[0]
        assert (u_count, p_count, t_count) == (50, 100, 200), (
            f"expected (50,100,200), got ({u_count},{p_count},{t_count})"
        )
        yield {
            "path": str(db_file),
            "counts": {"users": u_count, "projects": p_count, "tasks": t_count},
            "users": users,
            "projects": projects,
            "tasks": tasks,
        }
    finally:
        conn.close()


class TestFactorySeeding:
    def test_50_users_seeded(self, seeded_db):
        assert len(seeded_db["users"]) == 50
        usernames = {u["username"] for u in seeded_db["users"]}
        assert len(usernames) == 50, "user usernames must be unique"

    def test_100_projects_seeded(self, seeded_db):
        assert len(seeded_db["projects"]) == 100

    def test_200_tasks_seeded(self, seeded_db):
        assert len(seeded_db["tasks"]) == 200

    def test_referential_integrity(self, seeded_db, tmp_path):
        """Every project.owner_id references an existing user.id."""
        conn = sqlite3.connect(seeded_db["path"])
        try:
            bad = conn.execute(
                """
                SELECT p.id FROM factory_projects p
                LEFT JOIN factory_users u ON u.id = p.owner_id
                WHERE u.id IS NULL
                """
            ).fetchall()
            assert not bad, f"orphan projects: {bad[:5]}"

            bad_t = conn.execute(
                """
                SELECT t.id FROM factory_tasks t
                LEFT JOIN factory_projects p ON p.id = t.project_id
                WHERE p.id IS NULL
                """
            ).fetchall()
            assert not bad_t, f"orphan tasks: {bad_t[:5]}"
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# Performance baseline — single-request p95 against /healthz
# --------------------------------------------------------------------------- #
class TestPerfBaseline:
    """Light-touch baseline — not a load test, just a regression anchor."""

    def test_healthz_p95_under_500ms(self, client):
        """50 sequential /healthz hits; p95 must be < 500 ms.

        /healthz is the cheapest endpoint (no DB, no FS), so its p95 is a
        good proxy for framework overhead. Anything > 500 ms here means
        something has slowed the event loop itself.
        """
        N = 50
        latencies_ms: list[float] = []
        # One warm-up to skip first-call costs (imports, etc.)
        client.get("/healthz")
        for _ in range(N):
            t0 = time.perf_counter()
            r = client.get("/healthz")
            dt = (time.perf_counter() - t0) * 1000.0
            assert r.status_code == 200, r.text
            latencies_ms.append(dt)

        p50 = statistics.median(latencies_ms)
        p95 = sorted(latencies_ms)[int(0.95 * N) - 1]
        p99 = sorted(latencies_ms)[int(0.99 * N) - 1]
        mx = max(latencies_ms)
        mn = min(latencies_ms)

        # Persist a tiny CSV alongside the test for the deliverable to pick up.
        out = _HERE / "perf_baseline.csv"
        with open(out, "w", encoding="utf-8") as f:
            f.write("metric,value_ms\n")
            for k, v in [("min", mn), ("p50", p50), ("p95", p95),
                         ("p99", p99), ("max", mx), ("n", float(N))]:
                f.write(f"{k},{v:.3f}\n")

        assert p95 < 500.0, (
            f"p95 {p95:.1f}ms exceeds 500ms target; "
            f"p50={p50:.1f} p99={p99:.1f} max={mx:.1f} (n={N})"
        )

    def test_readyz_p95_under_800ms(self, client):
        """50 sequential /readyz hits; p95 must be < 800 ms (DB ping included)."""
        N = 50
        latencies_ms: list[float] = []
        client.get("/readyz")  # warm-up
        for _ in range(N):
            t0 = time.perf_counter()
            r = client.get("/readyz")
            dt = (time.perf_counter() - t0) * 1000.0
            # /readyz may legitimately be 503 (DB missing) — we only care
            # about latency, not status, for the baseline.
            assert r.status_code in (200, 503)
            latencies_ms.append(dt)

        p50 = statistics.median(latencies_ms)
        p95 = sorted(latencies_ms)[int(0.95 * N) - 1]
        mx = max(latencies_ms)

        # Append to the same CSV
        out = _HERE / "perf_baseline.csv"
        with open(out, "a", encoding="utf-8") as f:
            f.write("---readyz---\n")
            for k, v in [("min", min(latencies_ms)), ("p50", p50),
                         ("p95", p95), ("max", mx), ("n", float(N))]:
                f.write(f"{k},{v:.3f}\n")

        assert p95 < 800.0, (
            f"/readyz p95 {p95:.1f}ms exceeds 800ms; p50={p50:.1f} max={mx:.1f}"
        )
