"""P4-4-W1: search tests (fulltext + tag filter + recommend) (≥3 cases)."""
from __future__ import annotations

import pytest

from services.dataset_service.metadata import search as search_mod
from services.dataset_service.metadata.models import (
    TagAssignmentORM, TagORM, get_metadata_session,
)


def test_search_finds_columns_by_name(seeded_metadata):
    """Full-text search over seeded data should find 'email' and 'user_id'."""
    hits = search_mod.search("email")
    assert hits, "expected at least one hit for 'email'"
    assert any(h["type"] == "column" and h["name"] == "email" for h in hits)

    hits = search_mod.search("user_id")
    assert any(h["type"] == "column" and h["name"] == "user_id" for h in hits)


def test_search_type_filter_and_limit(seeded_metadata):
    """type=column restricts hits; limit caps results."""
    all_hits = search_mod.search("id", limit=100)
    types_all = {h["type"] for h in all_hits}
    # Multiple types may match "id"
    assert "column" in types_all

    col_only = search_mod.search("id", type_filter="column", limit=100)
    assert all(h["type"] == "column" for h in col_only)
    assert len(col_only) <= 100


def test_search_invalid_type_raises(seeded_metadata):
    with pytest.raises(ValueError):
        search_mod.search("x", type_filter="bogus")


def test_search_tag_filter(seeded_metadata, init_db):
    """Search restricted to PII-tagged columns returns only those."""
    # Auto-tag PII columns
    from services.dataset_service.metadata import tags as tags_mod
    tags_mod.auto_tag_pii()

    # All PII column ids
    with get_metadata_session() as s:
        pii_tag_ids = [t.id for t in s.query(TagORM).filter(
            TagORM.category == "pii").all()]
        all_pii_assignments = s.query(TagAssignmentORM).filter(
            TagAssignmentORM.tag_id.in_(pii_tag_ids),
            TagAssignmentORM.target_type == "column",
        ).all()
        assert all_pii_assignments, "auto-tag should have created assignments"
        pii_column_ids = {a.target_id for a in all_pii_assignments}

    # Search with tag_names filter — pick a query that overlaps the
    # PII-tagged column names (search uses token-overlap scoring).
    hits = search_mod.search("email phone real_name",
                              tag_names=["PII.email", "PII.phone", "PII.real_name"])
    hit_ids = {h["id"] for h in hits if h["type"] == "column"}
    # All returned columns should be PII-tagged
    assert hit_ids, "expected at least one PII-tagged column hit"
    assert hit_ids.issubset(pii_column_ids)


def test_search_chinese_token_fallback(seeded_metadata):
    """CJK fallback tokenization: a Chinese substring matches single columns."""
    # Add a column with a Chinese name to test CJK tokenization
    from services.dataset_service.metadata.models import (
        ColumnORM, get_metadata_session,
    )
    with get_metadata_session() as s:
        tbl = s.query(__import__("services").dataset_service.metadata.models.TableORM if False else  # noqa
                       __import__("services.dataset_service.metadata.models", fromlist=["TableORM"]).TableORM
                      ).filter_by(name="users").one()  # type: ignore
        s.add(ColumnORM(table_id=tbl.id, name="真实姓名", data_type="string",
                         nullable="true", ordinal="99"))
        s.commit()

    hits = search_mod.search("真实", type_filter="column")
    assert any(h["name"] == "真实姓名" for h in hits)


def test_recommend_based_on_view_history(seeded_metadata, init_db):
    """Recommend returns items the user has recently viewed."""
    # Tag a few columns so they show up under the seeded schema
    from services.dataset_service.metadata.models import TableORM, ColumnORM
    with get_metadata_session() as s:
        users = s.query(TableORM).filter_by(name="users").one()
        col_id = s.query(ColumnORM).filter_by(
            table_id=users.id, name="email"
        ).one().id

    # Record 3 views by the same user
    for _ in range(3):
        search_mod.record_view("alice", "column", col_id)
    recs = search_mod.recommend("alice")
    assert recs, "expected at least one recommendation"
    # The most-viewed column should appear
    names = [r["name"] for r in recs]
    assert "email" in names


def test_recommend_round_robin_caps_per_type(seeded_metadata, init_db):
    """At most 3 hits per type even if user viewed many of one type."""
    from services.dataset_service.metadata.models import ColumnORM, TableORM
    with get_metadata_session() as s:
        col_ids = [c.id for c in s.query(ColumnORM).limit(10).all()]
    assert len(col_ids) >= 5
    for cid in col_ids:
        search_mod.record_view("bob", "column", cid)
    recs = search_mod.recommend("bob", limit=20)
    type_counts: dict = {}
    for r in recs:
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
    # column capped at 3 by round-robin
    assert type_counts.get("column", 0) <= 3
