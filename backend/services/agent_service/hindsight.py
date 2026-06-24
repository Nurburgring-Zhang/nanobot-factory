"""P4-3-W2: Hindsight — verbatim long-term memory with 4-layer stack.

Inspired by the Hermes Hindsight design, this module gives the agent
**lossless, verbatim** storage of everything it sees / says, organised
into four retrieval layers:

  L0  Identity          — SOUL.md / user identity (immutable for a session)
  L1  Essential Story   — project-level core info (compressible)
  L2  Wing trigger      — light-weight keyword trigger (matches 1 wing)
  L3  Full semantic     — vector / full-text search of the verbatim log

The four layers are accessed through a single facade,
:class:`HindsightMemory`, so callers don't need to know which layer their
query hit.

Design points (the Hermes "verbatim" discipline):

  1. **Verbatim** — we never summarise / rewrite what the user or the
     agent said.  We always store the *raw* text (plus optional metadata
     for the user_name / timestamp / source).
  2. **Lazy L1 compression** — L1 entries are *generated* from L3 by an
     LLM; the LLM never mutates the source L3 entry, so the verbatim
     property survives.
  3. **Pluggable backends** — the vector / FTS backend is selected at
     construction time.  Production uses ``pgvector`` (placeholder for
     now; falls back to a SQLite-only exact-match backend when the
     dependency is missing).  Tests use ``sqlite_exact`` to stay
     hermetic.

Public surface:

  * :class:`HindsightMemory`     — facade
  * :class:`HindsightConfig`     — backend selector
  * :class:`MemoryItem`          — verbatim record
  * :func:`get_hindsight`        — module-level singleton accessor
  * :func:`reset_hindsight_for_test`

Integration with vector_retrieval (P3-5) is handled inside the facade —
the ``embed`` hook is provided as a callable; if absent, fallback
embeddings are zero-vectors (search degrades to LIKE / metadata match).
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────────────
class HindsightBackend(str, Enum):
    """Pluggable backends for the L3 vector layer."""

    SQLITE_EXACT = "sqlite_exact"
    PGVECTOR = "pgvector"
    CHROMADB = "chromadb"
    QDRANT = "qdrant"


@dataclass
class HindsightConfig:
    """Hindsight runtime config."""

    backend: HindsightBackend = HindsightBackend.SQLITE_EXACT
    db_path: Optional[str] = None
    # Optional embedder (callable: str -> List[float]).  When None, all
    # search degrades to LIKE / metadata.
    embedder: Optional[Callable[[str], List[float]]] = None
    # Optional LLM callable (str -> str) used for L1 compression.
    llm: Optional[Callable[[str], str]] = None
    # L1 auto-compress threshold (number of L3 items per parent before
    # triggering a compression).
    l1_compress_threshold: int = 20
    # Limit on how many L1 entries to keep.
    l1_max_entries: int = 50


# ── Memory item ──────────────────────────────────────────────────────────────
@dataclass
class MemoryItem:
    """A single verbatim memory record."""

    item_id: str
    layer: str             # "L0_identity" / "L1_essential_story" / "L2_wing" / "L3_full"
    content: str           # verbatim text
    role: str = "user"     # user / system / agent / tool
    source: str = ""       # where this came from (e.g. "session:abc")
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def new_id() -> str:
        return f"mem-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ── DDL ──────────────────────────────────────────────────────────────────────
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS hindsight_items (
        item_id     TEXT PRIMARY KEY,
        layer       TEXT NOT NULL,
        content     TEXT NOT NULL,
        role        TEXT NOT NULL DEFAULT 'user',
        source      TEXT NOT NULL DEFAULT '',
        embedding   TEXT,
        metadata    TEXT NOT NULL DEFAULT '{}',
        created_at  REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_hindsight_layer ON hindsight_items(layer)",
    "CREATE INDEX IF NOT EXISTS ix_hindsight_created ON hindsight_items(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_hindsight_source ON hindsight_items(source)",
    """
    CREATE TABLE IF NOT EXISTS hindsight_l1_story (
        story_id    TEXT PRIMARY KEY,
        parent_id   TEXT NOT NULL,    -- source item_id (L3) that triggered compress
        summary     TEXT NOT NULL,
        metadata    TEXT NOT NULL DEFAULT '{}',
        created_at  REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_hindsight_l1_parent ON hindsight_l1_story(parent_id)",
    """
    CREATE TABLE IF NOT EXISTS hindsight_wings (
        wing_id     TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        trigger_kw  TEXT NOT NULL DEFAULT '[]',
        created_at  REAL NOT NULL,
        metadata    TEXT NOT NULL DEFAULT '{}'
    )
    """,
]


def _row_to_item(row: sqlite3.Row) -> MemoryItem:
    emb_raw = row["embedding"]
    emb: Optional[List[float]] = None
    if emb_raw:
        try:
            emb = json.loads(emb_raw)
        except Exception:  # noqa: BLE001
            emb = None
    return MemoryItem(
        item_id=row["item_id"],
        layer=row["layer"],
        content=row["content"],
        role=row["role"],
        source=row["source"],
        embedding=emb,
        metadata=json.loads(row["metadata"] or "{}"),
        created_at=row["created_at"],
    )


# ── Helpers ──────────────────────────────────────────────────────────────────
def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── HindsightMemory facade ───────────────────────────────────────────────────
class HindsightMemory:
    """The Hindsight facade.  See module docstring for the 4-layer model."""

    def __init__(self, config: Optional[HindsightConfig] = None) -> None:
        self.config = config or HindsightConfig()
        self._lock = threading.RLock()
        if self.config.db_path is None:
            # Shared in-memory URI so the DDL survives short-lived connections.
            self.config.db_path = "file::memory:?cache=shared"
        if not self.config.db_path.startswith("file::memory:") and self.config.db_path != ":memory:":
            try:
                os.makedirs(os.path.dirname(self.config.db_path), exist_ok=True)
            except Exception:  # noqa: BLE001
                pass
        self._init_db()

    # ── DB ──────────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        uri = "file::memory:?cache=shared" in (self.config.db_path or "")
        conn = sqlite3.connect(self.config.db_path, check_same_thread=False, timeout=30, uri=uri)
        conn.row_factory = sqlite3.Row
        for stmt in _DDL:
            try:
                conn.execute(stmt)
            except Exception:  # pragma: no cover
                pass
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            for stmt in _DDL:
                conn.execute(stmt)
            conn.commit()

    # ── L0 Identity (immutable within a session) ────────────────────────────
    def retain_identity(self, content: str, *, source: str = "soul", metadata: Optional[Dict[str, Any]] = None) -> MemoryItem:
        """Store an L0 identity record.  Verbatim."""
        return self._retain("L0_identity", content, role="system", source=source, metadata=metadata)

    def list_identity(self, limit: int = 50) -> List[MemoryItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hindsight_items WHERE layer='L0_identity' "
                "ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    # ── L3 Full (verbatim log) ──────────────────────────────────────────────
    def retain(
        self,
        content: str,
        *,
        role: str = "user",
        source: str = "",
        layer: str = "L3_full",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """Store a verbatim L3 record (or any other layer).

        Triggers L1 auto-compression if the L3 log for this source
        crosses the configured threshold.
        """
        item = self._retain(layer, content, role=role, source=source, metadata=metadata)
        if layer == "L3_full":
            self._maybe_compress_l1(source=source)
        return item

    def _retain(
        self,
        layer: str,
        content: str,
        *,
        role: str = "user",
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        iid = MemoryItem.new_id()
        now = time.time()
        emb: Optional[List[float]] = None
        if self.config.embedder is not None:
            try:
                emb = self.config.embedder(content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("embedder failed: %s", exc)
                emb = None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hindsight_items
                  (item_id, layer, content, role, source, embedding, metadata, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    iid,
                    layer,
                    content,
                    role,
                    source,
                    json.dumps(emb) if emb is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        return self.get_item(iid)  # type: ignore[return-value]

    def get_item(self, item_id: str) -> Optional[MemoryItem]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hindsight_items WHERE item_id=?", (item_id,)
            ).fetchone()
        return _row_to_item(row) if row else None

    def list_items(
        self,
        layer: Optional[str] = None,
        source: Optional[str] = None,
        *,
        limit: int = 100,
    ) -> List[MemoryItem]:
        sql = "SELECT * FROM hindsight_items WHERE 1=1"
        params: List[Any] = []
        if layer:
            sql += " AND layer=?"
            params.append(layer)
        if source:
            sql += " AND source=?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def recall(self, item_id: str) -> Optional[MemoryItem]:
        """Get a single item verbatim by id."""
        return self.get_item(item_id)

    # ── L2 Wing trigger (light-weight keyword) ──────────────────────────────
    def register_wing(self, name: str, trigger_keywords: List[str], *, wing_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        wid = wing_id or f"hwing-{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hindsight_wings (wing_id, name, trigger_kw, created_at, metadata)
                VALUES (?,?,?,?,?)
                """,
                (
                    wid,
                    name,
                    json.dumps(trigger_keywords, ensure_ascii=False),
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        return wid

    def trigger_wings(self, text: str) -> List[Dict[str, Any]]:
        """Return the list of wings whose trigger_kw matches the given text.

        Cheap keyword scan, not semantic.  Used to *trigger* deeper search.
        """
        if not text:
            return []
        text_lc = text.lower()
        matched: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM hindsight_wings").fetchall()
        for r in rows:
            kws = json.loads(r["trigger_kw"] or "[]")
            if any((kw or "").lower() in text_lc for kw in kws):
                matched.append(
                    {
                        "wing_id": r["wing_id"],
                        "name": r["name"],
                        "trigger_keywords": kws,
                    }
                )
        return matched

    # ── L1 Essential Story (auto-compress from L3) ──────────────────────────
    def _maybe_compress_l1(self, *, source: str) -> Optional[str]:
        """If L3 log for ``source`` has >= threshold items, ask the LLM
        to summarise the last batch and store as L1.

        Idempotent — only one L1 per (source, batch).  No-op if no LLM
        is configured.
        """
        if self.config.llm is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM hindsight_items WHERE layer='L3_full' AND source=?",
                (source,),
            ).fetchone()
            count = int(row["n"])
        if count < self.config.l1_compress_threshold:
            return None
        if count % self.config.l1_compress_threshold != 0:
            return None
        # Pull the last N items verbatim
        items = self.list_items(layer="L3_full", source=source, limit=self.config.l1_compress_threshold)
        if not items:
            return None
        verbatim = "\n".join(f"[{it.role}] {it.content}" for it in items)
        try:
            summary = self.config.llm(
                f"Compress the following verbatim transcript into a 3-5 sentence "
                f"essential story. Preserve names, decisions, and constraints. "
                f"Output plain text, no preamble.\n\n{verbatim}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("L1 LLM compress failed: %s", exc)
            return None
        # Store as L1 + link to the latest L3 parent
        sid = f"story-{uuid.uuid4().hex[:10]}"
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hindsight_l1_story (story_id, parent_id, summary, metadata, created_at)
                VALUES (?,?,?,?,?)
                """,
                (
                    sid,
                    items[0].item_id,
                    summary,
                    json.dumps({"source": source, "items_compressed": len(items)}),
                    now,
                ),
            )
            conn.commit()
        return sid

    def list_l1_stories(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hindsight_l1_story ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [
            {
                "story_id": r["story_id"],
                "parent_id": r["parent_id"],
                "summary": r["summary"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ── Search (Layer-aware) ────────────────────────────────────────────────
    def search(
        self,
        query: str,
        *,
        layer: Optional[str] = None,
        source: Optional[str] = None,
        k: int = 10,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search the 4-layer stack.

        Strategy (cheap to expensive):

        1. L0 exact substring (highest priority) — only when ``query``
           looks like a key (e.g. ``user_name``).
        2. L2 wing trigger — match the query against registered
           trigger_kw, then pull recent L3 items whose source contains
           the wing.
        3. L1 essential story — substring match in the summary.
        4. L3 verbatim — full substring + (if embedder available)
           cosine re-rank.

        Results are de-duplicated and sorted by score (descending).
        """
        if not query:
            return []
        results: Dict[str, Dict[str, Any]] = {}

        # 1. L0 (always scan)
        if layer is None or layer == "L0_identity":
            for item in self._layer_substring("L0_identity", query, since=since, until=until):
                results[item.item_id] = {
                    "item": item,
                    "score": 1.0,
                    "match_layer": "L0_identity",
                }

        # 2. L2 wing trigger
        if layer is None or layer == "L2_wing":
            for wing in self.trigger_wings(query):
                results[f"wing:{wing['wing_id']}"] = {
                    "wing": wing,
                    "score": 0.85,
                    "match_layer": "L2_wing",
                }

        # 3. L1 essential story
        if layer is None or layer == "L1_essential_story":
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM hindsight_l1_story WHERE summary LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{query}%", int(k)),
                ).fetchall()
            for r in rows:
                results[f"story:{r['story_id']}"] = {
                    "story": {
                        "story_id": r["story_id"],
                        "parent_id": r["parent_id"],
                        "summary": r["summary"],
                        "metadata": json.loads(r["metadata"] or "{}"),
                        "created_at": r["created_at"],
                    },
                    "score": 0.7,
                    "match_layer": "L1_essential_story",
                }

        # 4. L3 verbatim (substring + vector re-rank)
        if layer is None or layer == "L3_full":
            l3 = self._layer_substring("L3_full", query, source=source, since=since, until=until)
            if self.config.embedder is not None:
                try:
                    qv = self.config.embedder(query)
                    for it in l3:
                        if it.embedding:
                            sim = _cosine(qv, it.embedding)
                            results[it.item_id] = {
                                "item": it,
                                "score": max(0.3, sim),
                                "match_layer": "L3_full",
                            }
                        else:
                            results[it.item_id] = {
                                "item": it,
                                "score": 0.4,
                                "match_layer": "L3_full",
                            }
                except Exception as exc:  # noqa: BLE001
                    logger.debug("vector re-rank failed: %s", exc)
                    for it in l3:
                        results[it.item_id] = {
                            "item": it,
                            "score": 0.4,
                            "match_layer": "L3_full",
                        }
            else:
                for it in l3:
                    results[it.item_id] = {
                        "item": it,
                        "score": 0.4,
                        "match_layer": "L3_full",
                    }

        # Rank + truncate
        ranked = sorted(results.values(), key=lambda r: r["score"], reverse=True)
        return ranked[: int(k)]

    def _layer_substring(
        self,
        layer: str,
        query: str,
        *,
        source: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 50,
    ) -> List[MemoryItem]:
        sql = "SELECT * FROM hindsight_items WHERE layer=? AND content LIKE ?"
        params: List[Any] = [layer, f"%{query}%"]
        if source:
            sql += " AND source=?"
            params.append(source)
        if since is not None:
            sql += " AND created_at>=?"
            params.append(float(since))
        if until is not None:
            sql += " AND created_at<=?"
            params.append(float(until))
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    # ── Stats ───────────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"backend": self.config.backend.value}
        with self._connect() as conn:
            for layer in ("L0_identity", "L1_essential_story", "L3_full"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM hindsight_items WHERE layer=?",
                    (layer,),
                ).fetchone()
                out[layer] = int(row["n"])
            row = conn.execute("SELECT COUNT(*) AS n FROM hindsight_l1_story").fetchone()
            out["L1_summaries"] = int(row["n"])
            row = conn.execute("SELECT COUNT(*) AS n FROM hindsight_wings").fetchone()
            out["L2_wings"] = int(row["n"])
        return out

    # ── Wipe ────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Drop all items (used by tests)."""
        with self._lock, self._connect() as conn:
            for tbl in (
                "hindsight_items",
                "hindsight_l1_story",
                "hindsight_wings",
            ):
                conn.execute(f"DELETE FROM {tbl}")
            conn.commit()


# ── Module-level singleton ──────────────────────────────────────────────────
_hindsight: Optional[HindsightMemory] = None
_hindsight_lock = threading.Lock()


def get_hindsight(config: Optional[HindsightConfig] = None) -> HindsightMemory:
    """Lazy-init the singleton (so TestClient doesn't need a real DB)."""
    global _hindsight
    with _hindsight_lock:
        if _hindsight is None:
            if config is None:
                cfg = HindsightConfig()
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    cfg.db_path = os.path.join(env, "hindsight.db")
                config = cfg
            _hindsight = HindsightMemory(config=config)
        return _hindsight


def reset_hindsight_for_test(config: Optional[HindsightConfig] = None) -> HindsightMemory:
    """Force a fresh singleton (used by TestClient fixtures)."""
    global _hindsight
    with _hindsight_lock:
        _hindsight = HindsightMemory(config=config or HindsightConfig())
        return _hindsight


__all__ = [
    "HindsightBackend",
    "HindsightConfig",
    "MemoryItem",
    "HindsightMemory",
    "get_hindsight",
    "reset_hindsight_for_test",
]
