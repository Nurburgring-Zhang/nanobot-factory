"""P4-3-W2: MemoryPalace — SQLite persistence + facade.

The 5 tables are intentionally simple (no foreign-key cascades, no
transactions across tables) so that the whole module works against a
plain SQLite file (the ``imdf`` data dir, or a per-test tmp file when
``reset_memory_palace_for_test`` is called).

The facade is the only entry point; the dataclasses in ``levels.py`` are
immutable view objects.  Every CRUD method returns a dataclass — never a
bare dict — so callers can rely on the schema.

Backed by SQLite (always) for now; if a real Postgres deployment is
required later, swap :meth:`MemoryPalace._connect` for a SQLAlchemy
session — the SQL is plain SQL/JSON, so the migration is mechanical.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .levels import (
    DrawerRecord,
    ItemRecord,
    MemoryLevel,
    RoomRecord,
    TunnelRecord,
    WingRecord,
)

logger = logging.getLogger(__name__)


# ── DDL (one-shot, idempotent) ───────────────────────────────────────────────
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS memory_wings (
        wing_id        TEXT PRIMARY KEY,
        name           TEXT NOT NULL,
        description    TEXT NOT NULL DEFAULT '',
        trigger_kw     TEXT NOT NULL DEFAULT '[]',
        created_at     REAL NOT NULL,
        updated_at     REAL NOT NULL,
        metadata       TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_rooms (
        room_id        TEXT PRIMARY KEY,
        wing_id        TEXT NOT NULL,
        title          TEXT NOT NULL,
        summary        TEXT NOT NULL DEFAULT '',
        status         TEXT NOT NULL DEFAULT 'active',
        created_at     REAL NOT NULL,
        updated_at     REAL NOT NULL,
        metadata       TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_memory_rooms_wing ON memory_rooms(wing_id)",
    "CREATE INDEX IF NOT EXISTS ix_memory_rooms_status ON memory_rooms(status)",
    """
    CREATE TABLE IF NOT EXISTS memory_drawers (
        drawer_id      TEXT PRIMARY KEY,
        room_id        TEXT NOT NULL,
        title          TEXT NOT NULL,
        content        TEXT NOT NULL DEFAULT '',
        content_type   TEXT NOT NULL DEFAULT 'text',
        uri            TEXT NOT NULL DEFAULT '',
        created_at     REAL NOT NULL,
        updated_at     REAL NOT NULL,
        metadata       TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_memory_drawers_room ON memory_drawers(room_id)",
    """
    CREATE TABLE IF NOT EXISTS memory_tunnels (
        tunnel_id      TEXT PRIMARY KEY,
        from_id        TEXT NOT NULL,
        from_kind      TEXT NOT NULL,
        to_id          TEXT NOT NULL,
        to_kind        TEXT NOT NULL,
        relation       TEXT NOT NULL DEFAULT 'related',
        note           TEXT NOT NULL DEFAULT '',
        created_at     REAL NOT NULL,
        metadata       TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_memory_tunnels_from ON memory_tunnels(from_id)",
    "CREATE INDEX IF NOT EXISTS ix_memory_tunnels_to ON memory_tunnels(to_id)",
    """
    CREATE TABLE IF NOT EXISTS memory_items (
        item_id        TEXT PRIMARY KEY,
        level          TEXT NOT NULL,
        parent_id      TEXT NOT NULL,
        content        TEXT NOT NULL,
        role           TEXT NOT NULL DEFAULT 'user',
        created_at     REAL NOT NULL,
        metadata       TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_memory_items_level ON memory_items(level)",
    "CREATE INDEX IF NOT EXISTS ix_memory_items_parent ON memory_items(parent_id)",
]


def _row_to_wing(row: sqlite3.Row) -> WingRecord:
    return WingRecord(
        wing_id=row["wing_id"],
        name=row["name"],
        description=row["description"],
        trigger_keywords=json.loads(row["trigger_kw"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _row_to_room(row: sqlite3.Row) -> RoomRecord:
    return RoomRecord(
        room_id=row["room_id"],
        wing_id=row["wing_id"],
        title=row["title"],
        summary=row["summary"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _row_to_drawer(row: sqlite3.Row) -> DrawerRecord:
    return DrawerRecord(
        drawer_id=row["drawer_id"],
        room_id=row["room_id"],
        title=row["title"],
        content=row["content"],
        content_type=row["content_type"],
        uri=row["uri"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _row_to_tunnel(row: sqlite3.Row) -> TunnelRecord:
    return TunnelRecord(
        tunnel_id=row["tunnel_id"],
        from_id=row["from_id"],
        from_kind=row["from_kind"],
        to_id=row["to_id"],
        to_kind=row["to_kind"],
        relation=row["relation"],
        note=row["note"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _row_to_item(row: sqlite3.Row) -> ItemRecord:
    return ItemRecord(
        item_id=row["item_id"],
        level=row["level"],
        parent_id=row["parent_id"],
        content=row["content"],
        role=row["role"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


# ── Facade ───────────────────────────────────────────────────────────────────
class MemoryPalace:
    """The MemoryPalace facade.  Use :func:`get_memory_palace` for the
    module-level singleton (or instantiate directly with a custom db_path
    in tests)."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        if db_path:
            self._init_db(db_path)
        else:
            # Use a shared in-memory URI so the DDL survives across
            # short-lived connections (sqlite3 default opens a fresh
            # in-memory DB per connection otherwise).
            self._db_path = "file::memory:?cache=shared"
        self._init_db(self._db_path)

    # ── DB helpers ──────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        if not path.startswith("file::memory:") and path != ":memory:":
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            except Exception:  # noqa: BLE001
                pass
        with self._connect() as conn:
            for stmt in _DDL:
                conn.execute(stmt)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=30, uri=("file::memory:?cache=shared" in self._db_path))
        conn.row_factory = sqlite3.Row
        # Ensure schema exists for the per-connection ephemeral case
        for stmt in _DDL:
            try:
                conn.execute(stmt)
            except Exception:  # pragma: no cover — DDL is idempotent
                pass
        return conn

    # ── L2 Wings ─────────────────────────────────────────────────────────────
    def create_wing(
        self,
        name: str,
        *,
        description: str = "",
        trigger_keywords: Optional[List[str]] = None,
        wing_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WingRecord:
        wid = wing_id or WingRecord.new_id()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_wings
                  (wing_id, name, description, trigger_kw, created_at, updated_at, metadata)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    wid,
                    name,
                    description,
                    json.dumps(trigger_keywords or [], ensure_ascii=False),
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.get_wing(wid)

    def get_wing(self, wing_id: str) -> Optional[WingRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_wings WHERE wing_id=?", (wing_id,)
            ).fetchone()
        return _row_to_wing(row) if row else None

    def list_wings(self, limit: int = 200) -> List[WingRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_wings ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_row_to_wing(r) for r in rows]

    def update_wing(
        self,
        wing_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_keywords: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[WingRecord]:
        updates: List[str] = []
        params: List[Any] = []
        if name is not None:
            updates.append("name=?")
            params.append(name)
        if description is not None:
            updates.append("description=?")
            params.append(description)
        if trigger_keywords is not None:
            updates.append("trigger_kw=?")
            params.append(json.dumps(trigger_keywords, ensure_ascii=False))
        if metadata is not None:
            updates.append("metadata=?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        if not updates:
            return self.get_wing(wing_id)
        updates.append("updated_at=?")
        params.append(time.time())
        params.append(wing_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE memory_wings SET {', '.join(updates)} WHERE wing_id=?",
                params,
            )
            conn.commit()
        return self.get_wing(wing_id)

    def delete_wing(self, wing_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_wings WHERE wing_id=?", (wing_id,))
            conn.commit()
        return cur.rowcount > 0

    # ── L3 Rooms ─────────────────────────────────────────────────────────────
    def create_room(
        self,
        wing_id: str,
        title: str,
        *,
        summary: str = "",
        status: str = "active",
        room_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoomRecord:
        rid = room_id or RoomRecord.new_id()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_rooms
                  (room_id, wing_id, title, summary, status, created_at, updated_at, metadata)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    rid,
                    wing_id,
                    title,
                    summary,
                    status,
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.get_room(rid)

    def get_room(self, room_id: str) -> Optional[RoomRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_rooms WHERE room_id=?", (room_id,)
            ).fetchone()
        return _row_to_room(row) if row else None

    def list_rooms(
        self,
        wing_id: Optional[str] = None,
        *,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[RoomRecord]:
        sql = "SELECT * FROM memory_rooms WHERE 1=1"
        params: List[Any] = []
        if wing_id:
            sql += " AND wing_id=?"
            params.append(wing_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_room(r) for r in rows]

    def update_room(
        self,
        room_id: str,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RoomRecord]:
        updates: List[str] = []
        params: List[Any] = []
        if title is not None:
            updates.append("title=?")
            params.append(title)
        if summary is not None:
            updates.append("summary=?")
            params.append(summary)
        if status is not None:
            updates.append("status=?")
            params.append(status)
        if metadata is not None:
            updates.append("metadata=?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        if not updates:
            return self.get_room(room_id)
        updates.append("updated_at=?")
        params.append(time.time())
        params.append(room_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE memory_rooms SET {', '.join(updates)} WHERE room_id=?",
                params,
            )
            conn.commit()
        return self.get_room(room_id)

    def delete_room(self, room_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_rooms WHERE room_id=?", (room_id,))
            conn.commit()
        return cur.rowcount > 0

    # ── L4 Drawers ───────────────────────────────────────────────────────────
    def create_drawer(
        self,
        room_id: str,
        title: str,
        *,
        content: str = "",
        content_type: str = "text",
        uri: str = "",
        drawer_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DrawerRecord:
        did = drawer_id or DrawerRecord.new_id()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_drawers
                  (drawer_id, room_id, title, content, content_type, uri,
                   created_at, updated_at, metadata)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    did,
                    room_id,
                    title,
                    content,
                    content_type,
                    uri,
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.get_drawer(did)

    def get_drawer(self, drawer_id: str) -> Optional[DrawerRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_drawers WHERE drawer_id=?", (drawer_id,)
            ).fetchone()
        return _row_to_drawer(row) if row else None

    def list_drawers(self, room_id: Optional[str] = None, limit: int = 500) -> List[DrawerRecord]:
        sql = "SELECT * FROM memory_drawers WHERE 1=1"
        params: List[Any] = []
        if room_id:
            sql += " AND room_id=?"
            params.append(room_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_drawer(r) for r in rows]

    def update_drawer(
        self,
        drawer_id: str,
        *,
        title: Optional[str] = None,
        content: Optional[str] = None,
        content_type: Optional[str] = None,
        uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DrawerRecord]:
        updates: List[str] = []
        params: List[Any] = []
        if title is not None:
            updates.append("title=?")
            params.append(title)
        if content is not None:
            updates.append("content=?")
            params.append(content)
        if content_type is not None:
            updates.append("content_type=?")
            params.append(content_type)
        if uri is not None:
            updates.append("uri=?")
            params.append(uri)
        if metadata is not None:
            updates.append("metadata=?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        if not updates:
            return self.get_drawer(drawer_id)
        updates.append("updated_at=?")
        params.append(time.time())
        params.append(drawer_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE memory_drawers SET {', '.join(updates)} WHERE drawer_id=?",
                params,
            )
            conn.commit()
        return self.get_drawer(drawer_id)

    def delete_drawer(self, drawer_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_drawers WHERE drawer_id=?", (drawer_id,))
            conn.commit()
        return cur.rowcount > 0

    # ── L5 Tunnels ───────────────────────────────────────────────────────────
    def create_tunnel(
        self,
        from_id: str,
        to_id: str,
        *,
        from_kind: str = "wing",
        to_kind: str = "wing",
        relation: str = "related",
        note: str = "",
        tunnel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TunnelRecord:
        tid = tunnel_id or TunnelRecord.new_id()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_tunnels
                  (tunnel_id, from_id, from_kind, to_id, to_kind, relation,
                   note, created_at, metadata)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    from_id,
                    from_kind,
                    to_id,
                    to_kind,
                    relation,
                    note,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.get_tunnel(tid)

    def get_tunnel(self, tunnel_id: str) -> Optional[TunnelRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_tunnels WHERE tunnel_id=?", (tunnel_id,)
            ).fetchone()
        return _row_to_tunnel(row) if row else None

    def list_tunnels(
        self,
        anchor_id: Optional[str] = None,
        *,
        limit: int = 200,
    ) -> List[TunnelRecord]:
        sql = "SELECT * FROM memory_tunnels WHERE 1=1"
        params: List[Any] = []
        if anchor_id:
            sql += " AND (from_id=? OR to_id=?)"
            params.extend([anchor_id, anchor_id])
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_tunnel(r) for r in rows]

    def delete_tunnel(self, tunnel_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_tunnels WHERE tunnel_id=?", (tunnel_id,))
            conn.commit()
        return cur.rowcount > 0

    # ── Free-form Items (L0 / L1 / L3 verbatim) ─────────────────────────────
    def create_item(
        self,
        level: str,
        parent_id: str,
        content: str,
        *,
        role: str = "user",
        item_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ItemRecord:
        iid = item_id or ItemRecord.new_id()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_items
                  (item_id, level, parent_id, content, role, created_at, metadata)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    iid,
                    level,
                    parent_id,
                    content,
                    role,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return self.get_item(iid)

    def get_item(self, item_id: str) -> Optional[ItemRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE item_id=?", (item_id,)
            ).fetchone()
        return _row_to_item(row) if row else None

    def list_items(
        self,
        level: Optional[str] = None,
        parent_id: Optional[str] = None,
        *,
        limit: int = 500,
    ) -> List[ItemRecord]:
        sql = "SELECT * FROM memory_items WHERE 1=1"
        params: List[Any] = []
        if level:
            sql += " AND level=?"
            params.append(level)
        if parent_id:
            sql += " AND parent_id=?"
            params.append(parent_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def search_items(
        self,
        query: str,
        *,
        level: Optional[str] = None,
        limit: int = 50,
    ) -> List[ItemRecord]:
        """Naive LIKE-based search; adequate for tests, swap for FTS5 in prod."""
        if not query:
            return []
        sql = "SELECT * FROM memory_items WHERE content LIKE ?"
        params: List[Any] = [f"%{query}%"]
        if level:
            sql += " AND level=?"
            params.append(level)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def delete_item(self, item_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_items WHERE item_id=?", (item_id,))
            conn.commit()
        return cur.rowcount > 0

    # ── Diagnostics ──────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, int]:
        """Return per-table counts — useful for /healthz and tests."""
        out: Dict[str, int] = {}
        with self._connect() as conn:
            for tbl in (
                "memory_wings",
                "memory_rooms",
                "memory_drawers",
                "memory_tunnels",
                "memory_items",
            ):
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {tbl}").fetchone()
                out[tbl] = int(row["n"])
        return out


# ── Module-level singleton ──────────────────────────────────────────────────
_palace: Optional[MemoryPalace] = None
_palace_lock = threading.Lock()


def get_memory_palace(db_path: Optional[str] = None) -> MemoryPalace:
    """Lazy-init the singleton (so TestClient doesn't need a real DB).

    If ``db_path`` is given AND the singleton hasn't been built yet, it
    is created with that db_path.  Subsequent calls with a different
    db_path are ignored (singleton wins).  Use
    :func:`reset_memory_palace_for_test` to force a rebuild.
    """
    global _palace
    with _palace_lock:
        if _palace is None:
            if db_path is None:
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    db_path = os.path.join(env, "memory_palace.db")
            _palace = MemoryPalace(db_path=db_path)
        return _palace


def reset_memory_palace_for_test(db_path: Optional[str] = None) -> MemoryPalace:
    """Force a fresh singleton (used by TestClient fixtures)."""
    global _palace
    with _palace_lock:
        _palace = MemoryPalace(db_path=db_path)
        return _palace


__all__ = [
    "MemoryPalace",
    "get_memory_palace",
    "reset_memory_palace_for_test",
]
