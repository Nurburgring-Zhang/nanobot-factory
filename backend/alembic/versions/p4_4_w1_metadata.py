"""P4-4-W1: 10 metadata tables for dataset_service (OpenMetadata-inspired).

Creates:
  md_databases / md_schemas / md_tables / md_columns / md_datasets /
  md_tags / md_tag_assignments / md_glossaries / md_glossary_terms /
  md_term_relations

Revision ID: p4_4_w1_metadata
Revises:
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "p4_4_w1_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # ── md_databases ─────────────────────────────────────────────────────────
    op.create_table(
        "md_databases",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("service", sa.String(length=64), nullable=False, server_default="custom"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("host", sa.String(length=256), server_default=""),
        sa.Column("port", sa.String(length=8), server_default=""),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_md_databases_service", "md_databases", ["service"])

    # ── md_schemas ───────────────────────────────────────────────────────────
    op.create_table(
        "md_schemas",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("database_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["database_id"], ["md_databases.id"],
            ondelete="CASCADE", name="fk_md_schemas_database",
        ),
    )
    op.create_index("ix_md_schemas_database", "md_schemas", ["database_id"])
    op.create_index(
        "uq_md_schemas_db_name", "md_schemas", ["database_id", "name"], unique=True
    )

    # ── md_tables ────────────────────────────────────────────────────────────
    op.create_table(
        "md_tables",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("schema_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("table_type", sa.String(length=32), server_default="table"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("owner", sa.String(length=128), server_default=""),
        sa.Column("row_count_estimate", sa.String(length=32), server_default="0"),
        sa.Column("extra", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["md_schemas.id"],
            ondelete="CASCADE", name="fk_md_tables_schema",
        ),
    )
    op.create_index("ix_md_tables_schema", "md_tables", ["schema_id"])
    op.create_index(
        "uq_md_tables_schema_name", "md_tables", ["schema_id", "name"], unique=True
    )

    # ── md_columns ───────────────────────────────────────────────────────────
    op.create_table(
        "md_columns",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("table_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("data_type", sa.String(length=64), server_default="string"),
        sa.Column("nullable", sa.String(length=8), server_default="true"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("ordinal", sa.String(length=16), server_default="0"),
        sa.Column("extra", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["table_id"], ["md_tables.id"],
            ondelete="CASCADE", name="fk_md_columns_table",
        ),
    )
    op.create_index("ix_md_columns_table", "md_columns", ["table_id"])
    op.create_index(
        "uq_md_columns_table_name", "md_columns", ["table_id", "name"], unique=True
    )

    # ── md_datasets ──────────────────────────────────────────────────────────
    op.create_table(
        "md_datasets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False, unique=True),
        sa.Column("format", sa.String(length=32), server_default="parquet"),
        sa.Column("size_bytes", sa.String(length=32), server_default="0"),
        sa.Column("row_count", sa.String(length=32), server_default="0"),
        sa.Column("columns_json", sa.Text(), server_default="[]"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("owner", sa.String(length=128), server_default=""),
        sa.Column("tier", sa.String(length=16), server_default="bronze"),
        sa.Column("location", sa.String(length=512), server_default=""),
        sa.Column("extra", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_md_datasets_tier", "md_datasets", ["tier"])

    # ── md_tags ──────────────────────────────────────────────────────────────
    op.create_table(
        "md_tags",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("category", sa.String(length=64), server_default="general"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("color", sa.String(length=16), server_default="#888888"),
        sa.Column("source", sa.String(length=32), server_default="manual"),
        sa.Column("sensitivity_level", sa.String(length=8), server_default="0"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_md_tags_category", "md_tags", ["category"])
    op.create_index("ix_md_tags_source", "md_tags", ["source"])

    # ── md_tag_assignments ───────────────────────────────────────────────────
    op.create_table(
        "md_tag_assignments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tag_id", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="manual"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["md_tags.id"],
            ondelete="CASCADE", name="fk_md_tag_assignments_tag",
        ),
    )
    op.create_index("ix_md_tag_assignments_tag", "md_tag_assignments", ["tag_id"])
    op.create_index(
        "ix_md_tag_assignments_target", "md_tag_assignments",
        ["target_type", "target_id"],
    )
    op.create_index(
        "uq_md_tag_assignments", "md_tag_assignments",
        ["tag_id", "target_type", "target_id"], unique=True,
    )

    # ── md_glossaries ────────────────────────────────────────────────────────
    op.create_table(
        "md_glossaries",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("owner", sa.String(length=128), server_default=""),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )

    # ── md_glossary_terms ────────────────────────────────────────────────────
    op.create_table(
        "md_glossary_terms",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("glossary_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("definition", sa.Text(), server_default=""),
        sa.Column("related_terms_json", sa.Text(), server_default="[]"),
        sa.Column("extra", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["glossary_id"], ["md_glossaries.id"],
            ondelete="CASCADE", name="fk_md_glossary_terms_glossary",
        ),
    )
    op.create_index("ix_md_glossary_terms_glossary", "md_glossary_terms", ["glossary_id"])
    op.create_index(
        "uq_md_glossary_terms_glossary_name", "md_glossary_terms",
        ["glossary_id", "name"], unique=True,
    )

    # ── md_term_relations ────────────────────────────────────────────────────
    op.create_table(
        "md_term_relations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("from_term_id", sa.String(length=32), nullable=False),
        sa.Column("to_term_id", sa.String(length=32), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), server_default=""),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_term_id"], ["md_glossary_terms.id"],
            ondelete="CASCADE", name="fk_md_term_relations_from",
        ),
        sa.ForeignKeyConstraint(
            ["to_term_id"], ["md_glossary_terms.id"],
            ondelete="CASCADE", name="fk_md_term_relations_to",
        ),
    )
    op.create_index("ix_md_term_relations_from", "md_term_relations", ["from_term_id"])
    op.create_index("ix_md_term_relations_to", "md_term_relations", ["to_term_id"])
    op.create_index(
        "uq_md_term_relations", "md_term_relations",
        ["from_term_id", "to_term_id", "relation_type"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("md_term_relations")
    op.drop_table("md_glossary_terms")
    op.drop_table("md_glossaries")
    op.drop_table("md_tag_assignments")
    op.drop_table("md_tags")
    op.drop_table("md_datasets")
    op.drop_table("md_columns")
    op.drop_table("md_tables")
    op.drop_table("md_schemas")
    op.drop_table("md_databases")
