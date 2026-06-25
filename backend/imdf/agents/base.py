"""P6-Fix-P0-5: BaseAgent abstract class + runtime plugin contract.

This module defines the canonical :class:`BaseAgent` ABC plus the value
objects that flow through the dispatch framework:

  * :class:`AgentContext`  — immutable-ish input the executor hands to a
    concrete agent.  Carries the task id, the requested mode, the
    original input payload, and an open metadata bag.
  * :class:`AgentResult`   — uniform response shape every concrete agent
    must return.  Even failure cases use this shape (``ok=False``,
    ``error=...``) so the executor can stay branch-free.

Why an ABC and not a Protocol?
  The platform already has 23 named :class:`AgentType` enum members and
  23 corresponding metadata entries in ``AGENT_REGISTRY``.  An ABC lets
  us declare the contract once and have ``isinstance`` work in
  user-facing code (routes, MCP tools) without re-introspecting dicts.

The contract is intentionally small:
  * :attr:`name`, :attr:`description`, :attr:`capabilities` — metadata
  * :attr:`agent_type` — back-link to the canonical enum member
  * :meth:`execute` — the only behaviour every concrete agent MUST
    implement
  * :meth:`plan` — optional helper that returns the canonical step
    list; default impl returns an empty list, the executor still
    produces a usable ``plan`` dict downstream.

A concrete subclass is *only* required to set the metadata class
attributes and implement :meth:`execute`.  Everything else (id
generation, registry binding, retry policy) is handled by the
executor / scheduler layers.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional


# Sentinel for "no enum coupling at import time" — the canonical
# :class:`AgentType` lives in ``services.agent_service.agents`` and we
# don't want a circular import.  We accept either the enum member,
# the string slug, or ``None`` (which means "untyped plugin").
AgentTypeRef = Optional[Any]


@dataclass
class AgentContext:
    """Input handed to :meth:`BaseAgent.execute`.

    Attributes:
        task_id:    Stable task id assigned by the store.  The agent
                    must echo this back in :attr:`AgentResult.task_id`
                    so the executor can correlate status updates.
        agent_type: The slug (string) identifying which agent type the
                    task is routed to.  Useful when an agent class
                    serves multiple AgentType entries (rare).
        mode:       ``"full_auto"`` / ``"semi_auto"`` / ``"manual"``.
        input:      User-supplied input payload (already validated by
                    the route layer).
        metadata:   Open bag for executor-provided hints (priority,
                    deadline, trace_id, downstream overrides, ...).
    """

    task_id: str
    agent_type: str
    mode: str = "full_auto"
    input: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Uniform return shape for :meth:`BaseAgent.execute`.

    The executor treats ``ok`` as the source of truth — it does NOT
    inspect ``output`` or ``plan`` for failure.  A failed agent should
    set ``ok=False`` + ``error=<reason>`` and may still attach
    diagnostic data in ``output`` (e.g. partial outputs).
    """

    ok: bool
    task_id: str
    agent_type: str
    output: Dict[str, Any] = field(default_factory=dict)
    plan: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict (for memory / store)."""
        return {
            "ok": bool(self.ok),
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "output": dict(self.output),
            "plan": list(self.plan),
            "error": self.error,
            "error_source": self.error_source,
        }

    @classmethod
    def from_exception(
        cls,
        task_id: str,
        agent_type: str,
        exc: BaseException,
        *,
        error_source: Optional[str] = None,
    ) -> "AgentResult":
        """Build a failure result from an exception (caller's helper)."""
        return cls(
            ok=False,
            task_id=task_id,
            agent_type=agent_type,
            output={},
            plan=[],
            error=f"{type(exc).__name__}: {exc}",
            error_source=error_source,
        )


class BaseAgent(abc.ABC):
    """Abstract base for every concrete agent type.

    Subclasses MUST:
      * set the class attributes (``name``, ``description``, ``capabilities``, ...)
      * implement :meth:`execute`

    Subclasses SHOULD:
      * set :attr:`agent_type` to the canonical :class:`AgentType`
        enum member (or its string slug) so the registry can validate
      * override :meth:`plan` only if the canonical step list differs
        from the metadata-driven default
    """

    # ── Metadata ────────────────────────────────────────────────────────
    # Concrete subclasses override these.  Defaults are the minimum
    # required to keep ``BaseAgent`` instantiable in tests.
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    capabilities: ClassVar[List[str]] = []

    # ── Dispatch metadata ───────────────────────────────────────────────
    # These are surfaced to the executor for retry / timeout / routing
    # decisions.  Default to conservative values.
    default_mode: ClassVar[str] = "full_auto"
    default_priority: ClassVar[int] = 5
    max_retries: ClassVar[int] = 1
    timeout_seconds: ClassVar[int] = 60
    downstream_service: ClassVar[Optional[str]] = None

    # ── Back-link to the canonical AgentType enum ───────────────────────
    # Set this on each subclass so :func:`get_agent_class` can resolve
    # ``AgentType.XXX -> ConcreteAgent``.  Importing the enum at module
    # scope creates a circular import; we keep the link as ``Any`` and
    # resolve lazily in :meth:`get_agent_type_slug`.
    agent_type: ClassVar[AgentTypeRef] = None

    # ── ABC contract ────────────────────────────────────────────────────
    @abc.abstractmethod
    def execute(self, context: AgentContext) -> AgentResult:
        """Run the agent against ``context`` and return a result.

        Implementations MUST be deterministic w.r.t. the inputs and
        MUST NOT raise on validation failures — they should return an
        ``AgentResult(ok=False, error=...)``.  Raising is reserved for
        programmer errors (TypeError, KeyError on a missing required
        field, ...).
        """

    # ── Optional helpers ────────────────────────────────────────────────
    def plan(self, context: AgentContext) -> List[str]:
        """Return the canonical step list for ``context``.

        Default impl returns an empty list.  Concrete agents that have
        a non-trivial plan (e.g. multi-stage generation pipelines)
        override this to expose the steps to the executor.
        """
        return []

    def validate(self, context: AgentContext) -> Optional[str]:
        """Pre-execute validation hook.  Returns None when OK, else
        a human-readable error string.

        Default impl checks that ``task_id`` is non-empty.  Concrete
        agents override to add domain checks (e.g. "input must
        contain 'dataset_id'").
        """
        if not context.task_id:
            return "task_id is required"
        return None

    # ── Identity helpers ────────────────────────────────────────────────
    def get_agent_type_slug(self) -> str:
        """Return the string slug for this agent.

        Prefers the enum's ``.value`` when :attr:`agent_type` is an
        :class:`AgentType` member; falls back to the attribute as-is
        when it is already a string; returns ``""`` when unset.
        """
        ref = self.agent_type
        if ref is None:
            return ""
        value = getattr(ref, "value", ref)
        return str(value) if value is not None else ""

    # ── Repr ────────────────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        slug = self.get_agent_type_slug() or "<untyped>"
        return f"<{type(self).__name__} agent_type={slug!r} name={self.name!r}>"


__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
]
