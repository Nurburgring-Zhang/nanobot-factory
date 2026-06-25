"""P4-4-W1: tags tests (auto PII + manual + propagation) (≥3 cases)."""
from __future__ import annotations

from services.dataset_service.metadata import tags as tags_mod
from services.dataset_service.metadata.models import (
    TagAssignmentORM, TagORM, get_metadata_session,
)


def test_detect_pii_by_name():
    """Regex-based PII detection covers common column name patterns."""
    cases = [
        ("email", "PII.email", 4),
        ("mail", "PII.email", 4),
        ("user_email", "PII.email", 4),
        ("phone_number", "PII.phone", 4),
        ("id_card", "PII.id_card", 5),
        ("password", "PII.password", 5),
        ("real_name", "PII.real_name", 3),
        ("first_name", "PII.real_name", 3),
        ("birthday", "PII.birthday", 3),
        ("gender", "PII.gender", 2),
        ("country", "PII.nationality", 2),
        ("ip_addr", "PII.ip", 2),
        ("created_at", None, None),
        ("user_id", None, None),
    ]
    for col, expected_tag, expected_level in cases:
        m = tags_mod.detect_pii_by_name(col)
        if expected_tag is None:
            assert m is None, f"{col} should not match"
        else:
            assert m is not None, f"{col} should match {expected_tag}"
            assert m.tag_name == expected_tag
            assert m.sensitivity_level == expected_level


def test_detect_pii_by_value():
    """Value-based PII detection (email / phone / Chinese name)."""
    assert tags_mod.detect_pii_by_value(["alice@example.com"]) == "PII.email"
    assert tags_mod.detect_pii_by_value(["+1 555-123-4567"]) == "PII.phone"
    assert tags_mod.detect_pii_by_value(["张三"]) == "PII.real_name"
    assert tags_mod.detect_pii_by_value(["李四丰"]) == "PII.real_name"
    # Non-PII returns None
    assert tags_mod.detect_pii_by_value(["hello world", "abc"]) is None
    # Empty
    assert tags_mod.detect_pii_by_value(["", "  "]) is None


def test_auto_tag_pii_assigns(seeded_metadata, init_db):
    """auto_tag_pii should tag columns whose names match PII patterns."""
    res = tags_mod.auto_tag_pii()
    assert res.scanned_columns >= 9  # the seeded schema has 9 columns
    names = {m.column_name for m in res.matches}
    # At minimum we expect the seeded PII-shaped columns to be flagged
    assert {"email", "phone", "real_name"}.issubset(names)
    assert res.tags_created >= 3
    assert res.assignments_created >= 3

    # Verify assignments in DB
    with get_metadata_session() as s:
        all_assignments = s.query(TagAssignmentORM).filter(
            TagAssignmentORM.target_type == "column",
            TagAssignmentORM.source == "auto_pii",
        ).all()
        assert len(all_assignments) >= 3

        pii_tags = s.query(TagORM).filter(TagORM.category == "pii").all()
        names = {t.name for t in pii_tags}
        assert {"PII.email", "PII.phone", "PII.real_name"}.issubset(names)


def test_propagate_column_tags(seeded_metadata, init_db):
    """After auto PII tagging, propagation should mirror column tags
    onto their parent table."""
    tags_mod.auto_tag_pii()
    res = tags_mod.propagate_column_tags(only_pii=True, dry_run=False)
    assert res.propagated_assignments >= 1
    assert res.rolled_up_tables >= 1
    # Confirm a table-level PII assignment now exists
    with get_metadata_session() as s:
        table_assignments = s.query(TagAssignmentORM).filter(
            TagAssignmentORM.target_type == "table",
            TagAssignmentORM.source == "propagation",
        ).all()
        assert len(table_assignments) >= 1


def test_tag_crud_and_assign(seeded_metadata, init_db):
    """Manual CRUD + assignment + idempotent re-assign."""
    tag = tags_mod.upsert_tag("finance.revenue", category="business",
                                color="#22aa22", source="manual",
                                sensitivity_level=2)
    assert tag.id
    # Re-upsert should not duplicate
    again = tags_mod.upsert_tag("finance.revenue", category="business")
    assert again.id == tag.id

    # Assign to a column
    orders_id = seeded_metadata["table_ids"]["orders"]
    a1 = tags_mod.assign_tag(tag.id, "column", "fake-col-id-orders")
    assert a1["tag_id"] == tag.id
    # Re-assign returns the existing row (idempotent)
    a2 = tags_mod.assign_tag(tag.id, "column", "fake-col-id-orders")
    assert a2["id"] == a1["id"]

    # Listing
    listed = tags_mod.list_assignments(tag_id=tag.id)
    assert len(listed) >= 1
    assert listed[0]["target_type"] == "column"

    # Unassign
    assert tags_mod.unassign_tag(tag.id, "column", "fake-col-id-orders")
    listed2 = tags_mod.list_assignments(tag_id=tag.id)
    assert all(a["target_id"] != "fake-col-id-orders" for a in listed2)
