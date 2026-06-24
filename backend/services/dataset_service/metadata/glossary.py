"""P4-4-W1 metadata glossary — business terms + relations + column linking.

Modelled after OpenMetadata's ``Glossary`` + ``GlossaryTerm`` entities.

Concepts:
  * **Glossary**        — a curated vocabulary for a domain (e.g. ``User``,
    ``Transaction``, ``Product``). Each glossary owns many terms.
  * **GlossaryTerm**    — a single business concept with a definition
    (e.g. ``user_id`` / ``email`` / ``真实姓名`` / ``性别``).
  * **TermRelation**    — directed edge between two terms:
      - ``synonym``      — interchangeable (e.g. ``user_id`` ⇄ ``uid``)
      - ``antonym``      — opposite (e.g. ``active`` vs ``disabled``)
      - ``parent``       — hierarchy (``to_term`` is the parent)
      - ``derives_from`` — ``from`` is derived from ``to``
      - ``maps_to``      — cross-domain mapping

The ``column linking`` half (``/api/v1/metadata/glossary/{term}/columns``)
walks the term-relation graph + matches by column name. We do not add a
dedicated ``TermColumnLink`` table — the matching is computed on demand
via the existing ``column`` + ``term`` rows.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    GlossaryORM,
    GlossaryTermORM,
    TableORM,
    TermRelationORM,
    _dumps,
    _new_id,
    _now,
    db_to_dict,
    get_metadata_session,
)

logger = logging.getLogger(__name__)


# ── Relation type helpers ────────────────────────────────────────────────────
_VALID_RELATION_TYPES = {"synonym", "antonym", "parent", "derives_from", "maps_to"}


def validate_relation_type(t: str) -> None:
    if t not in _VALID_RELATION_TYPES:
        raise ValueError(f"invalid_relation_type: {t} (allowed: {sorted(_VALID_RELATION_TYPES)})")


# ── Glossary CRUD ────────────────────────────────────────────────────────────
def upsert_glossary(
    name: str,
    *,
    description: str = "",
    owner: str = "",
) -> GlossaryORM:
    """Create or update a glossary by name. Idempotent."""
    with get_metadata_session() as s:
        g = s.query(GlossaryORM).filter(GlossaryORM.name == name).one_or_none()
        if g is None:
            g = GlossaryORM(name=name, description=description, owner=owner)
            s.add(g)
        else:
            g.description = description or g.description
            g.owner = owner or g.owner
        s.commit()
        s.refresh(g)
        return g


def list_glossaries() -> List[Dict[str, Any]]:
    """List glossaries with derived ``term_count``."""
    with get_metadata_session() as s:
        out: List[Dict[str, Any]] = []
        for g in s.query(GlossaryORM).order_by(GlossaryORM.name).all():
            d = db_to_dict(g)
            d["term_count"] = (
                s.query(GlossaryTermORM).filter(GlossaryTermORM.glossary_id == g.id).count()
            )
            out.append(d)
        return out


def get_glossary(glossary_id: str) -> Optional[Dict[str, Any]]:
    with get_metadata_session() as s:
        g = s.query(GlossaryORM).filter(GlossaryORM.id == glossary_id).one_or_none()
        if not g:
            return None
        d = db_to_dict(g)
        d["term_count"] = (
            s.query(GlossaryTermORM).filter(GlossaryTermORM.glossary_id == g.id).count()
        )
        return d


def delete_glossary(glossary_id: str) -> bool:
    with get_metadata_session() as s:
        g = s.query(GlossaryORM).filter(GlossaryORM.id == glossary_id).one_or_none()
        if not g:
            return False
        # Wipe relations for owned terms first
        term_ids = [
            t.id for t in s.query(GlossaryTermORM).filter(GlossaryTermORM.glossary_id == g.id)
        ]
        if term_ids:
            s.query(TermRelationORM).filter(
                TermRelationORM.from_term_id.in_(term_ids)
            ).delete(synchronize_session=False)
            s.query(TermRelationORM).filter(
                TermRelationORM.to_term_id.in_(term_ids)
            ).delete(synchronize_session=False)
        s.delete(g)
        s.commit()
        return True


# ── Term CRUD ────────────────────────────────────────────────────────────────
def create_term(
    glossary_id: str,
    name: str,
    *,
    definition: str = "",
    related_terms: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> GlossaryTermORM:
    """Create a new term in a glossary. Raises if name is already used in the same glossary."""
    with get_metadata_session() as s:
        if not s.query(GlossaryORM).filter(GlossaryORM.id == glossary_id).first():
            raise ValueError(f"glossary_not_found: {glossary_id}")
        existing = (
            s.query(GlossaryTermORM)
            .filter(
                GlossaryTermORM.glossary_id == glossary_id,
                GlossaryTermORM.name == name,
            )
            .one_or_none()
        )
        if existing is not None:
            raise ValueError(f"term_already_exists: {name}")
        t = GlossaryTermORM(
            glossary_id=glossary_id,
            name=name,
            definition=definition,
            related_terms_json=_dumps(related_terms or []),
            extra=_dumps(extra or {}),
        )
        s.add(t)
        s.commit()
        s.refresh(t)
        return t


def list_terms(
    glossary_id: Optional[str] = None,
    *,
    name_like: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List terms; optional glossary filter + name substring."""
    with get_metadata_session() as s:
        q = s.query(GlossaryTermORM)
        if glossary_id:
            q = q.filter(GlossaryTermORM.glossary_id == glossary_id)
        if name_like:
            q = q.filter(GlossaryTermORM.name.like(f"%{name_like}%"))
        return [db_to_dict(t) for t in q.order_by(GlossaryTermORM.name).all()]


def get_term(term_id: str) -> Optional[Dict[str, Any]]:
    with get_metadata_session() as s:
        t = s.query(GlossaryTermORM).filter(GlossaryTermORM.id == term_id).one_or_none()
        return db_to_dict(t) if t else None


def update_term(
    term_id: str,
    *,
    definition: Optional[str] = None,
    related_terms: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    with get_metadata_session() as s:
        t = s.query(GlossaryTermORM).filter(GlossaryTermORM.id == term_id).one_or_none()
        if not t:
            return None
        if definition is not None:
            t.definition = definition
        if related_terms is not None:
            t.related_terms_json = _dumps(related_terms)
        if extra is not None:
            t.extra = _dumps(extra)
        t.updated_at = _now()
        s.commit()
        s.refresh(t)
        return db_to_dict(t)


def delete_term(term_id: str) -> bool:
    with get_metadata_session() as s:
        t = s.query(GlossaryTermORM).filter(GlossaryTermORM.id == term_id).one_or_none()
        if not t:
            return False
        # Cascade relations
        s.query(TermRelationORM).filter(
            (TermRelationORM.from_term_id == term_id) | (TermRelationORM.to_term_id == term_id)
        ).delete(synchronize_session=False)
        s.delete(t)
        s.commit()
        return True


# ── Term relations ───────────────────────────────────────────────────────────
def add_relation(
    from_term_id: str,
    to_term_id: str,
    relation_type: str,
    *,
    note: str = "",
    bidirectional: bool = False,
) -> TermRelationORM:
    """Create a directed relation between two terms.

    For ``synonym`` the relation is *symmetric* by convention — we still
    store a single row but also return the symmetric view when listing.
    Use ``bidirectional=True`` to insert two mirrored rows (one each way).
    """
    validate_relation_type(relation_type)
    if from_term_id == to_term_id:
        raise ValueError("self_relation_not_allowed")

    with get_metadata_session() as s:
        if not s.query(GlossaryTermORM).filter(GlossaryTermORM.id == from_term_id).first():
            raise ValueError(f"from_term_not_found: {from_term_id}")
        if not s.query(GlossaryTermORM).filter(GlossaryTermORM.id == to_term_id).first():
            raise ValueError(f"to_term_not_found: {to_term_id}")
        existing = (
            s.query(TermRelationORM)
            .filter(
                TermRelationORM.from_term_id == from_term_id,
                TermRelationORM.to_term_id == to_term_id,
                TermRelationORM.relation_type == relation_type,
            )
            .one_or_none()
        )
        if existing is not None:
            return existing

        r = TermRelationORM(
            from_term_id=from_term_id,
            to_term_id=to_term_id,
            relation_type=relation_type,
            note=note,
        )
        s.add(r)
        if bidirectional and relation_type in ("synonym", "antonym", "maps_to"):
            r2 = TermRelationORM(
                from_term_id=to_term_id,
                to_term_id=from_term_id,
                relation_type=relation_type,
                note=note,
            )
            s.add(r2)
        s.commit()
        s.refresh(r)
        return r


def list_relations(
    term_id: Optional[str] = None,
    relation_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List relations; optional term_id filter (in either direction)."""
    with get_metadata_session() as s:
        q = s.query(TermRelationORM)
        if term_id:
            q = q.filter(
                (TermRelationORM.from_term_id == term_id)
                | (TermRelationORM.to_term_id == term_id)
            )
        if relation_type:
            q = q.filter(TermRelationORM.relation_type == relation_type)
        return [db_to_dict(r) for r in q.order_by(TermRelationORM.created_at.desc()).all()]


def delete_relation(relation_id: str) -> bool:
    with get_metadata_session() as s:
        r = (
            s.query(TermRelationORM).filter(TermRelationORM.id == relation_id).one_or_none()
        )
        if not r:
            return False
        s.delete(r)
        s.commit()
        return True


# ── Term ↔ column linking ────────────────────────────────────────────────────
@dataclass
class LinkedColumn:
    """A column linked to a glossary term (or via synonym)."""

    column_id: str
    column_name: str
    data_type: str
    table_name: str
    schema_name: str
    database_name: str
    match_source: str  # exact / synonym / fuzzy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_id": self.column_id,
            "column_name": self.column_name,
            "data_type": self.data_type,
            "table_name": self.table_name,
            "schema_name": self.schema_name,
            "database_name": self.database_name,
            "match_source": self.match_source,
        }


def link_term_to_columns(term_id: str) -> List[LinkedColumn]:
    """Return all columns whose name matches the term (or its synonyms).

    Strategy:
      1. Direct match: ``ColumnORM.name == term.name`` (case-insensitive).
      2. Synonym match: walk TermRelation rows of type ``synonym`` from the
         term and search for each synonym's name.
      3. Fuzzy match: substring (e.g. ``user_id`` matches ``user_id_str``).

    Results are de-duplicated by ``column_id``.
    """
    with get_metadata_session() as s:
        term = (
            s.query(GlossaryTermORM).filter(GlossaryTermORM.id == term_id).one_or_none()
        )
        if term is None:
            return []

        syn_ids: Set[str] = set()
        for rel in s.query(TermRelationORM).filter(
            TermRelationORM.from_term_id == term_id,
            TermRelationORM.relation_type == "synonym",
        ).all():
            syn_ids.add(rel.to_term_id)
        for rel in s.query(TermRelationORM).filter(
            TermRelationORM.to_term_id == term_id,
            TermRelationORM.relation_type == "synonym",
        ).all():
            syn_ids.add(rel.from_term_id)
        syn_names: Set[str] = set()
        if syn_ids:
            syn_names = {
                t.name for t in s.query(GlossaryTermORM).filter(
                    GlossaryTermORM.id.in_(syn_ids)
                ).all()
            }

        wanted_names = {term.name, *syn_names}
        wanted_lc = {n.lower() for n in wanted_names if n}

        results: List[LinkedColumn] = []
        seen: Set[str] = set()

        # Exact (case-insensitive)
        rows = (
            s.query(ColumnORM, TableORM, DatabaseSchemaORM, DatabaseORM)
            .join(TableORM, ColumnORM.table_id == TableORM.id)
            .join(DatabaseSchemaORM, TableORM.schema_id == DatabaseSchemaORM.id)
            .join(DatabaseORM, DatabaseSchemaORM.database_id == DatabaseORM.id)
            .all()
        )
        for col, tbl, sch, db in rows:
            cname_lc = (col.name or "").lower()
            if cname_lc in wanted_lc:
                key = f"{db.name}.{sch.name}.{tbl.name}.{col.name}"
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    LinkedColumn(
                        column_id=col.id,
                        column_name=col.name,
                        data_type=col.data_type,
                        table_name=tbl.name,
                        schema_name=sch.name,
                        database_name=db.name,
                        match_source="synonym" if col.name.lower() != term.name.lower() else "exact",
                    )
                )

        # Fuzzy substring (only if we got nothing exact)
        if not results:
            for col, tbl, sch, db in rows:
                cname_lc = (col.name or "").lower()
                if any(cname_lc.find(n.lower()) >= 0 or n.lower().find(cname_lc) >= 0
                       for n in wanted_lc):
                    key = f"{db.name}.{sch.name}.{tbl.name}.{col.name}"
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        LinkedColumn(
                            column_id=col.id,
                            column_name=col.name,
                            data_type=col.data_type,
                            table_name=tbl.name,
                            schema_name=sch.name,
                            database_name=db.name,
                            match_source="fuzzy",
                        )
                    )
        return results


# ── Seed data ────────────────────────────────────────────────────────────────
_DEFAULT_GLOSSARY_NAME = "User Domain"


def seed_default_glossary() -> Dict[str, Any]:
    """Create a default User Domain glossary with core business terms.

    Returns the seeded glossary + term count.
    """
    g = upsert_glossary(
        _DEFAULT_GLOSSARY_NAME,
        description="Default business glossary for the user/account domain.",
        owner="platform-team",
    )
    seed_terms = [
        ("user_id", "Unique identifier for a user account."),
        ("uid", "Short alias for user_id (synonym)."),
        ("email", "User email address — used for login and notifications."),
        ("phone", "User phone number (mobile)."),
        ("real_name", "User's real name as registered."),
        ("gender", "User gender."),
        ("age", "User age in years."),
        ("nationality", "User nationality / country."),
    ]
    term_ids: Dict[str, str] = {}
    for nm, defn in seed_terms:
        try:
            t = create_term(g.id, nm, definition=defn)
            term_ids[nm] = t.id
        except ValueError:
            existing = list_terms(g.id, name_like=nm)
            match = [t for t in existing if t["name"] == nm]
            if match:
                term_ids[nm] = match[0]["id"]

    # Synonym relations: user_id ⇄ uid
    if term_ids.get("user_id") and term_ids.get("uid"):
        try:
            add_relation(
                term_ids["user_id"],
                term_ids["uid"],
                "synonym",
                bidirectional=True,
                note="uid is a deprecated alias for user_id.",
            )
        except Exception:
            pass

    return {"glossary_id": g.id, "name": g.name, "seeded_terms": len(term_ids)}


__all__ = [
    "LinkedColumn",
    "validate_relation_type",
    "upsert_glossary",
    "list_glossaries",
    "get_glossary",
    "delete_glossary",
    "create_term",
    "list_terms",
    "get_term",
    "update_term",
    "delete_term",
    "add_relation",
    "list_relations",
    "delete_relation",
    "link_term_to_columns",
    "seed_default_glossary",
    "_DEFAULT_GLOSSARY_NAME",
    "_VALID_RELATION_TYPES",
]
