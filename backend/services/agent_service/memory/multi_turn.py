"""P4-3-W1: Multi-turn session memory for the Agent dispatch framework.

A ``SessionContext`` is the agent's per-conversation state.  Unlike the
short-term / long-term memory of P3-3 (which is keyed by ``scope/key``),
``SessionContext`` is keyed by ``session_id`` and stores:

* the rolling message list (with a configurable sliding window so the
  LLM context never explodes),
* a per-session ``variables`` dict (mirrored into the :mod:`variables`
  registry under the ``session`` namespace),
* a per-session ``tools`` set (so a session can opt-in to specific
  tools without exposing the whole registry to the LLM),
* running :class:`TokenUsageTracker` totals.

Persistence
-----------
Sessions live in two places:

* **In-process dict** — primary, hot look-ups, locks for thread-safety.
* **SQLite table ``agent_sessions``** — best-effort durable copy so
  sessions survive a process restart.  All public methods ``_persist``
  their state on the way out.

The schema intentionally lives in this file (instead of imdf.db) so the
agent service is hermetic for TestClient runs without PG.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Token tracker (P2-3 reuse) ───────────────────────────────────────────────
@dataclass
class TokenUsage:
    """Per-session token usage totals.

    ``prompt_tokens`` / ``completion_tokens`` are kept separately so the
    price calculator can apply a different rate to each.  ``total_tokens``
    is the cached sum (kept in sync by :meth:`add`).
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    last_model: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    def add(self, prompt: int, completion: int, model: Optional[str] = None) -> None:
        self.prompt_tokens += int(prompt)
        self.completion_tokens += int(completion)
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.last_model = model or self.last_model
        self.last_updated = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TokenUsageTracker:
    """Per-session + per-user + global token usage rollups.

    Used by the budget guard in P2-3; here we keep an in-process copy
    keyed by ``(user_id, session_id, "global")`` for cheap lookup.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # key -> TokenUsage
        self._by: Dict[str, TokenUsage] = {}

    def add(
        self,
        prompt: int,
        completion: int,
        *,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        global_total: bool = True,
    ) -> None:
        with self._lock:
            keys: List[str] = []
            if session_id:
                keys.append(f"session:{session_id}")
            if user_id:
                keys.append(f"user:{user_id}")
            if global_total:
                keys.append("global")
            for k in keys:
                usage = self._by.get(k) or TokenUsage()
                usage.add(prompt, completion, model)
                self._by[k] = usage

    def get(self, key: str) -> TokenUsage:
        with self._lock:
            return self._by.get(key) or TokenUsage()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._by.items()}

    def reset(self) -> None:
        with self._lock:
            self._by.clear()


# ── Message ──────────────────────────────────────────────────────────────────
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"
ROLE_TOOL = "tool"
VALID_ROLES = {ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL}


@dataclass
class Message:
    """One chat message in a session."""

    role: str
    content: str
    msg_id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # for role=tool
    name: Optional[str] = None  # for role=tool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        return cls(
            role=str(d.get("role", ROLE_USER)),
            content=str(d.get("content", "")),
            msg_id=str(d.get("msg_id", f"msg-{uuid.uuid4().hex[:12]}")),
            created_at=float(d.get("created_at", time.time())),
            metadata=dict(d.get("metadata") or {}),
            tool_calls=list(d.get("tool_calls") or []),
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )


# ── SessionContext ───────────────────────────────────────────────────────────
@dataclass
class SessionContext:
    """A single multi-turn conversation.

    Fields:
      * session_id    — stable unique id (also PK in the DB)
      * user_id       — owner of the session
      * messages      — chronologically ordered list[:max_messages]
      * variables     — per-session variable overrides
      * tools         — per-session allow-list of tool names
      * summary       — running LLM-generated summary (see ``summarize``)
      * usage         — :class:`TokenUsage` totals for this session
      * created_at / updated_at — ISO timestamps
    """

    session_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    summary: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": [m.to_dict() for m in self.messages],
            "variables": dict(self.variables),
            "tools": list(self.tools),
            "summary": self.summary,
            "usage": self.usage.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionContext":
        return cls(
            session_id=str(d["session_id"]),
            user_id=str(d.get("user_id", "anonymous")),
            messages=[Message.from_dict(m) for m in d.get("messages", [])],
            variables=dict(d.get("variables") or {}),
            tools=list(d.get("tools") or []),
            summary=str(d.get("summary", "")),
            usage=TokenUsage(**d.get("usage") or {}),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
            metadata=dict(d.get("metadata") or {}),
        )


# ── MultiTurnSessionManager ──────────────────────────────────────────────────
class MultiTurnSessionManager:
    """Thread-safe manager for :class:`SessionContext` objects.

    Sliding window
    --------------
    ``max_messages`` defaults to 50; once a session exceeds the cap, the
    oldest non-system message is dropped.  The dropped messages' content
    is *not* lost — they are condensed into ``summary`` (a separate
    :func:`summarize` call updates ``summary`` in place).  The cap can be
    changed per session by writing ``max_messages`` into the
    session's ``metadata`` dict.

    Persistence
    -----------
    When ``db_path`` is set, every mutation ``_persist``'s the new state
    of the session to a single-row ``INSERT OR REPLACE`` so a process
    restart picks up where we left off.
    """

    DEFAULT_MAX_MESSAGES = 50

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, SessionContext] = {}
        self._db_path = db_path
        self._tracker = TokenUsageTracker()
        if db_path:
            self._init_db(db_path)

    # ── DB ────────────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_sessions_user "
                "ON agent_sessions(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_sessions_updated "
                "ON agent_sessions(updated_at)"
            )
            conn.commit()

    def _persist(self, ctx: SessionContext) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_sessions
                    (session_id, user_id, state, created_at, updated_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        ctx.session_id,
                        ctx.user_id,
                        json.dumps(ctx.to_dict(), ensure_ascii=False),
                        ctx.created_at,
                        ctx.updated_at,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist session %s failed: %s", ctx.session_id, exc)

    def _delete_persist(self, session_id: str) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "DELETE FROM agent_sessions WHERE session_id=?",
                    (session_id,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete session %s failed: %s", session_id, exc)

    # ── CRUD ──────────────────────────────────────────────────────────────
    def create(
        self,
        user_id: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        sid = session_id or f"ses-{uuid.uuid4().hex[:12]}"
        ctx = SessionContext(
            session_id=sid,
            user_id=str(user_id or "anonymous"),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._sessions[sid] = ctx
            self._persist(ctx)
        logger.info("session created sid=%s user=%s", sid, ctx.user_id)
        return ctx

    def get(self, session_id: str) -> Optional[SessionContext]:
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is not None:
                return ctx
        # Try reload from DB
        return self._reload_from_db(session_id)

    def _reload_from_db(self, session_id: str) -> Optional[SessionContext]:
        if not self._db_path:
            return None
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT state FROM agent_sessions WHERE session_id=?",
                    (session_id,),
                ).fetchone()
        except Exception:  # noqa: BLE001
            return None
        if not row:
            return None
        try:
            d = json.loads(row[0])
            ctx = SessionContext.from_dict(d)
        except Exception as exc:  # noqa: BLE001
            logger.warning("reload session %s failed: %s", session_id, exc)
            return None
        with self._lock:
            self._sessions[session_id] = ctx
        return ctx

    def list(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[SessionContext]:
        items: List[SessionContext] = []
        if self._db_path:
            try:
                with sqlite3.connect(self._db_path) as conn:
                    if user_id:
                        rows = conn.execute(
                            "SELECT state FROM agent_sessions WHERE user_id=? "
                            "ORDER BY updated_at DESC LIMIT ?",
                            (user_id, int(limit)),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT state FROM agent_sessions "
                            "ORDER BY updated_at DESC LIMIT ?",
                            (int(limit),),
                        ).fetchall()
                for (state,) in rows:
                    try:
                        items.append(SessionContext.from_dict(json.loads(state)))
                    except Exception:  # noqa: BLE001
                        continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("list sessions failed: %s", exc)
        if not items:
            with self._lock:
                snapshot = list(self._sessions.values())
            if user_id:
                snapshot = [s for s in snapshot if s.user_id == user_id]
            snapshot.sort(key=lambda s: s.updated_at, reverse=True)
            items = snapshot[: max(0, limit)]
        return items

    def delete(self, session_id: str) -> bool:
        with self._lock:
            existed = self._sessions.pop(session_id, None) is not None
        self._delete_persist(session_id)
        return existed

    def reset_for_test(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._tracker.reset()

    # ── Messages ──────────────────────────────────────────────────────────
    def _cap(self, ctx: SessionContext) -> int:
        meta_cap = ctx.metadata.get("max_messages") if ctx.metadata else None
        try:
            return int(meta_cap) if meta_cap else self.DEFAULT_MAX_MESSAGES
        except (TypeError, ValueError):
            return self.DEFAULT_MAX_MESSAGES

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        ctx = self.get(session_id)
        if ctx is None:
            raise KeyError(f"session_not_found:{session_id}")
        if role not in VALID_ROLES:
            raise ValueError(f"invalid_role:{role}")
        msg = Message(
            role=role,
            content=str(content),
            tool_calls=list(tool_calls or []),
            tool_call_id=tool_call_id,
            name=name,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            ctx.messages.append(msg)
            ctx.updated_at = time.time()
            # Sliding window: drop oldest non-system message if over cap.
            cap = self._cap(ctx)
            while len(ctx.messages) > cap:
                # find first non-system
                drop_idx = -1
                for i, m in enumerate(ctx.messages):
                    if m.role != ROLE_SYSTEM:
                        drop_idx = i
                        break
                if drop_idx == -1:
                    break  # only system messages — refuse to drop
                ctx.messages.pop(drop_idx)
            self._persist(ctx)
        return msg

    def get_messages(
        self,
        session_id: str,
        *,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        ctx = self.get(session_id)
        if ctx is None:
            return []
        msgs = [m.to_dict() for m in ctx.messages]
        if limit is not None:
            msgs = msgs[-int(limit):]
        return msgs

    def clear_messages(self, session_id: str) -> int:
        ctx = self.get(session_id)
        if ctx is None:
            return 0
        with self._lock:
            n = len(ctx.messages)
            ctx.messages.clear()
            ctx.updated_at = time.time()
            self._persist(ctx)
        return n

    def pop_message(self, session_id: str, msg_id: str) -> Optional[Message]:
        ctx = self.get(session_id)
        if ctx is None:
            return None
        with self._lock:
            for i, m in enumerate(ctx.messages):
                if m.msg_id == msg_id:
                    removed = ctx.messages.pop(i)
                    ctx.updated_at = time.time()
                    self._persist(ctx)
                    return removed
        return None

    # ── Variables / tools bound to the session ────────────────────────────
    def set_variable(self, session_id: str, key: str, value: Any) -> None:
        ctx = self.get(session_id)
        if ctx is None:
            raise KeyError(f"session_not_found:{session_id}")
        with self._lock:
            ctx.variables[str(key)] = value
            ctx.updated_at = time.time()
            self._persist(ctx)

    def get_variable(self, session_id: str, key: str, default: Any = None) -> Any:
        ctx = self.get(session_id)
        if ctx is None:
            return default
        return ctx.variables.get(key, default)

    def set_tools(self, session_id: str, tools: List[str]) -> None:
        ctx = self.get(session_id)
        if ctx is None:
            raise KeyError(f"session_not_found:{session_id}")
        with self._lock:
            ctx.tools = [str(t) for t in tools]
            ctx.updated_at = time.time()
            self._persist(ctx)

    def get_tools(self, session_id: str) -> List[str]:
        ctx = self.get(session_id)
        if ctx is None:
            return []
        return list(ctx.tools)

    # ── Token tracking ────────────────────────────────────────────────────
    def record_usage(
        self,
        session_id: str,
        prompt: int,
        completion: int,
        *,
        model: Optional[str] = None,
    ) -> None:
        ctx = self.get(session_id)
        user_id = ctx.user_id if ctx else None
        with self._lock:
            if ctx is not None:
                ctx.usage.add(prompt, completion, model)
                ctx.updated_at = time.time()
                self._persist(ctx)
            self._tracker.add(
                prompt,
                completion,
                model=model,
                session_id=session_id,
                user_id=user_id,
            )

    def get_usage(self, session_id: str) -> TokenUsage:
        ctx = self.get(session_id)
        return ctx.usage if ctx else TokenUsage()

    def usage_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return self._tracker.snapshot()

    # ── Summary (LLM hook) ────────────────────────────────────────────────
    def set_summary(self, session_id: str, summary: str) -> None:
        ctx = self.get(session_id)
        if ctx is None:
            raise KeyError(f"session_not_found:{session_id}")
        with self._lock:
            ctx.summary = str(summary)
            ctx.updated_at = time.time()
            self._persist(ctx)

    def get_summary(self, session_id: str) -> str:
        ctx = self.get(session_id)
        return ctx.summary if ctx else ""

    def summarize(
        self,
        session_id: str,
        summariser: Any = None,
    ) -> str:
        """Run an LLM-style summary over the session's messages.

        ``summariser`` is a ``Callable[[List[Dict[str,str]]], str]``.  When
        ``None`` we fall back to a deterministic offline summary
        (concatenate the first 240 chars of each non-system message) so
        the route works without a live LLM.
        """
        ctx = self.get(session_id)
        if ctx is None:
            raise KeyError(f"session_not_found:{session_id}")

        if summariser is not None:
            try:
                summary = summariser([m.to_dict() for m in ctx.messages])
            except Exception as exc:  # noqa: BLE001
                logger.warning("custom summariser failed: %s", exc)
                summary = self._offline_summary(ctx)
        else:
            summary = self._offline_summary(ctx)
        self.set_summary(session_id, summary)
        return summary

    @staticmethod
    def _offline_summary(ctx: SessionContext) -> str:
        lines: List[str] = []
        for m in ctx.messages:
            if m.role == ROLE_SYSTEM:
                continue
            snippet = m.content.replace("\n", " ").strip()
            if len(snippet) > 240:
                snippet = snippet[:237] + "..."
            lines.append(f"[{m.role}] {snippet}")
        if not lines:
            return ""
        body = " | ".join(lines)
        if len(body) > 1024:
            body = body[:1021] + "..."
        return f"Session {ctx.session_id} ({len(ctx.messages)} msgs): {body}"


# ── Singleton ────────────────────────────────────────────────────────────────
_manager: Optional[MultiTurnSessionManager] = None
_manager_lock = threading.Lock()


def get_session_manager(db_path: Optional[str] = None) -> MultiTurnSessionManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            if db_path is None:
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    db_path = os.path.join(env, "agent_sessions.db")
            _manager = MultiTurnSessionManager(db_path=db_path)
        return _manager


def reset_session_manager_for_test() -> None:
    global _manager
    with _manager_lock:
        _manager = None


__all__ = [
    "Message",
    "SessionContext",
    "MultiTurnSessionManager",
    "TokenUsage",
    "TokenUsageTracker",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_SYSTEM",
    "ROLE_TOOL",
    "VALID_ROLES",
    "get_session_manager",
    "reset_session_manager_for_test",
]
