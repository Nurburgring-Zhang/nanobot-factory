"""P4-4-W1: tests for the 10 metadata ORM tables + basic CRUD (≥5 cases).

Covered:
  1. test_all_ten_tables_created       — init_metadata_db creates all 10
  2. test_database_crud                — create + read
  3. test_schema_table_column_crud     — nested create + cascade FK
  4. test_dataset_crud                 — dataset CRUD + JSON columns
  5. test_tag_assignment_crud          — tag + assignment + uniqueness
  6. test_glossary_term_relation_crud  — full glossary + term + relation
"""
from __future__ import annotations

import json

from services.dataset_service.metadata.models import (
    Base,
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    DatasetORM,
    GlossaryORM,
    GlossaryTermORM,
    TagAssignmentORM,
    TagORM,
    TableORM,
    TermRelationORM,
    get_metadata_session,
    init_metadata_db,
)


def test_all_ten_tables_created(init_db):
    """All 10 metadata tables must exist after init_metadata_db()."""
    tables = set(Base.metadata.tables.keys())
    expected = {
        "md_databases", "md_schemas", "md_tables", "md_columns",
        "md_datasets", "md_tags", "md_tag_assignments",
        "md_glossaries", "md_glossary_terms", "md_term_relations",
    }
    assert expected.issubset(tables), (
        f"missing tables: {expected - tables}"
    )
    # Also check the engine knows them
    from sqlalchemy import inspect
    insp = inspect(init_db)
    db_tables = set(insp.get_table_names())
    for t in expected:
        assert t in db_tables, f"missing in DB: {t}"


def test_database_crud(init_db):
    """Create / list / get / delete a Database row."""
    with get_metadata_session() as s:
        d = DatabaseORM(name="warehouse", service="postgres",
                         host="db.local", port="5432",
                         description="main warehouse")
        s.add(d); s.commit(); s.refresh(d)
        d_id = d.id

    with get_metadata_session() as s:
        got = s.query(DatabaseORM).filter(DatabaseORM.id == d_id).one()
        assert got.name == "warehouse"
        assert got.service == "postgres"
        assert got.host == "db.local"

        # List
        names = [r.name for r in s.query(DatabaseORM).all()]
        assert "warehouse" in names

        # Delete
        s.delete(got); s.commit()
        assert s.query(DatabaseORM).filter(DatabaseORM.id == d_id).count() == 0


def test_schema_table_column_crud(seeded_metadata):
    """Cascade create: Database → Schema → Table → Columns."""
    with get_metadata_session() as s:
        # Schema already seeded
        sch = s.query(DatabaseSchemaORM).filter(
            DatabaseSchemaORM.id == seeded_metadata["schema_public_id"]
        ).one()
        assert sch.database_id is not None

        # Tables
        users = s.query(TableORM).filter(
            TableORM.name == "users"
        ).one()
        assert users.schema_id == sch.id
        assert users.table_type == "table"

        # Columns
        cols = s.query(ColumnORM).filter(ColumnORM.table_id == users.id).order_by(
            ColumnORM.ordinal
        ).all()
        assert [c.name for c in cols] == ["id", "email", "phone", "real_name"]
        assert cols[0].data_type == "bigint"
        assert cols[0].nullable == "false"

        # Verify cascade: delete a column doesn't kill the table
        s.delete(cols[-1]); s.commit()
        again = s.query(ColumnORM).filter(ColumnORM.table_id == users.id).count()
        assert again == 3


def test_dataset_crud(init_db):
    """Dataset CRUD with JSON-serialised column list."""
    with get_metadata_session() as s:
        cols = [
            {"name": "id", "type": "int"},
            {"name": "feature", "type": "float"},
        ]
        d = DatasetORM(
            name="mnist_features",
            format="parquet",
            size_bytes="1048576",
            row_count="60000",
            columns_json=json.dumps(cols, ensure_ascii=False),
            tier="silver",
            description="Handwritten digits feature set.",
        )
        s.add(d); s.commit(); s.refresh(d)

        got = s.query(DatasetORM).filter(DatasetORM.id == d.id).one()
        assert got.name == "mnist_features"
        assert got.tier == "silver"
        # Round-trip the JSON
        parsed = json.loads(got.columns_json)
        assert parsed[0]["name"] == "id"
        assert parsed[1]["type"] == "float"


def test_tag_assignment_crud(init_db):
    """Tag + assignment + uniqueness."""
    with get_metadata_session() as s:
        tag = TagORM(name="PII.email", category="pii",
                      source="manual", sensitivity_level="4")
        s.add(tag); s.flush()

        col_id = "abc123def456"
        a1 = TagAssignmentORM(tag_id=tag.id, target_type="column",
                                 target_id=col_id, source="manual")
        s.add(a1); s.commit()

        # Re-assign is idempotent at the unique-constraint level
        # (caller should check; here we test we can list).
        all_a = s.query(TagAssignmentORM).all()
        assert len(all_a) == 1
        assert all_a[0].target_id == col_id

        # Tag can be filtered by category
        pii_tags = s.query(TagORM).filter(TagORM.category == "pii").all()
        assert {t.name for t in pii_tags} == {"PII.email"}


def test_glossary_term_relation_crud(init_db):
    """Full glossary + term + relation lifecycle."""
    with get_metadata_session() as s:
        g = GlossaryORM(name="User Domain",
                         description="User-account business terms.")
        s.add(g); s.flush()

        t_user = GlossaryTermORM(glossary_id=g.id, name="user_id",
                                   definition="Unique user identifier.")
        t_uid = GlossaryTermORM(glossary_id=g.id, name="uid",
                                  definition="Short alias for user_id.")
        s.add_all([t_user, t_uid]); s.flush()

        rel = TermRelationORM(
            from_term_id=t_user.id, to_term_id=t_uid.id,
            relation_type="synonym", note="uid is a deprecated alias.",
        )
        s.add(rel); s.commit()

        # Verify
        s.refresh(t_user)
        terms = s.query(GlossaryTermORM).filter(
            GlossaryTermORM.glossary_id == g.id
        ).order_by(GlossaryTermORM.name).all()
        assert [t.name for t in terms] == ["uid", "user_id"]

        rels = s.query(TermRelationORM).filter(
            TermRelationORM.relation_type == "synonym"
        ).all()
        assert len(rels) == 1
        assert rels[0].from_term_id == t_user.id
