"""P4-8-W1: SkillOrchestrator — multi-skill routing + chaining.

The orchestrator is the runtime layer above :class:`SkillRegistry`.  It
solves three problems:

1. **Task routing** — given a high-level request (a string or a dict),
   pick the best matching Skill.  When ``mode="auto"`` the orchestrator
   falls back to keyword scoring across registered skill names /
   descriptions / tags (no LLM dependency).

2. **Skill chaining** — run a sequence of skills, piping the previous
   result's ``data`` (or ``data["output"]``) into the next skill's input
   via the shared :class:`~.context.Blackboard`.

3. **Error handling** — three policies:

   * ``retry``    — re-run the failing skill up to N times before giving up
   * ``fallback`` — on failure, try the next skill in a fallback list
   * ``skip``     — record the error and continue with the next step

The orchestrator is fully async and stateless across calls — instances
may be safely reused.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from .base import Skill, SkillCategory
from .context import SkillContext
from .registry import SKILL_REGISTRY, SkillRegistry
from .result import SkillResult

logger = logging.getLogger(__name__)


# ── Chain step / chain spec ──────────────────────────────────────────────────
@dataclass
class ChainStep:
    """One entry in a skill chain."""

    skill: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    version: Optional[str] = None
    on_error: str = "skip"            # retry / fallback / skip
    retries: int = 1
    fallback: List[str] = field(default_factory=list)
    pick_mode: str = "data"           # data / output / json

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "inputs": dict(self.inputs),
            "version": self.version,
            "on_error": self.on_error,
            "retries": self.retries,
            "fallback": list(self.fallback),
            "pick_mode": self.pick_mode,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChainStep":
        return cls(
            skill=str(d["skill"]),
            inputs=dict(d.get("inputs", {})),
            version=d.get("version"),
            on_error=d.get("on_error", "skip"),
            retries=int(d.get("retries", 1)),
            fallback=list(d.get("fallback", [])),
            pick_mode=d.get("pick_mode", "data"),
        )


@dataclass
class ChainResult:
    """Outcome of a full chain execution."""

    success: bool
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_data: Any = None
    errors: List[str] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.ended_at <= 0 or self.started_at <= 0:
            return 0.0
        return (self.ended_at - self.started_at) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "steps": list(self.steps),
            "final_data": self.final_data,
            "errors": list(self.errors),
            "duration_ms": round(self.duration_ms, 2),
        }


# ── Orchestrator ─────────────────────────────────────────────────────────────
class SkillOrchestrator:
    """Coordinates routing + chaining + error handling for skills."""

    def __init__(self, registry: Optional[SkillRegistry] = None) -> None:
        self.registry = registry or SKILL_REGISTRY
        self._routing_keywords: Dict[str, List[str]] = {}

    # ── Routing ────────────────────────────────────────────────────────────
    def register_route(self, skill_name: str, keywords: Sequence[str]) -> None:
        """Bind a list of keywords to a skill for auto-routing."""
        self._routing_keywords[skill_name] = [k.lower() for k in keywords]

    def _score(self, query: str, skill_name: str) -> int:
        score = 0
        q = (query or "").lower()
        if not q:
            return 0
        if skill_name.lower() in q:
            score += 5
        for kw in self._routing_keywords.get(skill_name, []):
            if kw and kw in q:
                score += 2
        # Also score against the skill's description & tags.
        try:
            meta = self.registry.meta(skill_name)
            haystack = " ".join([
                meta.description.lower(),
                " ".join(meta.tags).lower(),
            ])
            for word in re.findall(r"\w+", q):
                if word and len(word) >= 2 and word in haystack:
                    score += 1
        except KeyError:
            pass
        return score

    def route(self, query: str, *, candidates: Optional[Sequence[str]] = None) -> Optional[str]:
        """Return the highest-scoring skill name for ``query`` or ``None``."""
        names = list(candidates) if candidates else self.registry.names()
        scored: List[Tuple[int, str]] = [
            (self._score(query, n), n) for n in names
        ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        if not scored or scored[0][0] <= 0:
            return None
        return scored[0][1]

    # ── Single-skill execution ─────────────────────────────────────────────
    async def run_skill(
        self,
        name: str,
        context: SkillContext,
        inputs: Optional[Dict[str, Any]] = None,
        *,
        version: Optional[str] = None,
        on_error: str = "skip",
        retries: int = 1,
        fallback: Optional[Sequence[str]] = None,
    ) -> SkillResult:
        """Execute a single skill with retry + fallback policy."""
        merged_inputs = dict(context.inputs)
        if inputs:
            merged_inputs.update(inputs)

        attempts = max(1, int(retries))
        candidates = [name] + list(fallback or [])

        last_result: Optional[SkillResult] = None
        for candidate in candidates:
            try:
                skill = self.registry.get(candidate, version=version)
            except KeyError as exc:
                last_result = SkillResult.fail(str(exc), skill_name=candidate)
                if on_error == "skip":
                    return last_result
                continue

            for attempt in range(attempts):
                ctx = context.derive(skill_name=candidate, inputs=merged_inputs)
                ctx.put("_skill_name", candidate)
                ctx.put("_attempt", attempt + 1)
                start = time.time()
                try:
                    raw = skill.execute(ctx)
                    if inspect.isawaitable(raw):
                        raw = await raw
                    if not isinstance(raw, SkillResult):
                        raw = SkillResult.ok(data=raw, skill_name=candidate)
                    raw.started_at = start
                    raw.ended_at = time.time()
                    raw.skill_name = raw.skill_name or candidate
                    ctx.finish_last(True, note=f"attempt={attempt + 1}")
                    # Stash the result for downstream skills.
                    context.put(f"step::{candidate}", raw.to_dict())
                    return raw
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "skill %s attempt %d/%d failed: %s",
                        candidate, attempt + 1, attempts, exc,
                    )
                    last_result = SkillResult.fail(str(exc), skill_name=candidate)
                    ctx.finish_last(False, error=str(exc), note=f"attempt={attempt + 1}")
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0)  # yield control
            # candidate exhausted, decide policy
            if on_error == "fallback":
                continue
            if on_error == "skip":
                return last_result or SkillResult.fail(
                    "unknown error", skill_name=candidate)
            return last_result or SkillResult.fail(
                "unknown error", skill_name=candidate)
        return last_result or SkillResult.fail("no candidates executed", skill_name=name)

    # ── Chain execution ────────────────────────────────────────────────────
    async def run_chain(
        self,
        steps: Sequence[ChainStep],
        context: SkillContext,
    ) -> ChainResult:
        """Run a sequence of :class:`ChainStep` definitions.

        Each step's output (under ``pick_mode``) is merged into the next
        step's inputs under the key ``"input"`` — that is, step N+1 sees::

            {"input": <step N result>, **original_inputs}
        """
        chain = ChainResult(success=True, started_at=time.time())
        current_value: Any = None
        for idx, step in enumerate(steps):
            merged_inputs = dict(step.inputs)
            if current_value is not None and idx > 0:
                merged_inputs.setdefault("input", current_value)
            res = await self.run_skill(
                step.skill,
                context,
                inputs=merged_inputs,
                version=step.version,
                on_error=step.on_error,
                retries=step.retries,
                fallback=step.fallback,
            )
            chain.steps.append({
                **step.to_dict(),
                "index": idx,
                "success": res.success,
                "error": res.error,
                "data_preview": _short_preview(res.data),
                "duration_ms": round(res.duration_ms, 2),
                "skill_name": res.skill_name,
            })
            if not res.success:
                chain.errors.append(f"{step.skill}: {res.error}")
                if step.on_error == "skip":
                    # Continue but mark chain as failed at the end.
                    current_value = None
                    continue
                chain.success = False
                break
            current_value = res.pick(step.pick_mode)
            # Also remember last successful output on the blackboard.
            context.put(f"chain::{step.skill}", res.data)

        chain.final_data = current_value
        chain.ended_at = time.time()
        if chain.errors and not any(s.get("success") for s in chain.steps):
            chain.success = False
        return chain

    # ── Auto routing shortcut ──────────────────────────────────────────────
    async def run_auto(
        self,
        query: str,
        context: SkillContext,
        *,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        """Route ``query`` to the best skill and run it once.

        Returns :class:`SkillResult` with ``success=False`` and
        ``error="no matching skill"`` when routing fails.
        """
        chosen = self.route(query)
        if not chosen:
            return SkillResult.fail("no matching skill", skill_name="__auto__")
        return await self.run_skill(chosen, context, inputs=inputs)


# ── Helpers ─────────────────────────────────────────────────────────────────
def _short_preview(value: Any, limit: int = 120) -> Any:
    """Compact JSON-safe preview of a result for trace logs."""
    if value is None:
        return None
    if isinstance(value, str):
        return value[:limit] + ("…" if len(value) > limit else "")
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_short_preview(v, limit) for v in list(value)[:5]]
    if isinstance(value, dict):
        return {str(k): _short_preview(v, limit) for k, v in list(value.items())[:8]}
    return str(value)[:limit]


__all__ = [
    "SkillOrchestrator",
    "ChainStep",
    "ChainResult",
]