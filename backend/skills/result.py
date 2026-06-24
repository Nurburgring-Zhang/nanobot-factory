"""P4-8-W1: SkillResult — the structured outcome of a Skill execution.

A :class:`SkillResult` is a deliberately small dataclass that captures:

  * ``success``         — bool, did the skill finish without raising?
  * ``data``            — any JSON-serializable payload (string / dict / list)
  * ``logs``            — list of human-readable log lines (UI surfacing)
  * ``artifacts``       — list of file paths / URLs the skill wrote
  * ``error``           — error message if ``success=False``
  * ``metadata``        — free-form (mock flag, model used, tokens, ...)
  * ``skill_name``      — convenience copy of meta.name for downstream code

Chaining convention
-------------------
When a Skill is part of a chain, the orchestrator pulls the next skill's
input either from ``result.data`` (if the caller asked for ``mode="data"``)
or from ``result.data["output"]`` (if ``mode="output"``).  Both are
supported; ``mode="data"`` is the default and is what the 10 built-in
skills return.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillResult:
    success: bool = True
    data: Any = None
    logs: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    skill_name: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0

    # ── Convenience factories ─────────────────────────────────────────────
    @classmethod
    def ok(cls, data: Any = None, *, skill_name: str = "",
           logs: Optional[List[str]] = None,
           artifacts: Optional[List[str]] = None,
           metadata: Optional[Dict[str, Any]] = None) -> "SkillResult":
        return cls(
            success=True,
            data=data,
            logs=list(logs or []),
            artifacts=list(artifacts or []),
            skill_name=skill_name,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def fail(cls, error: str, *, skill_name: str = "",
             metadata: Optional[Dict[str, Any]] = None) -> "SkillResult":
        return cls(
            success=False,
            error=error,
            skill_name=skill_name,
            metadata=dict(metadata or {}),
        )

    # ── Serialization ──────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    # ── Chaining helpers ───────────────────────────────────────────────────
    def pick(self, mode: str = "data") -> Any:
        """Return the value the next skill in a chain should consume.

        ``mode="data"``  → return ``self.data`` unchanged (default)
        ``mode="output"`` → return ``self.data["output"]`` if it's a dict
        ``mode="json"``  → return JSON string of ``self.data``
        """
        if mode == "data":
            return self.data
        if mode == "output":
            if isinstance(self.data, dict) and "output" in self.data:
                return self.data["output"]
            return self.data
        if mode == "json":
            return self.to_json()
        return self.data

    @property
    def duration_ms(self) -> float:
        if self.ended_at <= 0 or self.started_at <= 0:
            return 0.0
        return (self.ended_at - self.started_at) * 1000.0


__all__ = ["SkillResult"]