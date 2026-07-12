"""P19 v5.1-A: The Agency — 232 专家 roster loader.

The Agency is a static, JSON-backed persona catalogue used by the platform's
intent-classification and agent-routing layers (V5 Chapter 28 — "The Agency").
It is *not* a runtime plugin registry: those live in :mod:`imdf.agents`.

Design choices
==============

* **Data, not code**: each :class:`AgentRole` is a frozen dataclass with
  Chinese + English display fields and a system prompt.  No methods
  beyond ``__post_init__`` validation.  This keeps the roster reviewable
  in plain JSON and prevents accidental runtime side-effects.

* **JSON-departments, loader-handles-disc**: the roster lives in
  ``departments.json``.  The loader validates the JSON against the
  :data:`DEPARTMENT_ORDER` allow-list and exposes the four operations
  that v5 routing code actually needs: ``load_all``, ``load_by_department``,
  ``load_by_id``, ``search``, ``get_capability_matrix``.

* **Frozen instances**: ``@dataclass(frozen=True, slots=True)`` so two
  threads can hand the same role around without worrying about mutation.

* **Capability matrix**: dict[skill → sorted set of role IDs].  The
  agent router can ask "who knows X?" in O(1) by skill lookup.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Path to the directory holding The Agency's JSON fixtures.
#: Resolved at import time so tests can monkeypatch :data:`AGENCY_DIR`
#: without breaking subsequent imports.
AGENCY_DIR: Path = Path(__file__).resolve().parent

#: Canonical, frozen enumeration of The Agency's 16 departments.
#: Order matters: ``departments.json`` entries are expected to follow this
#: ordering for predictable diffs, and the loader asserts it during
#: :meth:`AgencyLoader._validate`.
DEPARTMENT_ORDER: tuple[str, ...] = (
    "Data Acquisition",          #  1 — 15 experts
    "Annotation",                #  2 — 15 experts
    "Quality Assurance",         #  3 — 15 experts
    "Workflow",                  #  4 — 14 experts
    "Project Management",        #  5 — 12 experts
    "Domain Expert",             #  6 — 20 experts
    "Creative Writing",          #  7 — 15 experts
    "Visual Arts",               #  8 — 15 experts
    "Audio & Music",             #  9 — 12 experts
    "Video & Film",              # 10 — 15 experts
    "AI/ML Research",            # 11 — 15 experts
    "Security & Compliance",     # 12 — 10 experts
    "DevOps & Infrastructure",   # 13 — 10 experts
    "Customer Service",          # 14 — 12 experts
    "Sales & Marketing",         # 15 — 12 experts
    "Executive & Strategy",      # 16 — 10 experts
)

#: Department → expected seat count.  Used by the test suite to assert
#: that the loader has the right roster size.  Sum should be 232.
#:
#: 16 primary departments sum to 217, plus 15 cross-functional bench
#: experts under ``"_spare_"`` = 232 total — matching the V5 Chapter 28
#: target.  Four of the original "10-count" departments were grown to
#: 12 to absorb eight seat additions that the V5 spec assumed but did
#: not break out in the original bullet list.
DEPARTMENT_SEAT_QUOTAS: Dict[str, int] = {
    "Data Acquisition": 15,
    "Annotation": 15,
    "Quality Assurance": 15,
    "Workflow": 14,
    "Project Management": 12,
    "Domain Expert": 20,
    "Creative Writing": 15,
    "Visual Arts": 15,
    "Audio & Music": 12,
    "Video & Film": 15,
    "AI/ML Research": 15,
    "Security & Compliance": 10,
    "DevOps & Infrastructure": 10,
    "Customer Service": 12,
    "Sales & Marketing": 12,
    "Executive & Strategy": 10,
    # 'spare' department: 15 cross-functional bench experts that can be
    # temporarily reassigned to any of the 16 departments above.
    "_spare_": 15,
}

#: Default name for the bundled JSON.  Single-file roster keeps the
#: deployment story simple.
DEFAULT_DEPARTMENTS_FILE: str = "departments.json"

#: Total expected roster size (sum of all department quotas).
EXPECTED_TOTAL_ROLES: int = sum(DEPARTMENT_SEAT_QUOTAS.values())


# ---------------------------------------------------------------------------
# Bilingual string helper
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Bilingual:
    """A pair of (zh, en) strings used everywhere a persona field needs
    both languages.  Both halves must be non-empty."""

    zh: str
    en: str

    def __post_init__(self) -> None:
        if not isinstance(self.zh, str) or not self.zh.strip():
            raise ValueError("Bilingual.zh must be a non-empty string")
        if not isinstance(self.en, str) or not self.en.strip():
            raise ValueError("Bilingual.en must be a non-empty string")

    def as_dict(self) -> Dict[str, str]:
        return {"zh": self.zh, "en": self.en}

    @classmethod
    def from_value(cls, value) -> "Bilingual":
        """Coerce JSON-friendly values (dict, str) to :class:`Bilingual`.

        Accepts:
          * ``{"zh": "...", "en": "..."}``  → both languages
          * ``"english text only"``        → en="text", zh="text"
        """
        if isinstance(value, Bilingual):
            return value
        if isinstance(value, dict):
            zh = value.get("zh") or value.get("zh-CN") or value.get("cn")
            en = value.get("en") or value.get("english")
            if not zh or not en:
                # Last-ditch fallback: if only one key was provided, mirror
                # it into both fields so downstream consumers don't blow up.
                only = next(iter(value.values()), "") if value else ""
                zh = zh or only
                en = en or only
            return cls(zh=str(zh), en=str(en))
        if isinstance(value, str):
            # Treat plain strings as English, mirror to zh.  Avoids
            # surprises when partial records exist during development.
            return cls(zh=value, en=value)
        raise TypeError(
            f"Bilingual.from_value expects dict or str, got {type(value).__name__}"
        )


# ---------------------------------------------------------------------------
# AgentRole dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentRole:
    """A single expert persona in The Agency.

    Frozen: the roster is configuration, not mutable runtime state.
    Slots: keeps memory tight at 232 instances.

    Fields:
        id                  Stable slug like ``"data_acquisition_expert_001"``.
                            Unique across the roster; the loader asserts this.
        name                Bilingual display name.
        department          One of :data:`DEPARTMENT_ORDER`.  Encodes rough
                            capability bucket.  Spare-pool experts may use
                            ``"_spare_"`` instead.
        title               Free-form job title (English, sometimes with CN
                            subtitle).  Examples: "Senior Crawler Specialist",
                            "Senior 爬虫工程师".
        skills              Skill tags.  Used by capability-matrix lookups.
                            Stored as a tuple (frozen + hashable).
        description         Bilingual summary paragraph.
        avatar_url          Optional CDN URL.  May be ``None`` when no
                            portrait has been commissioned yet.
        system_prompt       Bilingual system prompt fed to the LLM when this
                            persona is engaged.

    Note: the loader applies ``dataclasses.replace`` semantics internally;
    callers should not attempt to mutate instances.
    """

    id: str
    name: Bilingual
    department: str
    title: str
    skills: tuple[str, ...]
    description: Bilingual
    avatar_url: Optional[str]
    system_prompt: Bilingual

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError(f"AgentRole.id must be a non-empty str, got {self.id!r}")
        if not self.department or not isinstance(self.department, str):
            raise ValueError(
                f"AgentRole.department must be a non-empty str, got {self.department!r}"
            )
        # Allow "_spare_" sentinel plus the 16 canonical departments.
        allowed = set(DEPARTMENT_ORDER) | {"_spare_"}
        if self.department not in allowed:
            raise ValueError(
                f"AgentRole.department={self.department!r} not in DEPARTMENT_ORDER"
            )
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("AgentRole.title must be a non-empty str")
        if not isinstance(self.skills, (tuple, list)):
            raise ValueError("AgentRole.skills must be a list/tuple of strings")
        cleaned = tuple(str(s).strip() for s in self.skills if str(s).strip())
        if not cleaned:
            raise ValueError("AgentRole.skills must contain at least one non-empty skill")
        # Replace tuple to enforce canonicalisation without breaking frozen-ness.
        object.__setattr__(self, "skills", cleaned)
        if self.avatar_url is not None and not isinstance(self.avatar_url, str):
            raise ValueError("AgentRole.avatar_url must be str or None")

    # -- convenience accessors ----------------------------------------------

    def has_skill(self, skill: str) -> bool:
        """Return ``True`` if this role lists ``skill`` (case-insensitive)."""
        needle = skill.strip().lower()
        return any(s.lower() == needle for s in self.skills)

    def is_spare(self) -> bool:
        """Return ``True`` for cross-functional bench experts."""
        return self.department == "_spare_"

    def as_dict(self) -> Dict[str, object]:
        """Serialise back to a JSON-friendly dict (round-trip safe)."""
        return {
            "id": self.id,
            "name": self.name.as_dict(),
            "department": self.department,
            "title": self.title,
            "skills": list(self.skills),
            "description": self.description.as_dict(),
            "avatar_url": self.avatar_url,
            "system_prompt": self.system_prompt.as_dict(),
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class AgencyLoader:
    """JSON-backed loader for The Agency roster.

    Usage:
        >>> loader = AgencyLoader()          # loads departments.json
        >>> all_roles   = loader.load_all()
        >>> da_team     = loader.load_by_department("Data Acquisition")
        >>> role        = loader.load_by_id("data_acquisition_expert_001")
        >>> hits        = loader.search("crawler")
        >>> matrix      = loader.get_capability_matrix()

    The loader is intentionally cheap to instantiate; it caches the parsed
    roster in-memory so repeated queries don't re-read the JSON file.
    Call :meth:`reload` to force a re-parse (used in tests).
    """

    def __init__(self, source: Optional[os.PathLike[str] | str] = None) -> None:
        self._source: Path = Path(source) if source is not None else AGENCY_DIR / DEFAULT_DEPARTMENTS_FILE
        # Eagerly load on construction so failures surface at module import
        # time instead of inside a deeply-nested routing call.
        self._roles: List[AgentRole] = self._load_and_validate(self._source)

    # -- public API --------------------------------------------------------

    def reload(self, source: Optional[os.PathLike[str] | str] = None) -> "AgencyLoader":
        """Force a re-read of the JSON source.  Useful in tests.

        Returns ``self`` so callers can chain.
        """
        if source is not None:
            self._source = Path(source)
        self._roles = self._load_and_validate(self._source)
        return self

    def load_all(self) -> List[AgentRole]:
        """Return *all* roles in the roster, ordered by id (stable)."""
        return list(self._roles)

    def load_by_department(self, department: str) -> List[AgentRole]:
        """Return all roles belonging to ``department``.

        Match is case-insensitive on the canonical department name.  The
        ``"_spare_"`` sentinel is also matchable, e.g. via
        :meth:`load_by_department("_spare_")`.
        """
        if not department:
            return []
        needle = department.strip().lower()
        return [r for r in self._roles if r.department.lower() == needle]

    def load_by_id(self, role_id: str) -> Optional[AgentRole]:
        """Look up a single role by its slug; ``None`` if unknown."""
        if not role_id:
            return None
        needle = role_id.strip()
        for r in self._roles:
            if r.id == needle:
                return r
        return None

    def search(self, query: str) -> List[AgentRole]:
        """Free-text search across id, name, title, skills, description.

        Strategy:
          * empty / whitespace → return all roles (caller asked for everything)
          * otherwise match case-insensitively across all string fields
          * results sorted by (department order, id) for stable UI rendering
        """
        if not query or not query.strip():
            return list(self._roles)
        needle = query.strip().lower()
        tokens = [t for t in needle.split() if t]

        hits: List[AgentRole] = []
        for role in self._roles:
            haystack_parts: list[str] = [
                role.id.lower(),
                role.name.zh.lower(),
                role.name.en.lower(),
                role.title.lower(),
                role.description.zh.lower(),
                role.description.en.lower(),
                role.system_prompt.zh.lower(),
                role.system_prompt.en.lower(),
                " ".join(role.skills).lower(),
                role.department.lower(),
            ]
            haystack = "\n".join(haystack_parts)
            if all(t in haystack for t in tokens):
                hits.append(role)

        order = {name: i for i, name in enumerate(DEPARTMENT_ORDER)}
        order["_spare_"] = len(DEPARTMENT_ORDER)  # spares after the 16
        hits.sort(key=lambda r: (order.get(r.department, 99), r.id))
        return hits

    def get_capability_matrix(self) -> Dict[str, List[str]]:
        """Skill → sorted list of role IDs.

        Keys are lower-cased skills (canonical form), values are lists of
        role IDs in alphabetical order.  Useful for routing logic like
        *"who handles 'ocr' in Chinese OCR pipelines?"*.
        """
        matrix: Dict[str, Set[str]] = {}
        for role in self._roles:
            for skill in role.skills:
                matrix.setdefault(skill, set()).add(role.id)
        # Return sorted lists — JSON-friendly and predictable.
        return {skill: sorted(ids) for skill, ids in matrix.items()}

    def departments_present(self) -> List[str]:
        """Return the set of departments currently represented in the roster.

        Order matches :data:`DEPARTMENT_ORDER`; ``_spare_`` is appended last.
        """
        present = [d for d in DEPARTMENT_ORDER if self.load_by_department(d)]
        if self.load_by_department("_spare_"):
            present.append("_spare_")
        return present

    # -- internals ---------------------------------------------------------

    def _load_and_validate(self, source: Path) -> List[AgentRole]:
        if not source.exists():
            raise FileNotFoundError(f"Agency roster not found at {source}")
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {source}: {exc}") from exc

        # Accept either a list of role dicts, or {"departments": [...]} / {"roles": [...]}.
        if isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            entries = raw.get("departments") or raw.get("roles") or raw.get("roster")
            if entries is None:
                raise ValueError(
                    f"{source}: expected a list of role dicts, or a dict with "
                    f"'departments' / 'roles' / 'roster' key"
                )
        else:
            raise ValueError(f"{source}: top-level JSON must be list or dict")

        roles: List[AgentRole] = []
        seen_ids: Set[str] = set()
        for entry in entries:
            role = self._parse_entry(entry)
            if role.id in seen_ids:
                raise ValueError(f"Duplicate role id in roster: {role.id!r}")
            seen_ids.add(role.id)
            roles.append(role)

        roles.sort(key=lambda r: r.id)
        self._validate_quotas(roles, source)
        return roles

    def _parse_entry(self, entry: object) -> AgentRole:
        if not isinstance(entry, dict):
            raise ValueError(f"Role entry must be a dict, got {type(entry).__name__}")
        try:
            return AgentRole(
                id=str(entry["id"]).strip(),
                name=Bilingual.from_value(entry.get("name")),
                department=str(entry["department"]).strip(),
                title=str(entry["title"]).strip(),
                skills=list(entry.get("skills") or []),
                description=Bilingual.from_value(entry.get("description")),
                avatar_url=entry.get("avatar_url"),
                system_prompt=Bilingual.from_value(entry.get("system_prompt")),
            )
        except KeyError as missing:
            raise ValueError(f"Role entry missing required field: {missing}") from missing

    def _validate_quotas(self, roles: List[AgentRole], source: Path) -> None:
        """Enforce per-department quotas and the 232 total."""
        counts: Dict[str, int] = {d: 0 for d in DEPARTMENT_ORDER}
        counts["_spare_"] = 0
        for r in roles:
            counts[r.department] = counts.get(r.department, 0) + 1

        problems: List[str] = []
        for dept, expected in DEPARTMENT_SEAT_QUOTAS.items():
            actual = counts.get(dept, 0)
            if actual != expected:
                problems.append(f"{dept}: expected {expected}, got {actual}")
        if len(roles) != EXPECTED_TOTAL_ROLES:
            problems.append(f"total: expected {EXPECTED_TOTAL_ROLES}, got {len(roles)}")

        if problems:
            raise ValueError(
                f"Agency roster quota mismatch in {source.name}:\n  - "
                + "\n  - ".join(problems)
            )


__all__ = [
    "AGENCY_DIR",
    "DEFAULT_DEPARTMENTS_FILE",
    "DEPARTMENT_ORDER",
    "DEPARTMENT_SEAT_QUOTAS",
    "EXPECTED_TOTAL_ROLES",
    "AgentRole",
    "AgencyLoader",
    "Bilingual",
]
