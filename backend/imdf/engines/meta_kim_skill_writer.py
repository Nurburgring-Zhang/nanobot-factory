"""P19 v5.3 — Meta_Kim Skill Writer.

Helper that turns a *success lesson* into a persisted :class:`SkillSpec` so the
governance loop can teach itself.

Design notes:

* The real ``skill_engine`` interface is not yet committed to the repo (P19 v5.1-B
  defines ``SkillSpec`` but the executor side is still in flight).  This helper
  therefore takes a thin ``skill_engine`` protocol — anything that exposes a
  ``create_skill(name, description, steps, trigger_phrases, ...)`` method will
  work.  A stub is provided so callers (including tests) can run end-to-end
  without wiring the real engine.
* The result is a ``SkillRecord`` (typed dict) so the engine can stash it in
  ``learned_skills`` and re-publish to the bus without round-tripping through
  the registry.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(name: str) -> str:
    """Lower-case slug, 1-48 chars, safe for skill_id namespaces."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return (s or "skill")[:48]


# --------------------------------------------------------------------------- #
# Protocol + Stub
# --------------------------------------------------------------------------- #
class SkillEngineLike(Protocol):
    """Minimal interface ``MetaKimSkillWriter`` requires from a skill engine."""

    def create_skill(
        self,
        *,
        name: str,
        description: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
        trigger_phrases: Optional[List[str]] = None,
        category: str = "auto_generated",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        ...


class StubSkillEngine:
    """In-memory replacement for the real skill engine — used by tests."""

    def __init__(self) -> None:
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create_skill(
        self,
        *,
        name: str,
        description: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
        trigger_phrases: Optional[List[str]] = None,
        category: str = "auto_generated",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        skill_id = f"skill_{_slugify(name)}_{uuid.uuid4().hex[:6]}"
        record = {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "steps": list(steps or []),
            "trigger_phrases": list(trigger_phrases or []),
            "category": category,
            "metadata": dict(metadata or {}),
            "created_at": _now_iso(),
        }
        with self._lock:
            self._skills[skill_id] = record
        return record

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._skills.values())

    def get(self, skill_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._skills.get(skill_id)


# --------------------------------------------------------------------------- #
# SkillRecord — typed result
# --------------------------------------------------------------------------- #
@dataclass
class SkillRecord:
    """Materialised skill produced from a successful lesson."""

    skill_id: str
    name: str
    description: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    trigger_phrases: List[str] = field(default_factory=list)
    category: str = "auto_generated"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_engine_output(cls, raw: Any) -> "SkillRecord":
        """Coerce whatever the engine returned into a typed SkillRecord."""
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, dict):
            return cls(
                skill_id=str(raw.get("skill_id") or f"skill_{uuid.uuid4().hex[:8]}"),
                name=str(raw.get("name") or "auto_skill"),
                description=str(raw.get("description") or ""),
                steps=list(raw.get("steps") or []),
                trigger_phrases=list(raw.get("trigger_phrases") or []),
                category=str(raw.get("category") or "auto_generated"),
                metadata=dict(raw.get("metadata") or {}),
                created_at=str(raw.get("created_at") or _now_iso()),
            )
        # Engine returned something exotic — wrap it
        return cls(
            skill_id=f"skill_{uuid.uuid4().hex[:8]}",
            name=str(raw),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# MetaKimSkillWriter
# --------------------------------------------------------------------------- #
class MetaKimSkillWriter:
    """Turns a success lesson into a persisted SkillRecord."""

    def __init__(
        self,
        skill_engine: Optional[SkillEngineLike] = None,
        *,
        auto_name: Optional[Callable[[Dict[str, Any]], str]] = None,
    ) -> None:
        self._engine: SkillEngineLike = skill_engine or StubSkillEngine()
        self._auto_name = auto_name
        self._created: List[SkillRecord] = []
        self._lock = threading.RLock()

    # ----- public ---------------------------------------------------------
    @property
    def engine(self) -> SkillEngineLike:
        return self._engine

    @property
    def created_skills(self) -> List[SkillRecord]:
        with self._lock:
            return list(self._created)

    def write_skill_from_lesson(
        self,
        lesson: Dict[str, Any],
        *,
        intent: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Optional[SkillRecord]:
        """Create a skill from a success lesson; returns None on bad input.

        ``lesson`` is expected to be the ``content`` dict of a
        :class:`meta_kim_schemas.Lesson` whose ``type == success``.
        """
        if not isinstance(lesson, dict):
            return None
        if lesson.get("type") == "failure":
            # Failures never produce skills — they're routed to the KB.
            return None

        name = (
            lesson.get("name")
            or self._auto_name_from_intent(intent or {})
            or f"auto_skill_{uuid.uuid4().hex[:8]}"
        )
        description = lesson.get("description") or ""
        steps = list(lesson.get("steps") or [])
        trigger_phrases = list(lesson.get("trigger_phrases") or [])

        metadata: Dict[str, Any] = {
            "source": "meta_kim",
            "run_id": run_id or "",
            "intent_type": (intent or {}).get("intent_type", "unknown"),
        }

        try:
            raw = self._engine.create_skill(
                name=name,
                description=description,
                steps=steps,
                trigger_phrases=trigger_phrases,
                category="auto_generated",
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover — best-effort
            logger.warning("MetaKimSkillWriter: create_skill failed: %s", exc)
            return None

        record = SkillRecord.from_engine_output(raw)
        with self._lock:
            self._created.append(record)
        return record

    # ----- helpers --------------------------------------------------------
    def _auto_name_from_intent(self, intent: Dict[str, Any]) -> str:
        if self._auto_name is not None:
            try:
                return str(self._auto_name(intent) or "")
            except Exception:
                pass
        intent_type = intent.get("intent_type") or "auto"
        return f"auto_{_slugify(str(intent_type))}_pipeline"


__all__ = [
    "SkillRecord",
    "SkillEngineLike",
    "StubSkillEngine",
    "MetaKimSkillWriter",
]