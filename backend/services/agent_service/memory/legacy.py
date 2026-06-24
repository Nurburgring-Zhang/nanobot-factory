"""P3-3-W1: Agent memory — short-term + long-term.

Two tiers of memory:

* **Short-term** (in-process dict, optional TTL) — used while a task is being
  planned / executed.  Cleared when the task terminates.

* **Long-term** (SQLite-backed key/value store) — survives across task
  lifecycles and processes.  Used to remember user preferences, recurring
  patterns, and curated context that the next agent run should pick up.

The Agent dispatch framework calls into :func:`remember` /
:func:`recall` from any of the 15 agent implementations.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Short-term memory ────────────────────────────────────────────────────────
@dataclass
class ShortTermEntry:
    """One in-process memory record."""

    key: str
    value: Any
    owner: str = "global"          # task_id or 'global'
    created_at: float = field(default_factory=time.time)
    ttl_seconds: Optional[int] = None

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds


class ShortTermMemory:
    """In-process LRU-ish dict; entries auto-expire on access."""

    def __init__(self, default_ttl: Optional[int] = 3600) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, ShortTermEntry] = {}
        self._default_ttl = default_ttl

    def set(
        self,
        key: str,
        value: Any,
        *,
        owner: str = "global",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        with self._lock:
            self._entries[key] = ShortTermEntry(
                key=key, value=value, owner=owner, ttl_seconds=ttl
            )

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            if entry.is_expired():
                del self._entries[key]
                return None
            return entry.value

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def list(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._entries.values())
        if owner is not None:
            items = [e for e in items if e.owner == owner]
        # Drop expired
        items = [e for e in items if not e.is_expired()]
        return [
            {
                "key": e.key,
                "value": e.value,
                "owner": e.owner,
                "created_at": e.created_at,
                "ttl_seconds": e.ttl_seconds,
            }
            for e in items
        ]

    def clear(self, owner: Optional[str] = None) -> int:
        with self._lock:
            if owner is None:
                n = len(self._entries)
                self._entries.clear()
                return n
            keys = [k for k, v in self._entries.items() if v.owner == owner]
            for k in keys:
                del self._entries[k]
            return len(keys)

    def reset_for_test(self) -> None:
        with self._lock:
            self._entries.clear()


# ── Long-term memory (SQLite) ────────────────────────────────────────────────
class LongTermMemory:
    """SQLite-backed key/value memory.

    The schema is intentionally simple — one row per (scope, key) pair.
    ``value`` is stored as JSON text.  ``scope`` lets us partition
    memories by user / project / agent_type.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path
        if db_path:
            self._init_db(db_path)

    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_memory_scope_key "
                "ON agent_memory(scope, key)"
            )
            conn.commit()

    def upsert(self, scope: str, key: str, value: Any) -> str:
        if not self._db_path:
            logger.debug("long-term memory has no db_path; upsert is a no-op")
            return f"mem-{uuid.uuid4().hex[:12]}"
        now = time.time()
        existing = self._get(scope, key)
        if existing:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE agent_memory SET value=?, updated_at=? WHERE id=?",
                    (json.dumps(value, ensure_ascii=False), now, existing["id"]),
                )
                conn.commit()
            return existing["id"]
        new_id = f"mem-{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO agent_memory (id, scope, key, value, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (new_id, scope, key, json.dumps(value, ensure_ascii=False), now, now),
            )
            conn.commit()
        return new_id

    def get(self, scope: str, key: str) -> Optional[Any]:
        rec = self._get(scope, key)
        if not rec:
            return None
        try:
            return json.loads(rec["value"])
        except Exception:  # noqa: BLE001
            return rec["value"]

    def _get(self, scope: str, key: str) -> Optional[Dict[str, Any]]:
        if not self._db_path:
            return None
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, value FROM agent_memory WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "value": row[1]}

    def list(self, scope: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._db_path:
            return []
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, scope, key, value, created_at, updated_at "
                "FROM agent_memory WHERE scope=? ORDER BY updated_at DESC LIMIT ?",
                (scope, int(limit)),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                val = json.loads(r[3])
            except Exception:  # noqa: BLE001
                val = r[3]
            out.append(
                {
                    "id": r[0],
                    "scope": r[1],
                    "key": r[2],
                    "value": val,
                    "created_at": r[4],
                    "updated_at": r[5],
                }
            )
        return out

    def delete(self, scope: str, key: str) -> bool:
        if not self._db_path:
            return False
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "DELETE FROM agent_memory WHERE scope=? AND key=?",
                (scope, key),
            )
            conn.commit()
        return cur.rowcount > 0


# ── Module-level singletons ──────────────────────────────────────────────────
_short: Optional[ShortTermMemory] = None
_long: Optional[LongTermMemory] = None
_mem_lock = threading.Lock()


def get_short_term() -> ShortTermMemory:
    global _short
    with _mem_lock:
        if _short is None:
            _short = ShortTermMemory()
        return _short


def get_long_term() -> LongTermMemory:
    global _long
    with _mem_lock:
        if _long is None:
            db_path = None
            env = os.environ.get("IMDF_DATA_DIR")
            if env:
                db_path = os.path.join(env, "agent_memory.db")
            _long = LongTermMemory(db_path=db_path)
        return _long


def reset_memory_for_test() -> None:
    global _short, _long
    with _mem_lock:
        _short = None
        _long = None


# ── Convenience helpers used by the 15 agent implementations ─────────────────
def remember(scope: str, key: str, value: Any) -> str:
    """Write a long-term memory record.  Returns the memory id."""
    return get_long_term().upsert(scope, key, value)


def recall(scope: str, key: str) -> Optional[Any]:
    """Read a long-term memory record (returns ``None`` if missing)."""
    return get_long_term().get(scope, key)


__all__ = [
    "ShortTermMemory",
    "LongTermMemory",
    "ShortTermEntry",
    "get_short_term",
    "get_long_term",
    "reset_memory_for_test",
    "remember",
    "recall",
]
