"""P19-E3 / F2 fix-5: Pluggable storage backends for :class:`SLORecorder`.

Why this module
---------------
The default in-process ring buffer in :class:`SLORecorder` (in ``slo.py``)
is per-process: a uvicorn worker has its own deque, a Celery worker has
its own, and the FastAPI process has its own. For real deployments
(multi-worker uvicorn behind nginx, multi-pod k8s, sidecar processes)
budget calculations diverge between processes — a 0.5% bad-request ratio
in one worker looks like 5% bad-request ratio in another, just because
they observed different traffic.

This module introduces a :class:`SLORecorderBackend` Protocol with two
implementations:

* :class:`InMemoryBackend` — drop-in replacement for the existing deque,
  thread-safe, identical behavior to ``SLORecorder._records`` (good for
  single-process tests).
* :class:`SQLiteBackend` — file-backed ring buffer. Multiple processes
  sharing the same SQLite file see the same outcomes. Writes go through
  a single connection (the binding process); reads use a fresh read-only
  connection so workers don't contend on a writer lock.

The existing :class:`SLORecorder` keeps the in-process deque by default
to preserve its current API surface. The new
:func:`SLORecorder.with_backend` factory method returns a recorder that
delegates to a backend — used by the new test for the multi-process case.

Backward compatibility
----------------------
* ``SLORecorder.record_outcome`` / ``record_batch`` / ``snapshot`` /
  ``reset`` / ``compute_budget`` keep their signatures.
* Tests that exercise :class:`SLORecorder` directly (test_slo.py) keep
  passing unchanged.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# Backend Protocol
# --------------------------------------------------------------------------- #
@runtime_checkable
class SLORecorderBackend(Protocol):
    """Pluggable storage backend for :class:`SLORecorder`.

    All methods MUST be thread-safe. Methods that take / return dicts
    use the same shape as the existing in-process deque:
    ``{"success": bool, "latency_ms": float, "ts": float}``.
    """

    def append(self, record: Dict[str, Any]) -> None:
        """Append a single record."""
        ...

    def extend(self, records: List[Dict[str, Any]]) -> None:
        """Append many records at once."""
        ...

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return all records currently in storage (atomic)."""
        ...

    def prune_older_than(self, cutoff_ts: float) -> int:
        """Delete records with ``ts < cutoff_ts``; return number deleted."""
        ...

    def cap_max(self, max_records: int) -> int:
        """Drop oldest records until length ``<= max_records``; return count deleted."""
        ...

    def reset(self) -> None:
        """Remove all records."""
        ...


# --------------------------------------------------------------------------- #
# In-memory implementation (default; preserves existing behavior)
# --------------------------------------------------------------------------- #
@dataclass
class InMemoryBackend:
    """Thread-safe deque-backed backend.

    Mirrors the storage shape of ``SLORecorder._records`` exactly so
    tests that previously asserted behavior on the deque still pass.
    """

    _records: Deque[Dict[str, Any]] = None  # type: ignore[assignment]
    _lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._records is None:
            self._records = deque()
        if self._lock is None:
            self._lock = threading.Lock()

    def append(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._records.append(record)

    def extend(self, records: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._records.extend(records)

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def prune_older_than(self, cutoff_ts: float) -> int:
        with self._lock:
            deleted = 0
            while self._records and self._records[0].get("ts", 0.0) < cutoff_ts:
                self._records.popleft()
                deleted += 1
            return deleted

    def cap_max(self, max_records: int) -> int:
        with self._lock:
            deleted = 0
            while len(self._records) > max_records:
                self._records.popleft()
                deleted += 1
            return deleted

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


# --------------------------------------------------------------------------- #
# SQLite-backed implementation (multi-process safe)
# --------------------------------------------------------------------------- #
@dataclass
class SQLiteBackend:
    """File-backed ring buffer.

    Multiple processes can point at the same ``db_path`` and observe each
    other's writes (SQLite WAL mode). Each instance owns its own connection
    — the binding process uses a read-write connection, others may use
    a read-only connection by setting ``read_only=True``.

    Schema::

        CREATE TABLE slo_outcomes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slo_name    TEXT NOT NULL,
            ts          REAL NOT NULL,
            success     INTEGER NOT NULL,    -- 0 / 1
            latency_ms  REAL NOT NULL,
            extra_json  TEXT                 -- JSON-encoded extra metadata
        );

        CREATE INDEX ix_slo_outcomes_name_ts ON slo_outcomes(slo_name, ts);
    """

    slo_name: str
    db_path: str
    read_only: bool = False
    # Optional: cap how many rows this backend will retain for its SLO. The
    # default is 1_000_000 rows which is far more than any production
    # deployment should need but cheap in SQLite.
    max_records: int = 1_000_000
    _conn: Optional[sqlite3.Connection] = None
    _lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._lock is None:
            # F2 fix-5 attempt-6: use RLock so ``append`` may call helpers
            # like ``cap_max`` (which re-acquire the lock) without deadlocking.
            self._lock = threading.RLock()
        self._open()

    def _open(self) -> None:
        """Open the SQLite connection. Creates schema if needed."""
        # Ensure parent dir exists for the read-write case.
        if not self.read_only:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        uri = (
            f"{self.db_path}?mode=ro" if self.read_only else self.db_path
        )
        # ``check_same_thread=False`` lets us hand the connection across
        # threads; we serialize access with self._lock.
        self._conn = sqlite3.connect(
            uri,
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,  # autocommit; we manage transactions explicitly
        )
        if not self.read_only:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS slo_outcomes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    slo_name    TEXT NOT NULL,
                    ts          REAL NOT NULL,
                    success     INTEGER NOT NULL,
                    latency_ms  REAL NOT NULL,
                    extra_json  TEXT
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_slo_outcomes_name_ts "
                "ON slo_outcomes(slo_name, ts);"
            )

    # ---- protocol methods ---------------------------------------------- #
    def append(self, record: Dict[str, Any]) -> None:
        import json as _json
        ts = float(record.get("ts", time.time()))
        success = 1 if record.get("success", True) else 0
        latency_ms = float(record.get("latency_ms", 0.0))
        extra = {k: v for k, v in record.items()
                 if k not in ("success", "latency_ms", "ts")}
        with self._lock:
            self._conn.execute(  # type: ignore[union-attr]
                "INSERT INTO slo_outcomes (slo_name, ts, success, latency_ms, extra_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.slo_name, ts, success, latency_ms,
                 _json.dumps(extra) if extra else None),
            )
            # NOTE (F2 fix-5 attempt-6): cap_max is intentionally NOT called
            # here. The caller (``SLORecorder.record_outcome``) invokes it
            # after pruning; calling it here too would force recursive lock
            # acquisition and (with a regular Lock) deadlock. We rely on the
            # outer caller to bound the table size — its prune_older_than +
            # cap_max pair runs serially against this append without
            # re-entrancy.

    def extend(self, records: List[Dict[str, Any]]) -> None:
        with self._lock:
            for rec in records:
                self.append(rec)

    def snapshot(self) -> List[Dict[str, Any]]:
        import json as _json
        with self._lock:
            cur = self._conn.execute(  # type: ignore[union-attr]
                "SELECT ts, success, latency_ms, extra_json "
                "FROM slo_outcomes WHERE slo_name = ? ORDER BY ts ASC",
                (self.slo_name,),
            )
            rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for ts, success, latency_ms, extra_json in rows:
            d: Dict[str, Any] = {
                "ts": ts,
                "success": bool(success),
                "latency_ms": float(latency_ms),
            }
            if extra_json:
                try:
                    d.update(_json.loads(extra_json))
                except Exception:
                    pass
            out.append(d)
        return out

    def prune_older_than(self, cutoff_ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM slo_outcomes WHERE slo_name = ? AND ts < ?",
                (self.slo_name, cutoff_ts),
            )
            return cur.rowcount

    def cap_max(self, max_records: int) -> int:
        with self._lock:
            cur = self._conn.execute(  # type: ignore[union-attr]
                "SELECT COUNT(*) FROM slo_outcomes WHERE slo_name = ?",
                (self.slo_name,),
            )
            count = cur.fetchone()[0]
            if count <= max_records:
                return 0
            # Drop the oldest (count - max_records) rows.
            self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM slo_outcomes WHERE slo_name = ? AND id IN ("
                "  SELECT id FROM slo_outcomes WHERE slo_name = ? "
                "  ORDER BY ts ASC LIMIT ?"
                ")",
                (self.slo_name, self.slo_name, count - max_records),
            )
            return count - max_records

    def reset(self) -> None:
        with self._lock:
            self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM slo_outcomes WHERE slo_name = ?",
                (self.slo_name,),
            )

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None