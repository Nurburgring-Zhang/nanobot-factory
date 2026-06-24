"""P4-8-W1: SkillRegistry — catalogue of available skills.

The :class:`SkillRegistry` is a singleton-ish registry that supports:

  * registration by class (auto via ``@skill`` decorator) or by instance
    (for community / runtime-installed skills)
  * lookup by name (latest) or by name + version
  * listing with category / tag filters
  * statistics

The module also exposes :data:`SKILL_REGISTRY`, the default registry that
the ``@skill`` decorator imports and that ``SkillOrchestrator`` uses.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .base import Skill, SkillCategory, SkillMetadata

logger = logging.getLogger(__name__)


@dataclass
class _RegistryEntry:
    cls: type
    instance: Optional[Skill]
    meta: SkillMetadata

    def to_dict(self) -> Dict[str, object]:
        out = self.meta.to_dict()
        out["class"] = f"{self.cls.__module__}.{self.cls.__name__}"
        out["instantiated"] = self.instance is not None
        return out


class SkillRegistry:
    """Thread-safe in-memory skill catalogue."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_name: Dict[str, Dict[str, _RegistryEntry]] = {}
        self._stats = {"register": 0, "lookup": 0, "miss": 0}

    # ── Internal helpers ───────────────────────────────────────────────────
    def _register_class(self, cls: type, meta: SkillMetadata) -> None:
        if not issubclass(cls, Skill):
            raise TypeError(f"{cls!r} is not a Skill subclass")
        with self._lock:
            bucket = self._by_name.setdefault(meta.name, {})
            if meta.version in bucket:
                # Allow re-registration only if version differs.
                existing = bucket[meta.version]
                if existing.cls is cls:
                    return
                logger.debug(
                    "overwriting skill %s v%s (was %s)",
                    meta.name, meta.version, existing.cls,
                )
            bucket[meta.version] = _RegistryEntry(cls=cls, instance=None, meta=meta)
            self._stats["register"] += 1
            logger.info("registry: registered skill %s v%s", meta.name, meta.version)

    # ── Public API ─────────────────────────────────────────────────────────
    def register_instance(self, skill: Skill, meta: Optional[SkillMetadata] = None) -> None:
        """Register an already-instantiated skill (community upload path)."""
        m = meta or getattr(skill, "__skill_meta__", None)
        if m is None:
            raise ValueError("Skill must carry __skill_meta__ or pass meta explicitly")
        cls = type(skill)
        with self._lock:
            bucket = self._by_name.setdefault(m.name, {})
            bucket[m.version] = _RegistryEntry(cls=cls, instance=skill, meta=m)
            self._stats["register"] += 1
            logger.info("registry: registered instance %s v%s", m.name, m.version)

    def unregister(self, name: str, version: Optional[str] = None) -> bool:
        with self._lock:
            if name not in self._by_name:
                return False
            if version is None:
                del self._by_name[name]
                return True
            bucket = self._by_name[name]
            if version in bucket:
                del bucket[version]
                if not bucket:
                    del self._by_name[name]
                return True
            return False

    def has(self, name: str, version: Optional[str] = None) -> bool:
        with self._lock:
            if name not in self._by_name:
                return False
            if version is None:
                return True
            return version in self._by_name[name]

    def get(self, name: str, version: Optional[str] = None) -> Skill:
        """Return a live Skill instance (cached)."""
        with self._lock:
            self._stats["lookup"] += 1
            bucket = self._by_name.get(name)
            if not bucket:
                self._stats["miss"] += 1
                raise KeyError(f"skill not found: {name}")
            entry = self._select_entry(bucket, version)
            if entry.instance is None:
                # Lazy-instantiate.
                entry.instance = entry.cls()
            return entry.instance

    def meta(self, name: str, version: Optional[str] = None) -> SkillMetadata:
        with self._lock:
            bucket = self._by_name.get(name)
            if not bucket:
                raise KeyError(f"skill not found: {name}")
            entry = self._select_entry(bucket, version)
            return entry.meta

    def _select_entry(self, bucket: Dict[str, _RegistryEntry], version: Optional[str]) -> _RegistryEntry:
        if version is not None:
            if version not in bucket:
                raise KeyError(f"skill version not found: {version}")
            return bucket[version]
        # Pick the highest semver (string compare is fine for our versions).
        best_version = max(bucket.keys())
        return bucket[best_version]

    # ── Listing / search ───────────────────────────────────────────────────
    def list(
        self,
        category: Optional[SkillCategory] = None,
        tag: Optional[str] = None,
        *,
        include_community: bool = True,
    ) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        with self._lock:
            for name, bucket in self._by_name.items():
                entry = self._select_entry(bucket, None)
                if category is not None and entry.meta.category != category:
                    continue
                if tag and tag not in entry.meta.tags:
                    continue
                if not include_community and not entry.meta.builtin:
                    continue
                out.append(entry.to_dict())
        out.sort(key=lambda d: (str(d["category"]), str(d["name"])))
        return out

    def search(self, query: str) -> List[Dict[str, object]]:
        """Substring search across name, description, tags."""
        q = (query or "").strip().lower()
        if not q:
            return self.list()
        hits: List[Dict[str, object]] = []
        for d in self.list():
            blob = " ".join([
                str(d.get("name", "")), str(d.get("description", "")),
                " ".join(d.get("tags", []) or []),
            ]).lower()
            if q in blob:
                hits.append(d)
        return hits

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._by_name.keys())

    def categories_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {c.value: 0 for c in SkillCategory}
        for d in self.list():
            cat = str(d.get("category", ""))
            if cat in summary:
                summary[cat] += 1
        return summary

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_name)

    def __contains__(self, name: str) -> bool:
        return self.has(name)


# ── Module-level singleton ──────────────────────────────────────────────────
SKILL_REGISTRY = SkillRegistry()
"""The default skill registry, used by ``@skill`` and ``SkillOrchestrator``."""


__all__ = ["SkillRegistry", "SKILL_REGISTRY"]