"""P4-8-W1: SkillContext — per-call state shared across a Skill chain.

The context bundles everything a skill needs to know about its caller and
the chain it is part of:

  * ``user_id`` / ``project_id``  — multi-tenant scoping
  * ``blackboard``                 — dict shared across all chained skills
  * ``memory``                     — optional handle to MemoryPalace
  * ``inputs``                     — the raw input kwargs from the caller
  * ``artifacts_dir``              — where skills may write output files
  * ``parent``                     — optional parent context (for sub-skills)
  * ``trace``                      — list of step records (auto-populated)

A ``SkillContext`` is created once per top-level orchestrator call.  Each
skill that runs gets its own *derived* context (see ``derive``) which
shares the same blackboard + memory but carries the skill's own outputs
and a fresh trace entry.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Blackboard:
    """Mutable dict-like scratch space shared across chained skills.

    Backed by a real dict for simplicity; reads default to ``None`` so a
    skill can ask ``ctx.blackboard.get("draft")`` without worrying about
    whether the upstream skill actually produced one.
    """

    _store: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._store

    def pop(self, key: str, default: Any = None) -> Any:
        return self._store.pop(key, default)

    def items(self) -> List[Any]:
        return list(self._store.items())

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._store)

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)


@dataclass
class TraceEntry:
    """One row in the context trace (one per skill invocation)."""

    skill: str
    started_at: float
    ended_at: float = 0.0
    success: bool = False
    error: str = ""
    note: str = ""

    @property
    def duration_ms(self) -> float:
        if self.ended_at <= 0:
            return 0.0
        return (self.ended_at - self.started_at) * 1000.0


@dataclass
class SkillContext:
    """Per-call context for a Skill execution.

    Build with :meth:`create` (top-level) or :meth:`derive` (chained).
    """

    user_id: str
    project_id: str = "default"
    inputs: Dict[str, Any] = field(default_factory=dict)
    blackboard: Blackboard = field(default_factory=Blackboard)
    artifacts_dir: str = ""
    memory: Any = None  # optional MemoryPalace handle (P4-3-W2)
    session_id: str = field(default_factory=lambda: f"sk_{uuid.uuid4().hex[:12]}")
    parent: Optional["SkillContext"] = None
    trace: List[TraceEntry] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Factory helpers ────────────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        user_id: str = "anonymous",
        project_id: str = "default",
        inputs: Optional[Dict[str, Any]] = None,
        artifacts_dir: str = "",
        memory: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SkillContext":
        return cls(
            user_id=user_id,
            project_id=project_id,
            inputs=dict(inputs or {}),
            blackboard=Blackboard(),
            artifacts_dir=artifacts_dir,
            memory=memory,
            metadata=dict(metadata or {}),
        )

    def derive(
        self,
        *,
        skill_name: str,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> "SkillContext":
        """Return a child context that shares blackboard + memory.

        Useful when one skill internally calls another.
        """
        child = SkillContext(
            user_id=self.user_id,
            project_id=self.project_id,
            inputs=dict(inputs or {}),
            blackboard=self.blackboard,  # shared, not copied
            artifacts_dir=self.artifacts_dir,
            memory=self.memory,
            session_id=self.session_id,
            parent=self,
            metadata=dict(self.metadata),
        )
        child.trace.append(TraceEntry(skill=skill_name, started_at=time.time()))
        return child

    # ── Blackboard shortcuts ───────────────────────────────────────────────
    def put(self, key: str, value: Any) -> None:
        self.blackboard.set(key, value)

    def pull(self, key: str, default: Any = None) -> Any:
        return self.blackboard.get(key, default)

    # ── Trace helpers ──────────────────────────────────────────────────────
    def finish_last(self, success: bool, *, error: str = "", note: str = "") -> None:
        if not self.trace:
            return
        last = self.trace[-1]
        last.ended_at = time.time()
        last.success = success
        last.error = error
        last.note = note

    def trace_snapshot(self) -> List[Dict[str, Any]]:
        return [
            {
                "skill": t.skill,
                "duration_ms": round(t.duration_ms, 2),
                "success": t.success,
                "error": t.error,
                "note": t.note,
            }
            for t in self.trace
        ]


__all__ = ["SkillContext", "Blackboard", "TraceEntry"]