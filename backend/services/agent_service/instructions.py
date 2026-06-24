"""P4-3-W1: Agent Instructions — project-level rule system.

Inspired by Hermes' SOUL.md, AGENTS.md and the prompt-optimizer
``system_prompt`` layer, :class:`AgentInstructions` is a *prioritised*
stack of instruction fragments.  Each fragment is a plain string of
text with optional ``{{template_variables}}`` (resolved by
:mod:`variables`).

Priority (highest first):
    1. ``system``        — built-in defaults baked into the platform.
    2. ``project``       — SOUL.md / AGENTS.md / rules.txt from the
                          repository root.
    3. ``user``          — uploaded by the operator via REST.
    4. ``per_session``   — overrides bound to a specific session id.

When the agent runs a session, the four layers are concatenated (in
priority order) into a single ``system_prompt`` string.  Per-session
overrides can either *append* to or *replace* the merged upstream text
(controlled by ``InstructionFragment.scope_override``).

The set of fragments is mutable via the REST API; in addition the
:class:`loader.Loader` hot-reloads the project-level files when they
change on disk.
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
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Priority / scope enum ────────────────────────────────────────────────────
class InstructionScope(str, Enum):
    """Origin / priority level of an instruction fragment.

    Order matters: lower index = higher priority.  When the merged
    system prompt is built, fragments are concatenated in this order
    so the most "fundamental" rules show up first.
    """

    SYSTEM = "system"          # 1 — platform defaults (e.g. safety rails)
    PROJECT = "project"        # 2 — SOUL.md / AGENTS.md / rules.txt
    USER = "user"              # 3 — operator-uploaded
    PER_SESSION = "per_session"  # 4 — session-scoped override


SCOPE_ORDER: List[InstructionScope] = [
    InstructionScope.SYSTEM,
    InstructionScope.PROJECT,
    InstructionScope.USER,
    InstructionScope.PER_SESSION,
]


# ── Instruction fragment ─────────────────────────────────────────────────────
@dataclass
class InstructionFragment:
    """A single instruction text + metadata."""

    name: str
    content: str
    scope: InstructionScope = InstructionScope.USER
    fragment_id: str = field(default_factory=lambda: f"ins-{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    description: str = ""
    source_path: Optional[str] = None  # file path when loaded from disk
    priority: int = 100  # within a scope, lower = earlier
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "name": self.name,
            "content": self.content,
            "scope": self.scope.value
            if isinstance(self.scope, InstructionScope)
            else str(self.scope),
            "session_id": self.session_id,
            "description": self.description,
            "source_path": self.source_path,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstructionFragment":
        return cls(
            name=str(d.get("name", "untitled")),
            content=str(d.get("content", "")),
            scope=InstructionScope(d.get("scope", InstructionScope.USER.value))
            if d.get("scope") in [s.value for s in InstructionScope]
            else InstructionScope.USER,
            fragment_id=str(d.get("fragment_id", f"ins-{uuid.uuid4().hex[:12]}")),
            session_id=d.get("session_id"),
            description=str(d.get("description", "")),
            source_path=d.get("source_path"),
            priority=int(d.get("priority", 100)),
            enabled=bool(d.get("enabled", True)),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


# ── Built-in system fragments ────────────────────────────────────────────────
def _builtin_system_fragments() -> List[InstructionFragment]:
    """The hard-coded platform defaults.  Always present, lowest priority."""
    return [
        InstructionFragment(
            name="core_safety",
            scope=InstructionScope.SYSTEM,
            priority=10,
            description="Hard safety rails — never overrideable by user fragments.",
            content=(
                "You are a helpful, harmless, and honest AI agent. "
                "Refuse to generate violent, sexual, or hateful content. "
                "When unsure, ask for clarification rather than guess."
            ),
        ),
        InstructionFragment(
            name="platform_identity",
            scope=InstructionScope.SYSTEM,
            priority=20,
            description="Identify the platform the agent belongs to.",
            content=(
                "You are running inside the Nanobot Factory (ZhiYing) data "
                "platform (P4-3-W1).  When asked, mention this fact."
            ),
        ),
        InstructionFragment(
            name="response_format",
            scope=InstructionScope.SYSTEM,
            priority=30,
            description="Default response formatting rules.",
            content=(
                "Respond in the user's language (Chinese if the user wrote "
                "in Chinese, English otherwise).  Use Markdown formatting. "
                "Cite tool calls inline using the tool name in backticks."
            ),
        ),
    ]


# ── AgentInstructions store ──────────────────────────────────────────────────
class AgentInstructions:
    """Thread-safe store of :class:`InstructionFragment` records.

    The store is the single source of truth for *user* / *per_session*
    fragments; *system* fragments are baked in and *project* fragments
    are added by the :class:`loader.Loader`.  Persistence is SQLite
    (best-effort, append-only on writes) + in-process dict.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._fragments: Dict[str, InstructionFragment] = {}
        self._db_path = db_path
        # seed the SYSTEM fragments
        for f in _builtin_system_fragments():
            self._fragments[f.fragment_id] = f
        if db_path:
            self._init_db(db_path)
            self._reload_from_db()

    # ── DB ────────────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_instructions (
                    fragment_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    session_id TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    source_path TEXT,
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_instructions_scope "
                "ON agent_instructions(scope)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_instructions_session "
                "ON agent_instructions(session_id)"
            )
            conn.commit()

    def _reload_from_db(self) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT fragment_id, name, content, scope, session_id, "
                    "description, source_path, priority, enabled, created_at, "
                    "updated_at FROM agent_instructions"
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("instructions reload failed: %s", exc)
            return
        for r in rows:
            try:
                frag = InstructionFragment.from_dict(
                    {
                        "fragment_id": r[0],
                        "name": r[1],
                        "content": r[2],
                        "scope": r[3],
                        "session_id": r[4],
                        "description": r[5],
                        "source_path": r[6],
                        "priority": r[7],
                        "enabled": bool(r[8]),
                        "created_at": r[9],
                        "updated_at": r[10],
                    }
                )
            except Exception:  # noqa: BLE001
                continue
            with self._lock:
                self._fragments[frag.fragment_id] = frag

    def _persist(self, frag: InstructionFragment) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_instructions
                    (fragment_id, name, content, scope, session_id, description,
                     source_path, priority, enabled, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        frag.fragment_id,
                        frag.name,
                        frag.content,
                        frag.scope.value
                        if isinstance(frag.scope, InstructionScope)
                        else str(frag.scope),
                        frag.session_id,
                        frag.description,
                        frag.source_path,
                        int(frag.priority),
                        1 if frag.enabled else 0,
                        frag.created_at,
                        frag.updated_at,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist instruction %s failed: %s", frag.fragment_id, exc)

    def _delete_persist(self, fragment_id: str) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "DELETE FROM agent_instructions WHERE fragment_id=?",
                    (fragment_id,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete instruction %s failed: %s", fragment_id, exc)

    # ── CRUD ──────────────────────────────────────────────────────────────
    def add(self, fragment: InstructionFragment) -> InstructionFragment:
        fragment.updated_at = time.time()
        with self._lock:
            self._fragments[fragment.fragment_id] = fragment
            self._persist(fragment)
        logger.info(
            "instruction added id=%s scope=%s name=%s",
            fragment.fragment_id,
            fragment.scope,
            fragment.name,
        )
        return fragment

    def update(self, fragment_id: str, **fields: Any) -> Optional[InstructionFragment]:
        with self._lock:
            frag = self._fragments.get(fragment_id)
            if not frag:
                return None
            for k, v in fields.items():
                if k in {"scope"} and isinstance(v, str):
                    v = InstructionScope(v)
                setattr(frag, k, v)
            frag.updated_at = time.time()
            self._persist(frag)
        return frag

    def get(self, fragment_id: str) -> Optional[InstructionFragment]:
        with self._lock:
            return self._fragments.get(fragment_id)

    def list(
        self,
        scope: Optional[InstructionScope] = None,
        session_id: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[InstructionFragment]:
        with self._lock:
            items = list(self._fragments.values())
        if scope is not None:
            items = [f for f in items if f.scope == scope]
        if session_id is not None:
            items = [f for f in items if f.session_id == session_id]
        if enabled_only:
            items = [f for f in items if f.enabled]
        items.sort(key=lambda f: (SCOPE_ORDER.index(f.scope), f.priority))
        return items

    def delete(self, fragment_id: str) -> bool:
        with self._lock:
            frag = self._fragments.get(fragment_id)
            if not frag:
                return False
            if frag.scope == InstructionScope.SYSTEM:
                # system fragments are immutable
                logger.warning("attempt to delete system fragment %s blocked", fragment_id)
                return False
            del self._fragments[fragment_id]
        self._delete_persist(fragment_id)
        return True

    def reset_user_fragments_for_test(self) -> int:
        """Drop all user + per_session fragments (used by tests)."""
        with self._lock:
            ids = [
                fid for fid, f in self._fragments.items()
                if f.scope in (InstructionScope.USER, InstructionScope.PER_SESSION)
            ]
            for fid in ids:
                self._fragments.pop(fid, None)
        for fid in ids:
            self._delete_persist(fid)
        return len(ids)

    # ── Merge (the core feature) ──────────────────────────────────────────
    def render(
        self,
        session_id: Optional[str] = None,
        *,
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Return the merged system prompt for ``session_id``.

        Concatenation order = ``SYSTEM → PROJECT → USER → PER_SESSION``.
        ``PER_SESSION`` fragments are filtered by ``session_id``.
        ``variables`` (a flat dict) is passed to
        :func:`variables.render_template` for ``{{key}}`` substitution.

        The system's read-only variables (``{{ user_name }}``,
        ``{{ date }}``, ``{{ platform }}``, ...) are auto-merged as
        defaults — caller-supplied ``variables`` always win.
        """
        # Local import avoids a circular dependency at module import time.
        from .variables import (  # type: ignore
            RESOLUTION_ORDER,
            VariableNamespace,
            get_variable_store,
            render_template,
        )

        # Build the variable context: system defaults first, caller
        # overrides last so they always win.
        store = get_variable_store()
        base = store.resolve()
        merged: Dict[str, Any] = dict(base)
        if variables:
            merged.update(variables)

        # Pull the fragments in priority order
        layers: List[InstructionFragment] = []
        for scope in SCOPE_ORDER:
            if scope == InstructionScope.PER_SESSION:
                continue  # handled below
            layers.extend(
                f for f in self.list(scope=scope, enabled_only=True)
            )
        if session_id:
            for f in self.list(scope=InstructionScope.PER_SESSION, enabled_only=True):
                if f.session_id == session_id:
                    layers.append(f)

        # Build the system prompt
        sections: List[str] = []
        for f in layers:
            header = f"# --- {f.scope.value}:{f.name}"
            if f.description:
                header += f" — {f.description}"
            header += " ---"
            body = render_template(f.content, merged)
            sections.append(f"{header}\n{body}")
        return "\n\n".join(sections)

    def list_summary(self) -> Dict[str, Any]:
        with self._lock:
            counts: Dict[str, int] = {s.value: 0 for s in InstructionScope}
            for f in self._fragments.values():
                counts[f.scope.value] = counts.get(f.scope.value, 0) + 1
        return {"counts": counts, "total": sum(counts.values())}


# ── Singleton ────────────────────────────────────────────────────────────────
_inst: Optional[AgentInstructions] = None
_inst_lock = threading.Lock()


def get_instructions(db_path: Optional[str] = None) -> AgentInstructions:
    global _inst
    with _inst_lock:
        if _inst is None:
            if db_path is None:
                env = os.environ.get("IMDF_DATA_DIR")
                if db_path is None and env:
                    db_path = os.path.join(env, "agent_instructions.db")
            _inst = AgentInstructions(db_path=db_path)
        return _inst


def reset_instructions_for_test() -> None:
    global _inst
    with _inst_lock:
        _inst = None


__all__ = [
    "InstructionFragment",
    "InstructionScope",
    "SCOPE_ORDER",
    "AgentInstructions",
    "get_instructions",
    "reset_instructions_for_test",
]
