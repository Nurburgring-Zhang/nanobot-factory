"""P19-B4: AgentEngine — 13 Agent 统一调用引擎 (V5 第 16 章)

A stateful façade in front of :class:`AgentRouter` (logical dispatch)
and :class:`PluginRegistry` (the 13 builtin :class:`BaseAgent` classes
registered by :func:`imdf.agents.register_builtin_agents`).

The engine exposes:

  * :meth:`invoke_agent`         — run one task against one agent
  * :meth:`agent_session`        — multi-step conversational session
  * :meth:`agent_memory`         — in-process scratchpad per session
  * :meth:`start` / :meth:`stop` / :meth:`status` — uniform lifecycle

The engine itself does NOT execute agents (that's the router +
executor downstream).  It owns the dispatch record and lifecycle.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from . import agent_router as _agent_router_mod

# Lazy imports — the agents package transitively pulls services.*
# We avoid loading it at module import time.
_AgentContext: Optional[type] = None
_AgentResult: Optional[type] = None
_BaseAgent: Optional[type] = None
_PluginRegistry: Optional[type] = None


def _ensure_agent_classes() -> None:
    """Lazy import of the agent-plugin primitives.

    Tries ``imdf.agents.base`` first (canonical full path under the
    ``imdf`` package) and falls back to ``agents.base`` when running
    with a sys.path that has ``backend/imdf`` but not ``backend``.
    Both paths point at the same module.
    """
    global _AgentContext, _AgentResult, _BaseAgent, _PluginRegistry
    if _BaseAgent is not None:
        return
    last_err: Optional[Exception] = None
    for base in ("imdf.agents", "agents"):
        try:
            base_mod = __import__(base + ".base", fromlist=["AgentContext"])
            registry_mod = __import__(base + ".registry", fromlist=["PluginRegistry"])
            AgentContext = getattr(base_mod, "AgentContext")
            AgentResult = getattr(base_mod, "AgentResult")
            BaseAgent = getattr(base_mod, "BaseAgent")
            PluginRegistry = getattr(registry_mod, "PluginRegistry")
            _AgentContext = AgentContext
            _AgentResult = AgentResult
            _BaseAgent = BaseAgent
            _PluginRegistry = PluginRegistry
            return
        except Exception as exc:
            last_err = exc
            continue
    raise ImportError(
        "could not import agents.base from either imdf.agents or agents"
    ) from last_err


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Enums + dataclasses
# --------------------------------------------------------------------------- #
class AgentEngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class AgentInvocation:
    """One ``invoke_agent`` call's record."""

    invocation_id: str
    agent_type: str
    task_id: str
    mode: str
    status: str = "submitted"  # submitted / running / done / failed
    submitted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "agent_type": self.agent_type,
            "task_id": self.task_id,
            "mode": self.mode,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "finished_at": self.finished_at,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class AgentSession:
    """Multi-turn session record."""

    session_id: str
    invocations: List[str] = field(default_factory=list)  # invocation ids
    memory: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "invocations": list(self.invocations),
            "memory": dict(self.memory),
            "started_at": self.started_at,
        }


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class AgentEngine:
    """Stateful façade over :class:`AgentRouter` + :class:`PluginRegistry`."""

    def __init__(self, auto_register_builtin: bool = True) -> None:
        _ensure_agent_classes()
        assert _PluginRegistry is not None  # for type checkers
        self._registry = _PluginRegistry.get_registry()
        self._router = _agent_router_mod.get_agent_router()
        self._invocations: Dict[str, AgentInvocation] = {}
        self._sessions: Dict[str, AgentSession] = {}
        self._lock = threading.RLock()
        self._state = AgentEngineState.IDLE

        if auto_register_builtin:
            try:
                register_builtin_agents = None
                for base in ("imdf.agents", "agents"):
                    try:
                        mod = __import__(base, fromlist=["register_builtin_agents"])
                        register_builtin_agents = getattr(mod, "register_builtin_agents")
                        break
                    except Exception:
                        continue
                if register_builtin_agents is not None:
                    register_builtin_agents(self._registry)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("auto-register builtin agents failed: %s", exc)

    # ── Lifecycle ────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._state = AgentEngineState.RUNNING

    def stop(self) -> None:
        with self._lock:
            self._state = AgentEngineState.STOPPED

    def pause(self) -> None:
        with self._lock:
            if self._state == AgentEngineState.RUNNING:
                self._state = AgentEngineState.PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._state == AgentEngineState.PAUSED:
                self._state = AgentEngineState.RUNNING

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "registered_agents": self._registry.list(),
                "invocations": len(self._invocations),
                "sessions": len(self._sessions),
            }

    # ── Agent lookup ─────────────────────────────────────────────────
    def registered_agents(self) -> List[str]:
        with self._lock:
            return self._registry.list()

    # ── invoke_agent ─────────────────────────────────────────────────
    def invoke_agent(
        self,
        agent_type: str,
        input_payload: Dict[str, Any],
        *,
        mode: str = "full_auto",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> AgentInvocation:
        """Dispatch one task to the matching agent.

        Returns the :class:`AgentInvocation` record.  The actual
        execution happens downstream — we mark the record ``done``
        synchronously only when a local plugin is registered (so
        tests can verify the path end-to-end without a real
        agent-service).
        """
        if not agent_type or not isinstance(agent_type, str):
            raise ValueError(f"agent_type must be a non-empty string, got {agent_type!r}")
        if not isinstance(input_payload, dict):
            raise TypeError(f"input_payload must be a dict, got {type(input_payload).__name__}")

        invocation_id = uuid.uuid4().hex[:12]
        task_id = uuid.uuid4().hex[:8]

        record = AgentInvocation(
            invocation_id=invocation_id,
            agent_type=agent_type,
            task_id=task_id,
            mode=mode,
        )

        # Decision via the existing router — captures routing metadata
        # even when no real downstream service exists.
        try:
            decision = self._router.route(agent_type, input_payload)
            record.output["routing"] = {
                "downstream_service": decision.downstream_service,
                "eligible": decision.eligible,
                "reason": decision.reason,
            }
        except Exception as exc:  # pragma: no cover — defensive
            record.output["routing"] = {"error": str(exc)}

        # When a local plugin is registered, execute it inline so tests
        # can verify the full path without a downstream service.
        plugin_cls = None
        try_get = getattr(self._registry, "try_get", None)
        if callable(try_get):
            plugin_cls = try_get(agent_type)
        else:
            try:
                plugin_cls = self._registry.get(agent_type)
            except Exception:
                plugin_cls = None

        if plugin_cls is not None and _AgentContext is not None:
            try:
                plugin = plugin_cls()
                ctx = _AgentContext(
                    task_id=task_id,
                    agent_type=agent_type,
                    mode=mode,
                    input=input_payload,
                    metadata=metadata or {},
                )
                err = plugin.validate(ctx)
                if err is not None:
                    record.status = "failed"
                    record.error = err
                else:
                    result = plugin.execute(ctx)
                    record.output["plan"] = plugin.plan(ctx)
                    if getattr(result, "ok", False):
                        record.status = "done"
                        record.output["result"] = result.output
                    else:
                        record.status = "failed"
                        record.error = getattr(result, "error", "unknown error")
            except Exception as exc:
                record.status = "failed"
                record.error = f"plugin execution raised: {exc}"
        else:
            # No local plugin — dispatch to downstream service (logical).
            record.status = "submitted"

        record.finished_at = datetime.now().isoformat()

        with self._lock:
            self._invocations[invocation_id] = record
            if session_id:
                sess = self._sessions.setdefault(session_id, AgentSession(session_id=session_id))
                sess.invocations.append(invocation_id)

        return record

    # ── agent_session ────────────────────────────────────────────────
    def agent_session(
        self,
        session_id: Optional[str] = None,
        *,
        memory: Optional[Dict[str, Any]] = None,
    ) -> AgentSession:
        """Create or fetch a multi-turn session."""
        sid = session_id or uuid.uuid4().hex[:12]
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                sess = AgentSession(session_id=sid, memory=dict(memory or {}))
                self._sessions[sid] = sess
            elif memory:
                sess.memory.update(memory)
        return sess

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        with self._lock:
            return self._sessions.get(session_id)

    # ── agent_memory ────────────────────────────────────────────────
    def agent_memory(self, session_id: str, key: Optional[str] = None, value: Any = None) -> Any:
        """Get / set a memory key for a session.

        * ``key=None`` → return the whole memory dict
        * ``key=X, value=None`` → return memory[key]
        * ``key=X, value=Y`` → set memory[key] = Y and return Y
        """
        with self._lock:
            sess = self._sessions.setdefault(session_id, AgentSession(session_id=session_id))
            if key is None:
                return dict(sess.memory)
            if value is None and key not in sess.memory:
                return None
            if value is None:
                return sess.memory.get(key)
            sess.memory[key] = value
            return value

    # ── Convenience ──────────────────────────────────────────────────
    def get_invocation(self, invocation_id: str) -> Optional[AgentInvocation]:
        with self._lock:
            return self._invocations.get(invocation_id)


__all__ = [
    "AgentEngine",
    "AgentEngineState",
    "AgentInvocation",
    "AgentSession",
]