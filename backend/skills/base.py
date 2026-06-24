"""P4-8-W1: Skill base class + ``@skill`` decorator.

A :class:`Skill` is the second-generation building block of the platform's
AI workflow:

    Skill
        ↑   ABC with name / description / category / version / dependencies
        │   execute(context: SkillContext) -> SkillResult
        │
        ├── BuiltinSkill (10 official skills, this package)
        └── CommunitySkill (downloaded from marketplace)

The ``@skill`` decorator is the sugar used everywhere in ``builtin/``::

    @skill(name="guizang_ppt", category="content", version="1.0.0",
           dependencies=[])
    class GuizangPPTSkill(Skill):
        async def execute(self, ctx: SkillContext) -> SkillResult: ...

The decorator registers the class in the default :data:`SKILL_REGISTRY`
singleton at import time so ``SkillRegistry.list()`` immediately sees it.
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Category enum ────────────────────────────────────────────────────────────
class SkillCategory(str, Enum):
    """Top-level skill categories used by both registry and marketplace."""

    CONTENT = "content"           # articles, books, copywriting
    RESEARCH = "research"         # deep-research, fact-check
    DATA = "data"                 # csv, json, ETL
    CODE = "code"                 # codegen, review, refactor
    IMAGE = "image"               # prompt libraries, generation
    VIDEO = "video"               # clip extraction, edit
    PRODUCTIVITY = "productivity" # calendar, email, todos
    MARKETING = "marketing"       # SEO, ads, growth
    KNOWLEDGE = "knowledge"       # wiki, RAG, graph


ALL_CATEGORIES: List[SkillCategory] = list(SkillCategory)


# ── Decorator state ──────────────────────────────────────────────────────────
@dataclass
class SkillMetadata:
    name: str
    description: str
    category: SkillCategory
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    author: str = "builtin"
    source: str = ""
    builtin: bool = True
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value if isinstance(self.category, SkillCategory) else str(self.category),
            "version": self.version,
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
            "author": self.author,
            "source": self.source,
            "builtin": self.builtin,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
        }


# ── Decorator ────────────────────────────────────────────────────────────────
def skill(
    name: str,
    description: str = "",
    category: SkillCategory = SkillCategory.PRODUCTIVITY,
    version: str = "1.0.0",
    dependencies: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    author: str = "builtin",
    source: str = "",
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> Callable[[type], type]:
    """Class decorator that tags a Skill subclass and registers it globally.

    The decorated class must inherit from :class:`Skill`.  After decoration,
    the class carries a ``__skill_meta__`` attribute holding a
    :class:`SkillMetadata`, and is also added to :data:`SKILL_REGISTRY`.
    """
    def _wrap(cls: type) -> type:
        if not inspect.isclass(cls):
            raise TypeError("@skill can only decorate classes")
        if not issubclass(cls, Skill):
            raise TypeError(f"@skill requires Skill subclass, got {cls!r}")
        meta = SkillMetadata(
            name=name,
            description=description or (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else "",
            category=category,
            version=version,
            dependencies=list(dependencies or []),
            tags=list(tags or []),
            author=author,
            source=source,
            builtin=True,
            input_schema=dict(input_schema or {}),
            output_schema=dict(output_schema or {}),
        )
        cls.__skill_meta__ = meta  # type: ignore[attr-defined]
        # Lazy import to avoid circular: registry.py imports this module.
        from .registry import SKILL_REGISTRY
        SKILL_REGISTRY._register_class(cls, meta)
        logger.debug("registered skill %s v%s (%s)", name, version, category)
        return cls
    return _wrap


# ── Abstract base ────────────────────────────────────────────────────────────
class Skill(ABC):
    """Base class for every skill (built-in or community-uploaded)."""

    # Populated by ``@skill`` decorator.
    __skill_meta__: SkillMetadata  # type: ignore[assignment]

    def __init__(self) -> None:
        self._llm: Optional[Any] = None  # injected via set_llm()
        self._metrics: Dict[str, int] = {
            "calls": 0,
            "success": 0,
            "failure": 0,
            "total_ms": 0,
        }

    # ── Lifecycle hooks ────────────────────────────────────────────────────
    def set_llm(self, llm: Any) -> None:
        """Inject the LLM client.  Optional — skills degrade to mock mode."""
        self._llm = llm

    async def setup(self) -> None:  # pragma: no cover - optional hook
        """One-shot async setup (e.g. load resources).  Default: no-op."""
        return None

    async def teardown(self) -> None:  # pragma: no cover - optional hook
        """One-shot async teardown."""
        return None

    # ── Required entry point ───────────────────────────────────────────────
    @abstractmethod
    async def execute(self, context: "SkillContext") -> "SkillResult":
        """Run the skill with the supplied context and return a SkillResult."""
        raise NotImplementedError

    # ── Helpers used by subclasses ─────────────────────────────────────────
    def call_llm(self, prompt: str, *, system: str = "", **kwargs: Any) -> str:
        """Call the injected LLM.  Falls back to a deterministic stub."""
        self._metrics["calls"] += 1
        if self._llm is None:
            return _mock_llm_response(prompt, getattr(self, "__skill_meta__", None))
        try:
            text = self._llm.generate(prompt=prompt, system=system, **kwargs)
            if not isinstance(text, str):
                text = str(text)
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed for %s: %s — falling back to mock",
                           getattr(self.__skill_meta__, "name", "?"), exc)
            return _mock_llm_response(prompt, getattr(self, "__skill_meta__", None))

    def metrics_snapshot(self) -> Dict[str, int]:
        return dict(self._metrics)

    @property
    def meta(self) -> SkillMetadata:
        return self.__skill_meta__


# ── Mock LLM helper ─────────────────────────────────────────────────────────
def _mock_llm_response(prompt: str, meta: Optional[SkillMetadata]) -> str:
    """Deterministic placeholder used when no real LLM is wired in.

    Tests assert on the leading marker so a real LLM call is easy to spot.
    """
    skill_name = meta.name if meta else "skill"
    head = (prompt or "").strip().splitlines()[0][:80] if prompt else ""
    return f"[mock:{skill_name}] echo head='{head}' len={len(prompt or '')}"


# ── Schema introspection for execute() signature ────────────────────────────
def inspect_input_schema(cls: type) -> Dict[str, Any]:
    """Best-effort JSON Schema for ``execute(ctx, **kwargs)`` signature."""
    try:
        sig = inspect.signature(cls.execute)
    except (TypeError, ValueError):
        return {"type": "object", "additionalProperties": True}
    params = list(sig.parameters.values())
    if not params:
        return {"type": "object", "additionalProperties": True}
    # The first parameter is the SkillContext (positional); extras are kwargs.
    extras = params[1:]
    if not extras:
        return {"type": "object", "additionalProperties": False}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for p in extras:
        ann = p.annotation
        js_type = "string"
        if ann in (int,):
            js_type = "integer"
        elif ann in (float,):
            js_type = "number"
        elif ann in (bool,):
            js_type = "boolean"
        elif ann in (list, List):
            js_type = "array"
        elif ann in (dict, Dict):
            js_type = "object"
        properties[p.name] = {"type": js_type, "description": f"Argument {p.name}"}
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    return {"type": "object", "properties": properties, "required": required}


__all__ = [
    "Skill",
    "SkillCategory",
    "SkillMetadata",
    "ALL_CATEGORIES",
    "skill",
    "inspect_input_schema",
]