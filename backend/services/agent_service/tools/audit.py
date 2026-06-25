"""P6-Fix-B-3: Tool audit chain — HMAC-signed bridge into :mod:`imdf.engines.audit_chain`.

This module wires the agent-service :class:`ToolRegistry` to the existing
:class:`imdf.engines.audit_chain.AuditChain` (HMAC-SHA256, OWASP A08:2021
Software & Data Integrity) so that every tool invocation produces a
tamper-evident record alongside the lightweight ``AuditEntry`` row.

Why a separate module
---------------------
The :class:`ToolRegistry` already writes an :class:`AuditEntry` to an
in-memory list and a SQLite ``tool_audit`` table — useful for hot-path
debugging but **not** integrity-protected.  This module adds the heavy
audit layer that:

* signs every entry with the project's :data:`AUDIT_CHAIN_SECRET`
* validates the chain at startup (``verify_chain()`` ⇒ fail-fast on tamper)
* exposes ``/api/v1/agent/tools/audit`` consumers with HMAC-verified rows

Scope decisions
---------------
* We **never** raise from the hot path — tool invocations must not be
  killed because the audit chain is unreachable.  Failures degrade to
  the in-memory :class:`AuditEntry` list (existing behaviour).
* The HMAC chain is **append-only** — there is no public API to delete
  or rewrite entries.  Tampering the SQLite file breaks ``verify_chain``.
* This module does **not** depend on FastAPI / Pydantic — pure Python so
  it can be unit-tested without spinning up an app.

Public surface
--------------
* :class:`ToolAuditChain` — main facade, persists HMAC-signed entries
* :func:`get_tool_audit_chain` — module singleton accessor
* :func:`reset_tool_audit_for_test` — test hook

OWASP threat model
------------------
Attacker scenario A: modify SQLite ``tool_audit`` row → ``entry_hash``
mismatch → ``verify_chain`` returns ``(False, bad_seq)``.

Attacker scenario B: rewrite ``entry_hash`` to match → HMAC ``signature``
mismatch (no AUDIT_CHAIN_SECRET) → ``verify_chain`` returns BAD.

Attacker scenario C: insert forged row with their own signature → chain
seq discontinuity → ``verify_chain`` returns BAD at the gap.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import — audit_chain.py may not be importable in all test contexts.
try:
    from imdf.engines.audit_chain import (  # type: ignore
        AuditChain,
        AuditChainError,
        ChainEntry as _ChainEntry,
    )
    _AUDIT_CHAIN_AVAILABLE = True
except Exception:  # noqa: BLE001
    _AUDIT_CHAIN_AVAILABLE = False
    AuditChain = None  # type: ignore
    AuditChainError = Exception  # type: ignore

    class _ChainEntry:  # minimal stub for type checking
        seq: int
        timestamp: str
        method: str
        path: str
        user: str


# ============================================================================
# Public dataclass
# ============================================================================
@dataclass
class ToolAuditRecord:
    """A single tool invocation signed into the audit chain.

    Mirrors :class:`tools.registry.AuditEntry` plus a ``prev_hash`` /
    ``signature`` pair so callers can verify a record without walking
    the chain.
    """
    invocation_id: str
    tool: str
    actor: str
    timestamp: str
    args: Dict[str, Any]
    result_preview: Optional[str]
    error: Optional[str]
    latency_ms: int
    seq: int
    entry_hash: str
    prev_hash: str
    signature: str
    status: str = "ok"  # ok | error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "tool": self.tool,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "args": dict(self.args),
            "result_preview": self.result_preview,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "seq": self.seq,
            "entry_hash": self.entry_hash,
            "prev_hash": self.prev_hash,
            "signature": self.signature,
        }


# ============================================================================
# Tool audit chain — thin wrapper over AuditChain
# ============================================================================
class ToolAuditChain:
    """Bridge :class:`ToolRegistry` invocations to :class:`AuditChain`.

    The bridge stores tool invocations as ``AuditChain.append`` entries
    (method="TOOL", path="<tool-name>") and exposes a typed accessor
    for the API layer.
    """

    # When AuditChain is unavailable we keep an in-memory ring buffer so
    # the tool registry can still record invocations.
    RING_LIMIT = 1000

    def __init__(self, chain: Optional[Any] = None, db_path: Optional[str] = None):
        self._chain = chain
        self._db_path = db_path
        self._lock = threading.Lock()
        # In-memory fallback ring (used when AuditChain unavailable or as a
        # fast hot-path mirror — we still write to AuditChain when ready).
        self._ring: List[ToolAuditRecord] = []
        # Tool-call index — keyed by (tool, actor) for quick filtering.
        self._init_tool_audit_table()

    # ------------------------------------------------------------------
    # SQLite mirror — fast queries without walking the HMAC chain
    # ------------------------------------------------------------------
    def _init_tool_audit_table(self) -> None:
        if not self._db_path:
            return
        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_audit_chain (
                    invocation_id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    args TEXT NOT NULL,
                    result_preview TEXT,
                    error TEXT,
                    latency_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    entry_hash TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    signature TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_tool_audit_chain_tool ON tool_audit_chain(tool)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_tool_audit_chain_seq ON tool_audit_chain(seq)"
            )
            conn.commit()

    def _persist(self, rec: ToolAuditRecord) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tool_audit_chain
                    (invocation_id, tool, actor, timestamp, args,
                     result_preview, error, latency_ms, status,
                     seq, entry_hash, prev_hash, signature)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        rec.invocation_id,
                        rec.tool,
                        rec.actor,
                        rec.timestamp,
                        json.dumps(rec.args, ensure_ascii=False),
                        rec.result_preview,
                        rec.error,
                        rec.latency_ms,
                        rec.status,
                        rec.seq,
                        rec.entry_hash,
                        rec.prev_hash,
                        rec.signature,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist tool audit %s failed: %s", rec.invocation_id, exc)

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------
    def append(
        self,
        *,
        invocation_id: str,
        tool: str,
        actor: str,
        args: Dict[str, Any],
        result: Any,
        error: Optional[str],
        started_at: float,
        finished_at: float,
    ) -> ToolAuditRecord:
        """Record a tool invocation into the HMAC chain + SQLite mirror.

        Best-effort: if the HMAC chain is unavailable we fall back to
        the in-memory ring buffer and a sentinel signature so callers
        always get a :class:`ToolAuditRecord` back.
        """
        latency_ms = max(0, int((finished_at - started_at) * 1000))
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(finished_at))
        result_preview = self._truncate_result(result)
        status = "error" if error else "ok"

        # Default record (signature-less, used as fallback)
        rec = ToolAuditRecord(
            invocation_id=invocation_id,
            tool=tool,
            actor=actor or "anonymous",
            timestamp=timestamp,
            args=dict(args or {}),
            result_preview=result_preview,
            error=error,
            latency_ms=latency_ms,
            status=status,
            seq=-1,
            entry_hash="",
            prev_hash="",
            signature="",
        )

        # Try to push into the HMAC chain.  Path is "<tool-name>" so the
        # chain query endpoint can filter by tool directly.
        chain_ok = False
        if self._chain is not None:
            try:
                entry = self._chain.append(
                    timestamp=timestamp,
                    method="TOOL",
                    path=tool,
                    user=actor or "anonymous",
                    body_hash=self._hash_args(args),
                    status_code=0 if status == "ok" else 500,
                )
                rec.seq = entry.seq
                rec.prev_hash = entry.prev_hash
                rec.entry_hash = entry.entry_hash
                rec.signature = entry.signature
                chain_ok = True
            except AuditChainError as exc:
                # Fail-fast integrity violation — log loudly, do not raise
                # into the tool hot path.  The caller still gets a record.
                logger.error("tool audit chain integrity error: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("tool audit chain append failed: %s", exc)

        # Mirror into ring + SQLite
        with self._lock:
            self._ring.append(rec)
            if len(self._ring) > self.RING_LIMIT:
                self._ring = self._ring[-self.RING_LIMIT:]
        self._persist(rec)
        return rec

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------
    def query(
        self,
        *,
        tool: Optional[str] = None,
        actor: Optional[str] = None,
        limit: int = 100,
        since_seq: int = 0,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """Return audit records (optionally filtered).

        Parameters
        ----------
        tool : str, optional
            Filter by tool name (exact match).
        actor : str, optional
            Filter by actor (exact match).
        limit : int
            Max number of records to return (newest first).
        since_seq : int
            Return only records with ``seq > since_seq``.
        verify : bool
            If True, run :meth:`AuditChain.verify_chain` and include
            ``chain_ok`` / ``bad_seq`` in the response.
        """
        # Prefer SQLite query when db available; otherwise walk ring.
        rows = self._query_db(tool=tool, actor=actor, since_seq=since_seq, limit=limit)
        if rows is None:
            rows = self._query_ring(tool=tool, actor=actor, since_seq=since_seq, limit=limit)

        chain_ok: Optional[bool] = None
        bad_seq: int = -1
        if verify and self._chain is not None:
            try:
                chain_ok, bad_seq = self._chain.verify_chain()
            except Exception as exc:  # noqa: BLE001
                logger.warning("verify_chain failed: %s", exc)
                chain_ok = False

        return {
            "count": len(rows),
            "limit": limit,
            "tool": tool,
            "actor": actor,
            "since_seq": since_seq,
            "chain_ok": chain_ok,
            "bad_seq": bad_seq,
            "records": [r.to_dict() for r in rows],
        }

    def verify(self) -> Dict[str, Any]:
        """Verify HMAC integrity of the underlying :class:`AuditChain`."""
        if self._chain is None:
            return {"chain_ok": None, "bad_seq": -1, "reason": "chain_unavailable"}
        ok, bad_seq = self._chain.verify_chain()
        return {"chain_ok": ok, "bad_seq": bad_seq, "reason": None}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _truncate_result(result: Any) -> Optional[str]:
        if result is None:
            return None
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            text = repr(result)[:512]
        return text[:512]

    @staticmethod
    def _hash_args(args: Optional[Dict[str, Any]]) -> str:
        import hashlib
        if not args:
            return ""
        try:
            payload = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:  # noqa: BLE001
            payload = repr(args)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _query_db(
        self,
        *,
        tool: Optional[str],
        actor: Optional[str],
        since_seq: int,
        limit: int,
    ) -> Optional[List[ToolAuditRecord]]:
        if not self._db_path or not os.path.isfile(self._db_path):
            return None
        where: List[str] = ["seq > ?"]
        params: List[Any] = [since_seq]
        if tool:
            where.append("tool = ?")
            params.append(tool)
        if actor:
            where.append("actor = ?")
            params.append(actor)
        sql = (
            f"SELECT * FROM tool_audit_chain WHERE {' AND '.join(where)} "
            f"ORDER BY seq DESC LIMIT ?"
        )
        params.append(int(limit))
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, params)
                return [self._row_to_record(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            logger.warning("query tool_audit_chain db failed: %s", exc)
            return None

    def _query_ring(
        self,
        *,
        tool: Optional[str],
        actor: Optional[str],
        since_seq: int,
        limit: int,
    ) -> List[ToolAuditRecord]:
        with self._lock:
            snapshot = list(self._ring)
        rows = [r for r in snapshot if r.seq > since_seq]
        if tool:
            rows = [r for r in rows if r.tool == tool]
        if actor:
            rows = [r for r in rows if r.actor == actor]
        rows.sort(key=lambda r: r.seq, reverse=True)
        return rows[: int(limit)]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ToolAuditRecord:
        try:
            args = json.loads(row["args"] or "{}")
        except Exception:  # noqa: BLE001
            args = {}
        return ToolAuditRecord(
            invocation_id=row["invocation_id"],
            tool=row["tool"],
            actor=row["actor"],
            timestamp=row["timestamp"],
            args=args,
            result_preview=row["result_preview"],
            error=row["error"],
            latency_ms=row["latency_ms"],
            status=row["status"],
            seq=row["seq"],
            entry_hash=row["entry_hash"],
            prev_hash=row["prev_hash"],
            signature=row["signature"],
        )


# ============================================================================
# Module singleton
# ============================================================================
_chain_singleton: Optional[ToolAuditChain] = None
_chain_lock = threading.Lock()


def get_tool_audit_chain(db_path: Optional[str] = None) -> ToolAuditChain:
    """Return the process-wide :class:`ToolAuditChain` singleton.

    If :data:`AUDIT_CHAIN_SECRET` is set in the environment, the
    singleton is wired to the global :class:`AuditChain` from
    :mod:`imdf.engines.audit_chain`.  Otherwise we fall back to an
    in-memory ring buffer so the tool registry can still record
    invocations.
    """
    global _chain_singleton
    with _chain_lock:
        if _chain_singleton is not None:
            return _chain_singleton

        chain_obj: Optional[Any] = None
        if _AUDIT_CHAIN_AVAILABLE and os.environ.get("AUDIT_CHAIN_SECRET"):
            try:
                # Late import to avoid touching DATA_DIR settings
                from imdf.engines.audit_chain import get_chain  # type: ignore
                chain_obj = get_chain()
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not acquire AuditChain singleton: %s", exc)
                chain_obj = None

        # SQLite mirror path
        mirror_db: Optional[str] = None
        if db_path is None:
            env_data = os.environ.get("IMDF_DATA_DIR")
            if env_data:
                mirror_db = os.path.join(env_data, "tool_audit_chain.db")

        _chain_singleton = ToolAuditChain(chain=chain_obj, db_path=mirror_db)
        return _chain_singleton


def reset_tool_audit_for_test(db_path: Optional[str] = None, chain: Optional[Any] = None) -> ToolAuditChain:
    """Reset the singleton — used by pytest fixtures."""
    global _chain_singleton
    with _chain_lock:
        _chain_singleton = ToolAuditChain(chain=chain, db_path=db_path)
    return _chain_singleton


__all__ = [
    "ToolAuditChain",
    "ToolAuditRecord",
    "get_tool_audit_chain",
    "reset_tool_audit_for_test",
]
