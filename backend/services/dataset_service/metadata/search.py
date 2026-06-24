"""P4-4-W1 metadata search — full-text + tag filter + recommendations.

The search backend is intentionally simple and portable — no Lucene, no
external index service. It does substring + token-level matching over the
10 metadata tables, with two ergonomic features:

  * **Tag filter** — restrict results by tag ids (or tag names).
  * **Type filter** — restrict to ``database / schema / table / column /
    dataset / glossary_term`` (OpenMetadata-style).

For "real" full-text we'd swap in a Postgres ``tsvector`` index; for the
SQLite tests we fall back to in-memory tokenization.

**Chinese tokenization** — when ``jieba`` is importable we use it;
otherwise we fall back to single-character + word-boundary tokenization
(which still matches the most common CJK names).

**Recommendations** — ``recommend()`` returns a small ranked list
combining recency (last_viewed_at) and popularity (view_count).
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .models import (
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    DatasetORM,
    GlossaryORM,
    GlossaryTermORM,
    TableORM,
    TagAssignmentORM,
    TagORM,
    TermRelationORM,
    db_to_dict,
    get_metadata_session,
)

logger = logging.getLogger(__name__)


# ── Tokenization ─────────────────────────────────────────────────────────────
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")
_LATIN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokenize(text: str) -> List[str]:
    """Split *text* into lowercase tokens; uses jieba if importable."""
    if not text:
        return []
    text = str(text)
    try:
        import jieba  # type: ignore
        tokens = [t.strip().lower() for t in jieba.cut(text) if t.strip()]
        return [t for t in tokens if t]
    except Exception:
        pass
    out: List[str] = []
    out.extend(m.group(0).lower() for m in _LATIN_RE.finditer(text))
    out.extend(c for c in text if _CJK_RE.match(c))
    return out


def _score(haystack_tokens: List[str], query_tokens: List[str]) -> float:
    """Token overlap score: matches / max(len(q), 1)."""
    if not query_tokens:
        return 0.0
    if not haystack_tokens:
        return 0.0
    s = set(haystack_tokens)
    hits = sum(1 for q in query_tokens if q in s)
    return hits / max(len(query_tokens), 1)


# ── Recommendation store ─────────────────────────────────────────────────────
@dataclass
class _View:
    """One user view event."""

    user_id: str
    target_type: str
    target_id: str
    viewed_at: float = field(default_factory=time.time)


_VIEW_EVENTS: List[_View] = []
_RECENT_PER_USER: Dict[str, List[Tuple[str, str]]] = {}  # user → [(type, id), ...]


def record_view(user_id: str, target_type: str, target_id: str) -> None:
    """Record a user view; used for recommendation."""
    _VIEW_EVENTS.append(_View(user_id=user_id, target_type=target_type, target_id=target_id))
    rl = _RECENT_PER_USER.setdefault(user_id, [])
    rl.append((target_type, target_id))
    # Cap at 50
    if len(rl) > 50:
        del rl[:-50]


def reset_view_store() -> None:
    """Test hook — wipe view history."""
    _VIEW_EVENTS.clear()
    _RECENT_PER_USER.clear()


# ── Search result DTO ────────────────────────────────────────────────────────
@dataclass
class SearchHit:
    """A single search hit."""

    type: str
    id: str
    name: str
    score: float
    description: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "score": round(self.score, 4),
            "description": self.description,
            **self.extra,
        }


def _hit(type_: str, id_: str, name: str, score: float, description: str = "",
         **extra) -> SearchHit:
    return SearchHit(type=type_, id=id_, name=name, score=score,
                     description=description, extra=extra)


# ── Core search ──────────────────────────────────────────────────────────────
_VALID_TYPES = {"database", "schema", "table", "column", "dataset", "glossary_term"}


def search(
    q: str,
    *,
    type_filter: Optional[str] = None,
    tag_ids: Optional[List[str]] = None,
    tag_names: Optional[List[str]] = None,
    limit: int = 50,
    include_description: bool = True,
) -> List[Dict[str, Any]]:
    """Search the metadata catalog.

    Parameters
    ----------
    q : str
        Free-text query.
    type_filter : str, optional
        One of ``database / schema / table / column / dataset / glossary_term``;
        ``None`` searches everything.
    tag_ids / tag_names : list, optional
        Restrict hits to those tagged with the given tags (union, not
        intersection — typical for "show me anything tagged PII or financial").
    limit : int
        Max hits returned.
    include_description : bool
        Include description in haystack (vs name only).

    Returns
    -------
    list[dict]
        List of :class:`SearchHit` dicts, sorted by score desc.
    """
    query_tokens = _tokenize(q)
    type_filter_norm = (type_filter or "").strip().lower() or None
    if type_filter_norm and type_filter_norm not in _VALID_TYPES:
        raise ValueError(f"invalid_type: {type_filter_norm}")

    # Resolve tag filter to a set of target ids
    target_id_set = _resolve_tag_filter(tag_ids=tag_ids, tag_names=tag_names)

    hits: List[SearchHit] = []
    wanted_types = {type_filter_norm} if type_filter_norm else _VALID_TYPES

    with get_metadata_session() as s:
        if "database" in wanted_types:
            for db in s.query(DatabaseORM).all():
                tokens = _tokenize(db.name)
                if include_description:
                    tokens += _tokenize(db.description)
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    if target_id_set is not None and ("database", db.id) not in target_id_set:
                        continue
                    hits.append(
                        _hit("database", db.id, db.name, sc, db.description,
                             service=db.service)
                    )

        if "schema" in wanted_types:
            for sch in s.query(DatabaseSchemaORM).all():
                tokens = _tokenize(sch.name)
                if include_description:
                    tokens += _tokenize(sch.description)
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    hits.append(_hit("schema", sch.id, sch.name, sc, sch.description))

        if "table" in wanted_types:
            for tbl in s.query(TableORM).all():
                tokens = _tokenize(tbl.name)
                if include_description:
                    tokens += _tokenize(tbl.description or "")
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    if target_id_set is not None and ("table", tbl.id) not in target_id_set:
                        continue
                    hits.append(
                        _hit("table", tbl.id, tbl.name, sc, tbl.description or "",
                             table_type=tbl.table_type, owner=tbl.owner)
                    )

        if "column" in wanted_types:
            for col in s.query(ColumnORM).all():
                tokens = _tokenize(col.name)
                if include_description:
                    tokens += _tokenize(col.description or "")
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    if target_id_set is not None and ("column", col.id) not in target_id_set:
                        continue
                    hits.append(
                        _hit("column", col.id, col.name, sc, col.description or "",
                             data_type=col.data_type)
                    )

        if "dataset" in wanted_types:
            for ds in s.query(DatasetORM).all():
                tokens = _tokenize(ds.name)
                if include_description:
                    tokens += _tokenize(ds.description or "")
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    if target_id_set is not None and ("dataset", ds.id) not in target_id_set:
                        continue
                    hits.append(
                        _hit("dataset", ds.id, ds.name, sc, ds.description or "",
                             tier=ds.tier, format=ds.format)
                    )

        if "glossary_term" in wanted_types:
            for t in s.query(GlossaryTermORM).all():
                tokens = _tokenize(t.name)
                if include_description:
                    tokens += _tokenize(t.definition or "")
                sc = _score(tokens, query_tokens)
                if sc > 0:
                    if target_id_set is not None and ("glossary_term", t.id) not in target_id_set:
                        continue
                    hits.append(
                        _hit("glossary_term", t.id, t.name, sc, t.definition or "")
                    )

    hits.sort(key=lambda h: (-h.score, h.type, h.name))
    return [h.to_dict() for h in hits[: max(1, limit)]]


def _resolve_tag_filter(
    *,
    tag_ids: Optional[List[str]] = None,
    tag_names: Optional[List[str]] = None,
) -> Optional[Set[Tuple[str, str]]]:
    """Return ``{(type, id), ...}`` if a tag filter is in effect; else None."""
    if not (tag_ids or tag_names):
        return None
    resolved_ids: Set[str] = set(tag_ids or [])
    if tag_names:
        with get_metadata_session() as s:
            rows = s.query(TagORM).filter(TagORM.name.in_(tag_names)).all()
            resolved_ids |= {r.id for r in rows}
    if not resolved_ids:
        # Filter was supplied but resolved to nothing — return an empty set
        # so all hits are rejected.
        return set()
    with get_metadata_session() as s:
        rows = (
            s.query(TagAssignmentORM)
            .filter(TagAssignmentORM.tag_id.in_(resolved_ids))
            .all()
        )
        return {(r.target_type, r.target_id) for r in rows}


# ── Recommendations ──────────────────────────────────────────────────────────
def recommend(
    user_id: str,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Recommend metadata assets for *user_id*.

    Strategy:
      * **Personal recency** — assets the user has viewed recently
        (boost: +0.5 per hit, decay over time).
      * **Global popularity** — assets with the most views across all
        users (boost: log10(view_count) * 0.3).
      * **Type round-robin** — keep at most 3 hits per type to avoid
        columns dominating.

    Returns a list of dicts with ``type``, ``id``, ``name``, ``score``.
    """
    if not user_id:
        return []

    # Score all assets
    scores: Dict[Tuple[str, str], float] = {}
    counts: Counter = Counter()
    now = time.time()

    # Personal recency
    user_events = [v for v in _VIEW_EVENTS if v.user_id == user_id]
    for v in user_events:
        age_h = (now - v.viewed_at) / 3600.0
        decay = max(0.0, 1.0 - age_h / 168.0)  # 1-week half-life-ish
        scores[(v.target_type, v.target_id)] = (
            scores.get((v.target_type, v.target_id), 0.0) + 0.5 + 0.5 * decay
        )
        counts[(v.target_type, v.target_id)] += 1

    # Global popularity
    for v in _VIEW_EVENTS:
        counts[(v.target_type, v.target_id)] += 1
    for k, c in counts.items():
        scores[k] = scores.get(k, 0.0) + 0.3 * (1.0 + _log10(c))

    # Hydrate names
    out: List[SearchHit] = []
    with get_metadata_session() as s:
        for (t, tid), sc in sorted(scores.items(), key=lambda kv: -kv[1]):
            obj, name = _hydrate(s, t, tid)
            if not name:
                continue
            out.append(SearchHit(type=t, id=tid, name=name, score=sc))

    # Round-robin: at most 3 per type
    by_type: Dict[str, List[SearchHit]] = {}
    for h in out:
        by_type.setdefault(h.type, []).append(h)
    pruned: List[SearchHit] = []
    for t in sorted(by_type):
        pruned.extend(by_type[t][:3])

    pruned.sort(key=lambda h: (-h.score, h.type, h.name))
    return [h.to_dict() for h in pruned[: max(1, limit)]]


def _log10(n: int) -> float:
    if n <= 0:
        return 0.0
    import math
    return math.log10(n)


def _hydrate(s, type_: str, id_: str) -> Tuple[Optional[Any], str]:
    """Return ``(obj, name)`` for a search hit, or ``(None, '')`` if missing."""
    if type_ == "database":
        obj = s.query(DatabaseORM).filter(DatabaseORM.id == id_).one_or_none()
    elif type_ == "table":
        obj = s.query(TableORM).filter(TableORM.id == id_).one_or_none()
    elif type_ == "column":
        obj = s.query(ColumnORM).filter(ColumnORM.id == id_).one_or_none()
    elif type_ == "dataset":
        obj = s.query(DatasetORM).filter(DatasetORM.id == id_).one_or_none()
    elif type_ == "glossary_term":
        obj = s.query(GlossaryTermORM).filter(GlossaryTermORM.id == id_).one_or_none()
    elif type_ == "schema":
        obj = s.query(DatabaseSchemaORM).filter(DatabaseSchemaORM.id == id_).one_or_none()
    else:
        obj = None
    if obj is None:
        return None, ""
    return obj, getattr(obj, "name", "")


__all__ = [
    "SearchHit",
    "search",
    "recommend",
    "record_view",
    "reset_view_store",
    "_tokenize",
    "_VALID_TYPES",
]
