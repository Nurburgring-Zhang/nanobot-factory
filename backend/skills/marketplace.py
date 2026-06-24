"""P4-8-W1: Skill marketplace — install / rate / community catalogue.

A lightweight Skill marketplace modelled on VS Code extensions + Hugging
Face model hub:

  * Official 10 skills (already registered via :mod:`skills.builtin`)
  * Community skills uploaded by users (YAML manifest + Python code)
  * Rating + downloads + reviews

Storage is in-memory + a JSON file under the platform's ``imdf`` data
dir; production deployments can swap in a SQLite table without touching
the API surface.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .base import SkillCategory
from .registry import SKILL_REGISTRY

logger = logging.getLogger(__name__)


# ── Rating / Review records ──────────────────────────────────────────────────
@dataclass
class SkillRating:
    skill_id: str
    user_id: str
    stars: int            # 1-5
    review: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillEntry:
    """Marketplace catalog entry."""

    id: str
    name: str
    description: str
    category: str
    version: str = "1.0.0"
    author: str = "community"
    tags: List[str] = field(default_factory=list)
    downloads: int = 0
    rating_sum: int = 0
    rating_count: int = 0
    source_path: str = ""
    builtin: bool = False
    created_at: float = field(default_factory=time.time)

    @property
    def rating_avg(self) -> float:
        if self.rating_count <= 0:
            return 0.0
        return round(self.rating_sum / self.rating_count, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rating_avg"] = self.rating_avg
        return d


# ── Marketplace ──────────────────────────────────────────────────────────────
class SkillMarketplace:
    """In-memory marketplace backed by an optional JSON file."""

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._entries: Dict[str, SkillEntry] = {}
        self._ratings: List[SkillRating] = []
        self._lock = threading.RLock()
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    # ── Catalog management ─────────────────────────────────────────────────
    def publish(self, entry: SkillEntry) -> SkillEntry:
        with self._lock:
            if entry.id in self._entries:
                # Bump version if name already exists.
                existing = self._entries[entry.id]
                existing.version = entry.version
                existing.description = entry.description
                existing.tags = list(entry.tags)
                self._save()
                return existing
            self._entries[entry.id] = entry
            self._save()
            return entry

    def unpublish(self, skill_id: str) -> bool:
        with self._lock:
            if skill_id in self._entries:
                del self._entries[skill_id]
                self._save()
                return True
            return False

    def get(self, skill_id: str) -> Optional[SkillEntry]:
        return self._entries.get(skill_id)

    def list(
        self,
        category: Optional[SkillCategory] = None,
        query: Optional[str] = None,
        *,
        include_builtin: bool = True,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            entries = list(self._entries.values())
        if category is not None:
            cat = category.value if isinstance(category, SkillCategory) else str(category)
            entries = [e for e in entries if e.category == cat]
        if not include_builtin:
            entries = [e for e in entries if not e.builtin]
        if query:
            q = query.lower()
            entries = [
                e for e in entries
                if q in e.name.lower() or q in e.description.lower()
                or any(q in t.lower() for t in e.tags)
            ]
        # Built-in skills first.
        entries.sort(key=lambda e: (not e.builtin, -e.downloads, e.name))
        return [e.to_dict() for e in entries]

    def search(self, query: str) -> List[Dict[str, Any]]:
        return self.list(query=query)

    # ── Install / rate ─────────────────────────────────────────────────────
    def install(self, skill_id: str) -> Dict[str, Any]:
        with self._lock:
            entry = self._entries.get(skill_id)
            if not entry:
                return {"success": False, "error": f"unknown skill: {skill_id}"}
            entry.downloads += 1
            self._save()
            return {
                "success": True,
                "skill_id": skill_id,
                "version": entry.version,
                "downloads": entry.downloads,
                "source_path": entry.source_path,
                "already_registered": skill_id in SKILL_REGISTRY,
            }

    def rate(self, skill_id: str, user_id: str, stars: int, review: str = "") -> Dict[str, Any]:
        if not 1 <= stars <= 5:
            return {"success": False, "error": "stars must be 1-5"}
        with self._lock:
            entry = self._entries.get(skill_id)
            if not entry:
                return {"success": False, "error": f"unknown skill: {skill_id}"}
            self._ratings.append(SkillRating(
                skill_id=skill_id, user_id=user_id, stars=stars, review=review,
            ))
            entry.rating_sum += stars
            entry.rating_count += 1
            self._save()
            return {
                "success": True,
                "skill_id": skill_id,
                "new_rating_avg": entry.rating_avg,
                "rating_count": entry.rating_count,
            }

    def reviews(self, skill_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._ratings if r.skill_id == skill_id]

    # ── Snapshot of registry → marketplace ────────────────────────────────
    def sync_from_registry(self) -> int:
        """Publish every registered skill into the marketplace (idempotent)."""
        added = 0
        with self._lock:
            for info in SKILL_REGISTRY.list():
                skill_id = info["name"]
                if skill_id in self._entries:
                    continue
                entry = SkillEntry(
                    id=skill_id,
                    name=str(info["name"]),
                    description=str(info.get("description", "")),
                    category=str(info.get("category", "productivity")),
                    version=str(info.get("version", "1.0.0")),
                    author=str(info.get("author", "builtin")),
                    tags=list(info.get("tags") or []),
                    builtin=bool(info.get("builtin", True)),
                )
                self._entries[skill_id] = entry
                added += 1
            self._save()
            return added

    # ── Persistence helpers ────────────────────────────────────────────────
    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            payload = {
                "entries": [e.to_dict() for e in self._entries.values()],
                "ratings": [r.to_dict() for r in self._ratings],
            }
            with open(self._persist_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except OSError as exc:  # noqa: BLE001
            logger.warning("marketplace save failed: %s", exc)

    def _load(self) -> None:
        try:
            with open(self._persist_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for raw in payload.get("entries", []):
            e = SkillEntry(
                id=raw["id"],
                name=raw["name"],
                description=raw.get("description", ""),
                category=raw.get("category", "productivity"),
                version=raw.get("version", "1.0.0"),
                author=raw.get("author", "community"),
                tags=list(raw.get("tags") or []),
                downloads=int(raw.get("downloads", 0)),
                rating_sum=int(raw.get("rating_sum", 0)),
                rating_count=int(raw.get("rating_count", 0)),
                source_path=raw.get("source_path", ""),
                builtin=bool(raw.get("builtin", False)),
                created_at=float(raw.get("created_at", time.time())),
            )
            self._entries[e.id] = e
        for raw in payload.get("ratings", []):
            self._ratings.append(SkillRating(
                skill_id=raw["skill_id"],
                user_id=raw["user_id"],
                stars=int(raw["stars"]),
                review=raw.get("review", ""),
                created_at=float(raw.get("created_at", time.time())),
            ))


# ── Singleton + helpers ──────────────────────────────────────────────────────
_MARKETPLACE: Optional[SkillMarketplace] = None
_MP_LOCK = threading.Lock()


def get_marketplace(persist_path: Optional[str] = None) -> SkillMarketplace:
    global _MARKETPLACE
    with _MP_LOCK:
        if _MARKETPLACE is None:
            path = persist_path or os.environ.get(
                "NANOBOT_SKILLS_MARKETPLACE",
                os.path.join(os.path.expanduser("~"), ".nanobot", "skill_marketplace.json"),
            )
            _MARKETPLACE = SkillMarketplace(persist_path=path)
            # First-run: publish the 10 built-in skills so the marketplace is
            # never empty.
            _MARKETPLACE.sync_from_registry()
        return _MARKETPLACE


def reset_marketplace_for_test() -> None:
    global _MARKETPLACE
    with _MP_LOCK:
        _MARKETPLACE = None


def new_community_skill(
    name: str,
    description: str,
    category: str,
    *,
    tags: Optional[List[str]] = None,
    author: str = "community",
) -> SkillEntry:
    return SkillEntry(
        id=name,
        name=name,
        description=description,
        category=category,
        tags=list(tags or []),
        author=author,
        source_path=f"community://{uuid.uuid4().hex[:8]}/{name}",
    )


__all__ = [
    "SkillEntry",
    "SkillRating",
    "SkillMarketplace",
    "get_marketplace",
    "reset_marketplace_for_test",
    "new_community_skill",
]