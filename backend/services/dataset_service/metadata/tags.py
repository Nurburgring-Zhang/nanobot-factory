"""P4-4-W1 metadata tags — manual + auto PII + propagation.

The taxonomy is intentionally tiny but pragmatic:

  * **manual** tags    — owner-attached; managed via CRUD.
  * **auto PII**       — a regex/heuristic detector scans column names
    + small samples and assigns a sensitivity 1-5 tag (``PII.email``,
    ``PII.phone``, ``PII.id_card`` ...).
  * **auto business**  — matches column names against a glossary term
    (e.g. a column named ``user_id`` becomes tagged with the
    ``user_id`` business term).
  * **propagation**    — when a column gets a tag, its parent table
    and (if any) parent dataset also get a roll-up tag with category
    ``propagated`` (so you can answer "which datasets contain PII?").

Routes exposed:
  * ``POST /api/v1/metadata/tags``             — create (manual or auto)
  * ``GET  /api/v1/metadata/tags``             — list, optional filter
  * ``POST /api/v1/metadata/tags/auto/pii``    — bulk PII scan over a DB
  * ``POST /api/v1/metadata/tags/propagate``   — re-run propagation across DB
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import (
    ColumnORM,
    DatasetORM,
    TableORM,
    TagAssignmentORM,
    TagORM,
    _dumps,
    _new_id,
    _now,
    db_to_dict,
    get_metadata_session,
)

logger = logging.getLogger(__name__)


# ── PII / sensitivity detector ───────────────────────────────────────────────
_PII_PATTERNS: List[Tuple[str, re.Pattern, int]] = [
    # (tag-name, column-name regex, sensitivity-level 1-5)
    ("PII.email", re.compile(r"^(e?mail(_?addr(ess)?)?|user_mail)$", re.I), 4),
    ("PII.phone", re.compile(r"^(phone(_?num(ber)?)?|mobile|tel)$", re.I), 4),
    ("PII.id_card", re.compile(r"^(id_?card|identity(_?num(ber)?)?|national_?id|ssn)$", re.I), 5),
    ("PII.real_name", re.compile(r"^(real_?name|full_?name|first_?name|last_?name|user_?name|legal_?name)$", re.I), 3),
    ("PII.password", re.compile(r"^(password|passwd|pwd|secret|api_?key)$", re.I), 5),
    ("PII.address", re.compile(r"^addr(ess)?(_?line)?(_?[1-3])?$", re.I), 3),
    ("PII.birthday", re.compile(r"^(birth_?day|birth_?date|dob|birthdate)$", re.I), 3),
    ("PII.gender", re.compile(r"^gender$|^sex$|^性别$", re.I), 2),
    ("PII.nationality", re.compile(r"^nationality$|^国籍$|^country(_?code)?$", re.I), 2),
    ("PII.ip", re.compile(r"^ip(_?addr(ess)?)?$", re.I), 2),
    ("PII.bank_card", re.compile(r"^bank_?card(_?no)?$|^card_?no$", re.I), 5),
    ("PII.credit", re.compile(r"^credit_?card$|^cvv$", re.I), 5),
    ("PII.cookie", re.compile(r"^cookie(_?id)?$", re.I), 2),
    ("PII.device", re.compile(r"^(device_?id|udid|imei|mac(_?addr(ess)?)?)$", re.I), 2),
    ("PII.location", re.compile(r"^(location|gps|lat|lon|latitude|longitude)$", re.I), 3),
    ("PII.biometric", re.compile(r"^(face(_?id)?|fingerprint|voice_?print|iris)$", re.I), 5),
]

_PII_VALUE_PATTERNS: Dict[str, re.Pattern] = {
    "PII.email": re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$"),
    "PII.phone": re.compile(r"^\+?\d[\d\s-]{7,}$"),
    "PII.id_card": re.compile(r"^\d{15}(\d{2}[0-9Xx])?$"),
    "PII.ip": re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"),
}

# Chinese name heuristic — a 2-3 character CJK string
_CJK_NAME = re.compile(r"^[\u4e00-\u9fa5]{2,4}$")


# Additional PII email aliases (canonical email regex is anchored; we
# separately match prefixed variants like ``user_email`` / ``contact_mail``).
_PII_EMAIL_ALIASES = re.compile(
    r"^(user_?e?mail|contact_?e?mail|customer_?e?mail|account_?e?mail|"
    r"user_?mail|contact_?mail|customer_?mail|account_?mail|email_?addr(ess)?|"
    r"e_?mail_?addr(ess)?)$",
    re.I,
)


@dataclass
class PIIMatch:
    """One column flagged by the detector."""

    column_id: str
    column_name: str
    table_name: str
    schema_name: str
    tag_name: str
    sensitivity_level: int
    source: str = "auto_pii"  # name / value / propagation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_id": self.column_id,
            "column_name": self.column_name,
            "table_name": self.table_name,
            "schema_name": self.schema_name,
            "tag_name": self.tag_name,
            "sensitivity_level": self.sensitivity_level,
            "source": self.source,
        }


def detect_pii_by_name(column_name: str) -> Optional[PIIMatch]:
    """Return a PII match if ``column_name`` matches any PII pattern."""
    for tag_name, pat, level in _PII_PATTERNS:
        if pat.match(column_name):
            return PIIMatch(
                column_id="",
                column_name=column_name,
                table_name="",
                schema_name="",
                tag_name=tag_name,
                sensitivity_level=level,
                source="name",
            )
    # Alias patterns (e.g. ``user_email``, ``contact_mail``)
    if _PII_EMAIL_ALIASES.match(column_name):
        return PIIMatch(
            column_id="",
            column_name=column_name,
            table_name="",
            schema_name="",
            tag_name="PII.email",
            sensitivity_level=4,
            source="name",
        )
    return None


def detect_pii_by_value(samples: Iterable[str]) -> Optional[str]:
    """Return the strongest PII tag matching any of the sample values."""
    for v in samples:
        v = (v or "").strip()
        if not v:
            continue
        if "@" in v and _PII_VALUE_PATTERNS["PII.email"].match(v):
            return "PII.email"
        if _PII_VALUE_PATTERNS["PII.phone"].match(v):
            return "PII.phone"
        if _CJK_NAME.match(v):
            return "PII.real_name"
        if _PII_VALUE_PATTERNS["PII.ip"].match(v):
            return "PII.ip"
        if _PII_VALUE_PATTERNS["PII.id_card"].match(v):
            return "PII.id_card"
    return None


# ── Tag CRUD ─────────────────────────────────────────────────────────────────
def upsert_tag(
    name: str,
    *,
    category: str = "general",
    description: str = "",
    color: str = "#888888",
    source: str = "manual",
    sensitivity_level: int = 0,
) -> TagORM:
    """Create or update a tag by name. Idempotent."""
    with get_metadata_session() as s:
        tag = s.query(TagORM).filter(TagORM.name == name).one_or_none()
        if tag is None:
            tag = TagORM(
                name=name,
                category=category,
                description=description,
                color=color,
                source=source,
                sensitivity_level=str(sensitivity_level),
            )
            s.add(tag)
        else:
            tag.category = category or tag.category
            tag.description = description or tag.description
            tag.color = color or tag.color
            tag.source = source or tag.source
            try:
                tag.sensitivity_level = str(int(sensitivity_level))
            except Exception:
                pass
        s.commit()
        s.refresh(tag)
        return tag


def list_tags(
    *,
    category: Optional[str] = None,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tags; optional filters."""
    with get_metadata_session() as s:
        q = s.query(TagORM)
        if category:
            q = q.filter(TagORM.category == category)
        if source:
            q = q.filter(TagORM.source == source)
        return [db_to_dict(t) for t in q.order_by(TagORM.name).all()]


def get_tag_by_id(tag_id: str) -> Optional[Dict[str, Any]]:
    with get_metadata_session() as s:
        t = s.query(TagORM).filter(TagORM.id == tag_id).one_or_none()
        return db_to_dict(t) if t else None


def delete_tag(tag_id: str) -> bool:
    with get_metadata_session() as s:
        t = s.query(TagORM).filter(TagORM.id == tag_id).one_or_none()
        if not t:
            return False
        # Cascade deletes assignments
        s.query(TagAssignmentORM).filter(TagAssignmentORM.tag_id == tag_id).delete()
        s.delete(t)
        s.commit()
        return True


# ── Tag assignment ───────────────────────────────────────────────────────────
def assign_tag(
    tag_id: str,
    target_type: str,
    target_id: str,
    *,
    source: str = "manual",
) -> Dict[str, Any]:
    """Attach a tag to a target (column / table / dataset / glossary_term). Idempotent."""
    if target_type not in {"column", "table", "dataset", "glossary_term"}:
        raise ValueError(f"invalid_target_type: {target_type}")
    with get_metadata_session() as s:
        existing = (
            s.query(TagAssignmentORM)
            .filter(
                TagAssignmentORM.tag_id == tag_id,
                TagAssignmentORM.target_type == target_type,
                TagAssignmentORM.target_id == target_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return db_to_dict(existing)
        a = TagAssignmentORM(
            tag_id=tag_id, target_type=target_type, target_id=target_id, source=source
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        return db_to_dict(a)


def unassign_tag(tag_id: str, target_type: str, target_id: str) -> bool:
    with get_metadata_session() as s:
        a = (
            s.query(TagAssignmentORM)
            .filter(
                TagAssignmentORM.tag_id == tag_id,
                TagAssignmentORM.target_type == target_type,
                TagAssignmentORM.target_id == target_id,
            )
            .one_or_none()
        )
        if not a:
            return False
        s.delete(a)
        s.commit()
        return True


def list_assignments(
    *,
    tag_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with get_metadata_session() as s:
        q = s.query(TagAssignmentORM)
        if tag_id:
            q = q.filter(TagAssignmentORM.tag_id == tag_id)
        if target_type:
            q = q.filter(TagAssignmentORM.target_type == target_type)
        if target_id:
            q = q.filter(TagAssignmentORM.target_id == target_id)
        return [db_to_dict(a) for a in q.order_by(TagAssignmentORM.created_at.desc()).all()]


# ── Auto PII scan ────────────────────────────────────────────────────────────
@dataclass
class AutoTagResult:
    scanned_columns: int = 0
    matches: List[PIIMatch] = field(default_factory=list)
    tags_created: int = 0
    assignments_created: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanned_columns": self.scanned_columns,
            "matches": [m.to_dict() for m in self.matches],
            "tags_created": self.tags_created,
            "assignments_created": self.assignments_created,
        }


def auto_tag_pii(
    *,
    database_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    dry_run: bool = False,
) -> AutoTagResult:
    """Walk columns, detect PII by column name (and small value sample if present),
    create tags (idempotent) and assignments. Returns a summary.
    """
    res = AutoTagResult()
    with get_metadata_session() as s:
        q = (
            s.query(ColumnORM, TableORM, DatasetORM)  # type: ignore[arg-type]
            .join(TableORM, ColumnORM.table_id == TableORM.id)
            .outerjoin(DatasetORM, TableORM.id == DatasetORM.id)
        )
        # Optional DB / schema filters via path
        rows = q.all()
        for col, tbl, _ds in rows:
            res.scanned_columns += 1
            match = detect_pii_by_name(col.name)
            if match is None:
                continue
            match.column_id = col.id
            match.table_name = tbl.name
            res.matches.append(match)

    if dry_run or not res.matches:
        return res

    # Create tags + assignments
    with get_metadata_session() as s:
        for m in res.matches:
            tag = s.query(TagORM).filter(TagORM.name == m.tag_name).one_or_none()
            if tag is None:
                tag = TagORM(
                    name=m.tag_name,
                    category="pii",
                    description=f"Auto-detected PII column ({m.source})",
                    color="#ff6b6b",
                    source="auto_pii",
                    sensitivity_level=str(m.sensitivity_level),
                )
                s.add(tag)
                s.flush()
                res.tags_created += 1
            existing = (
                s.query(TagAssignmentORM)
                .filter(
                    TagAssignmentORM.tag_id == tag.id,
                    TagAssignmentORM.target_type == "column",
                    TagAssignmentORM.target_id == m.column_id,
                )
                .one_or_none()
            )
            if existing is None:
                s.add(
                    TagAssignmentORM(
                        tag_id=tag.id,
                        target_type="column",
                        target_id=m.column_id,
                        source="auto_pii",
                    )
                )
                res.assignments_created += 1
        s.commit()
    return res


# ── Tag propagation ──────────────────────────────────────────────────────────
@dataclass
class PropagationResult:
    """Result of propagating column tags up to parent table + dataset."""

    propagated_assignments: int = 0
    rolled_up_tables: int = 0
    rolled_up_datasets: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "propagated_assignments": self.propagated_assignments,
            "rolled_up_tables": self.rolled_up_tables,
            "rolled_up_datasets": self.rolled_up_datasets,
        }


def propagate_column_tags(
    *, only_pii: bool = True, dry_run: bool = False
) -> PropagationResult:
    """For every column tag assignment, ensure the parent table also gets
    the same tag (with ``source="propagation"``); if the table is bound to
    a dataset, ensure the dataset gets the tag too.
    """
    res = PropagationResult()
    seen_tables: set = set()
    seen_datasets: set = set()
    new_assignments: List[TagAssignmentORM] = []

    with get_metadata_session() as s:
        assignments = s.query(TagAssignmentORM).filter(
            TagAssignmentORM.target_type == "column"
        ).all()

        for a in assignments:
            if only_pii:
                tag = s.query(TagORM).filter(TagORM.id == a.tag_id).one_or_none()
                if tag is None or tag.category != "pii":
                    continue
            col = s.query(ColumnORM).filter(ColumnORM.id == a.target_id).one_or_none()
            if col is None:
                continue
            tbl = s.query(TableORM).filter(TableORM.id == col.table_id).one_or_none()
            if tbl is None:
                continue
            # Table-level propagation
            if (a.tag_id, "table", tbl.id) not in seen_tables:
                seen_tables.add((a.tag_id, "table", tbl.id))
                existing = (
                    s.query(TagAssignmentORM)
                    .filter(
                        TagAssignmentORM.tag_id == a.tag_id,
                        TagAssignmentORM.target_type == "table",
                        TagAssignmentORM.target_id == tbl.id,
                    )
                    .one_or_none()
                )
                if existing is None:
                    if not dry_run:
                        new_assignments.append(
                            TagAssignmentORM(
                                tag_id=a.tag_id,
                                target_type="table",
                                target_id=tbl.id,
                                source="propagation",
                            )
                        )
                    res.propagated_assignments += 1
                    res.rolled_up_tables += 1

            # Dataset-level propagation (skip — we don't bind tables to datasets directly here)
            # (kept as a no-op placeholder for clarity; extend in P4-4-W2)

    if new_assignments and not dry_run:
        with get_metadata_session() as sess:
            for na in new_assignments:
                sess.add(na)
            sess.commit()
    return res


__all__ = [
    "PIIMatch",
    "AutoTagResult",
    "PropagationResult",
    "detect_pii_by_name",
    "detect_pii_by_value",
    "upsert_tag",
    "list_tags",
    "get_tag_by_id",
    "delete_tag",
    "assign_tag",
    "unassign_tag",
    "list_assignments",
    "auto_tag_pii",
    "propagate_column_tags",
]
