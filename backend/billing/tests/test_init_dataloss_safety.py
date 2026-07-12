"""P15-C: ``init_billing_runtime()`` data-loss safety tests.

The bug
-------
Before P15-C, ``init_billing_runtime()`` in :mod:`billing` called
``reset_state()`` with no arguments, which defaulted to
``reset_db=True``. That meant every process startup **wiped the persisted
quota tables** — a P0 data-loss bug for production.

The fix
-------
1. ``init_billing_runtime(reset_db=None)`` defaults to ``False`` (production
   safe).
2. ``BILLING_RESET_DB_ON_STARTUP`` env var provides an opt-in for dev / test
   workflows (truthy tokens: ``1``, ``true``, ``yes``, ``on``).
3. Resolution order: explicit arg > env var > ``False``.

What these tests verify
-----------------------
1. **TestInitRuntimeDefaults** — the default ``reset_db=False`` path does
   not touch persisted quota tables.
2. **TestRestartPreservesAllData** — 1 000 quota records survive a second
   ``init_billing_runtime()`` call (simulated process restart). The
   ``quota_usage`` row count is unchanged.
3. **TestEnvResetOptIn** — ``BILLING_RESET_DB_ON_STARTUP=1`` does wipe the
   tables, restoring the dev/test clean-slate behavior.

All tests run against a tmp_path SQLite file so they cannot collide with
real production data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── path injection (matches existing billing/tests/*.py style) ────────────
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from sqlalchemy import select, text

from billing import init_billing_runtime
from billing.db import reset_engine
from billing.quota_models import QuotaEvent, QuotaUsage


# ─── helpers ───────────────────────────────────────────────────────────────


def _set_db_url(monkeypatch, db_path: Path) -> str:
    """Point the global engine at ``db_path`` and return the URL.

    Also forces ``QUOTA_TRACKER_BACKEND=db`` so ``_build_state`` builds a
    real :class:`DBQuotaTracker` against this file. ``reset_engine()``
    drops the cached engine so the next ``get_engine()`` rebuilds against
    the new URL.
    """
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("BILLING_DB_URL", url)
    monkeypatch.setenv("QUOTA_TRACKER_BACKEND", "db")
    # Belt and suspenders — strip any prior opt-in.
    monkeypatch.delenv("BILLING_RESET_DB_ON_STARTUP", raising=False)
    reset_engine()
    return url


def _count_usage_rows(db_path: Path) -> int:
    """Open a fresh engine against ``db_path`` and count quota_usage rows.

    Uses a brand-new engine (not the cached singleton) so we read the
    on-disk truth without any in-memory cache interference.
    """
    from sqlalchemy import create_engine
    eng = create_engine(f"sqlite:///{db_path}")
    try:
        with eng.connect() as conn:
            return int(
                conn.execute(text("SELECT COUNT(*) FROM quota_usage")).scalar_one()
            )
    finally:
        eng.dispose()


def _count_event_rows(db_path: Path) -> int:
    """Same as :func:`_count_usage_rows` but for ``quota_event``."""
    from sqlalchemy import create_engine
    eng = create_engine(f"sqlite:///{db_path}")
    try:
        with eng.connect() as conn:
            return int(
                conn.execute(text("SELECT COUNT(*) FROM quota_event")).scalar_one()
            )
    finally:
        eng.dispose()


# ─── 1. Default behavior: no destructive reset ──────────────────────────────


class TestInitRuntimeDefaults:
    """``init_billing_runtime()`` with no arguments must NOT wipe data."""

    def test_001_default_no_reset_db_arg_does_not_wipe(self, tmp_path, monkeypatch):
        """Calling ``init_billing_runtime()`` on a DB with prior records
        must leave the records intact.

        This is the core P0 regression test.
        """
        db_path = tmp_path / "default_safe.db"
        url = _set_db_url(monkeypatch, db_path)

        # ── First "startup": fresh DB, write 50 records.
        init_billing_runtime(url=url)
        # Pull the tracker out of the rebuilt _STATE.
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        for i in range(50):
            tracker.record(f"user_{i:04d}", "datasets", 1)
        # Force flush + cache invalidation before counting.
        tracker.engine.dispose()
        reset_engine()

        assert _count_usage_rows(db_path) == 50

        # ── Second "startup": simulated process restart, default args.
        init_billing_runtime(url=url)

        # Data MUST survive — this is the P0 fix.
        assert _count_usage_rows(db_path) == 50, (
            "P0 data-loss bug regressed: init_billing_runtime() wiped "
            "quota_usage on the second startup"
        )

    def test_002_explicit_reset_db_false_preserves_data(self, tmp_path, monkeypatch):
        """Explicit ``reset_db=False`` argument must preserve data."""
        db_path = tmp_path / "explicit_false.db"
        url = _set_db_url(monkeypatch, db_path)

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        for i in range(20):
            tracker.record(f"u{i}", "ai_tokens", 100)
        tracker.engine.dispose()
        reset_engine()

        init_billing_runtime(url=url, reset_db=False)
        assert _count_usage_rows(db_path) == 20

    def test_003_unset_env_does_not_reset(self, tmp_path, monkeypatch):
        """When ``BILLING_RESET_DB_ON_STARTUP`` is unset, no reset happens."""
        db_path = tmp_path / "env_unset.db"
        url = _set_db_url(monkeypatch, db_path)
        # Make sure the env var is unset (fixture already does this, but
        # belt-and-suspenders in case other tests touched it).
        monkeypatch.delenv("BILLING_RESET_DB_ON_STARTUP", raising=False)

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        tracker.record("alice", "datasets", 5)
        tracker.engine.dispose()
        reset_engine()

        init_billing_runtime(url=url)
        assert _count_usage_rows(db_path) == 1

    def test_004_env_empty_string_does_not_reset(self, tmp_path, monkeypatch):
        """Empty env string must be treated as False (no reset)."""
        db_path = tmp_path / "env_empty.db"
        url = _set_db_url(monkeypatch, db_path)
        monkeypatch.setenv("BILLING_RESET_DB_ON_STARTUP", "")

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        tracker.record("alice", "datasets", 5)
        tracker.engine.dispose()
        reset_engine()

        init_billing_runtime(url=url)
        assert _count_usage_rows(db_path) == 1

    def test_005_env_falsey_tokens_do_not_reset(self, tmp_path, monkeypatch):
        """``0``, ``false``, ``no``, ``off`` all mean False (no reset)."""
        for token in ("0", "false", "no", "off", "FALSE", "No", "OFF"):
            # Each iteration: fresh DB.
            db_path = tmp_path / f"env_{token}_safe.db"
            url = _set_db_url(monkeypatch, db_path)
            monkeypatch.setenv("BILLING_RESET_DB_ON_STARTUP", token)

            init_billing_runtime(url=url)
            from billing import routes as _routes
            tracker = _routes.get_state()["quota_tracker"]
            tracker.record("alice", "datasets", 3)
            tracker.engine.dispose()
            reset_engine()

            init_billing_runtime(url=url)
            assert _count_usage_rows(db_path) == 1, (
                f"token {token!r} unexpectedly reset the DB"
            )
            # Reset env for next iteration (monkeypatch undoes at teardown
            # anyway, but be explicit).
            monkeypatch.delenv("BILLING_RESET_DB_ON_STARTUP", raising=False)


# ─── 2. Restart preserves 1 000 records ─────────────────────────────────────


class TestRestartPreservesAllData:
    """Write 1 000 records, restart, verify all survive + quota_usage size
    unchanged."""

    def test_010_1000_records_survive_restart(self, tmp_path, monkeypatch):
        """The flagship restart-safety test for the P15-C fix."""
        db_path = tmp_path / "restart_1000.db"
        url = _set_db_url(monkeypatch, db_path)

        # ── Boot #1 — schema + tracker live.
        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]

        # Write exactly 1 000 quota records → 1 000 distinct (user, dim)
        # pairs → 1 000 rows in quota_usage. The DBQuotaTracker UPSERTs on
        # (user_id, dimension), so each call to record() must target a
        # unique pair to grow the row count.
        N = 1_000
        DIM = "datasets"
        for i in range(N):
            tracker.record(f"user_{i:04d}", DIM, 1)
        tracker.engine.dispose()
        reset_engine()

        # Sanity: the on-disk count is N.
        usage_before = _count_usage_rows(db_path)
        event_before = _count_event_rows(db_path)
        assert usage_before == N, (
            f"setup wrote {usage_before} rows, expected {N}"
        )
        assert event_before == N, (
            f"setup wrote {event_before} event rows, expected {N}"
        )

        # ── Boot #2 — simulated restart with default args.
        init_billing_runtime(url=url)

        # All N rows must still be in quota_usage AND quota_event.
        usage_after = _count_usage_rows(db_path)
        event_after = _count_event_rows(db_path)
        assert usage_after == usage_before, (
            f"quota_usage size changed: {usage_before} → {usage_after} "
            "(data loss!)"
        )
        assert event_after == event_before, (
            f"quota_event size changed: {event_before} → {event_after} "
            "(audit trail lost!)"
        )
        assert usage_after == N

        # Spot-check a few snapshots via a fresh tracker so we know the
        # actual values are still readable (not just the row counts).
        reset_engine()
        from billing.quota_db import DBQuotaTracker
        verifier = DBQuotaTracker(url=url, auto_init=False)
        try:
            # Spot-check the first / middle / last user, each should have
            # qty=1 (one record call per pair).
            assert verifier.current("user_0000", DIM) == 1
            assert verifier.current("user_0500", DIM) == 1
            assert verifier.current("user_0999", DIM) == 1
            # Also verify a missing pair returns 0 (proves the table was
            # not wiped and re-seeded with a different scheme).
            assert verifier.current("user_9999", DIM) == 0
        finally:
            verifier.engine.dispose()

    def test_011_three_restarts_in_a_row(self, tmp_path, monkeypatch):
        """Three successive restarts must not lose data either."""
        db_path = tmp_path / "restart_3x.db"
        url = _set_db_url(monkeypatch, db_path)

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        for i in range(30):
            tracker.record(f"u{i}", "datasets", i + 1)
        tracker.engine.dispose()
        reset_engine()

        for boot in range(3):
            init_billing_runtime(url=url)
            assert _count_usage_rows(db_path) == 30, (
                f"restart #{boot + 1}: lost rows"
            )
            reset_engine()


# ─── 3. ENV opt-in: dev / test mode wipes ───────────────────────────────────


class TestEnvResetOptIn:
    """``BILLING_RESET_DB_ON_STARTUP`` truthy tokens enable the destructive
    reset (matches the pre-P15-C behavior for dev / test workflows)."""

    @pytest.mark.parametrize("token", ["1", "true", "yes", "on", "TRUE", "Yes", "ON"])
    def test_020_truthy_env_resets_db(self, tmp_path, monkeypatch, token):
        """Each truthy token must trigger a destructive reset."""
        db_path = tmp_path / f"env_{token}_reset.db"
        url = _set_db_url(monkeypatch, db_path)
        monkeypatch.setenv("BILLING_RESET_DB_ON_STARTUP", token)

        # Boot #1 — schema created, 10 records written.
        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        for i in range(10):
            tracker.record(f"u{i}", "datasets", 1)
        tracker.engine.dispose()
        reset_engine()

        assert _count_usage_rows(db_path) == 10

        # Boot #2 with the truthy env — destructive reset wipes the rows.
        init_billing_runtime(url=url)
        assert _count_usage_rows(db_path) == 0, (
            f"truthy token {token!r} failed to reset quota_usage"
        )

    def test_021_explicit_reset_db_true_overrides_safe_env(self, tmp_path, monkeypatch):
        """Explicit ``reset_db=True`` arg overrides env (still defaults to
        reset if explicit wins)."""
        db_path = tmp_path / "explicit_override.db"
        url = _set_db_url(monkeypatch, db_path)
        # Env explicitly says False (no reset).
        monkeypatch.setenv("BILLING_RESET_DB_ON_STARTUP", "false")

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        tracker.record("alice", "datasets", 7)
        tracker.engine.dispose()
        reset_engine()

        # Explicit reset_db=True wins over env=False.
        init_billing_runtime(url=url, reset_db=True)
        assert _count_usage_rows(db_path) == 0

    def test_022_explicit_reset_db_false_overrides_truthy_env(self, tmp_path, monkeypatch):
        """Explicit ``reset_db=False`` overrides even a truthy env."""
        db_path = tmp_path / "explicit_safe_override.db"
        url = _set_db_url(monkeypatch, db_path)
        monkeypatch.setenv("BILLING_RESET_DB_ON_STARTUP", "1")

        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        tracker.record("alice", "datasets", 4)
        tracker.engine.dispose()
        reset_engine()

        # Explicit reset_db=False wins over env="1".
        init_billing_runtime(url=url, reset_db=False)
        assert _count_usage_rows(db_path) == 1


# ─── 4. Quota_usage table size specifically tracked ────────────────────────


class TestQuotaUsageSizeTracked:
    """Spec test (5): verify ``quota_usage`` table size did not change across
    restart, after writing exactly 1 000 records."""

    def test_030_quota_usage_size_unchanged_after_restart(
        self, tmp_path, monkeypatch,
    ):
        db_path = tmp_path / "size_tracking.db"
        url = _set_db_url(monkeypatch, db_path)

        # Boot #1 + write exactly 1 000 records.
        init_billing_runtime(url=url)
        from billing import routes as _routes
        tracker = _routes.get_state()["quota_tracker"]
        for i in range(1_000):
            tracker.record(f"u{i:04d}", "datasets", 1)
        tracker.engine.dispose()
        reset_engine()

        size_before = _count_usage_rows(db_path)
        assert size_before == 1_000

        # Boot #2 (default — production safe).
        init_billing_runtime(url=url)

        size_after = _count_usage_rows(db_path)
        assert size_after == size_before, (
            f"quota_usage row count changed: {size_before} → {size_after}"
        )
        assert size_after == 1_000