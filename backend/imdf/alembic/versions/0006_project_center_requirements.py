"""P21 P2 P1 — 4 ORM tables missing from the alembic chain.

Revision ID: 0006_project_center_requirements
Revises: 0005_packs
Create Date: 2026-07-11 05:36:00.000000

背景 (per ``reports/p21_r2_audit_db.md`` §N3):

R1 originally claimed that 10 ORM tables lacked migrations. R2 re-audited the
project and discovered the real imdf alembic chain at ``backend/imdf/alembic/``
(``env.py:37`` correctly points to ``Base.metadata``) — not the legacy
``backend/alembic/`` chain that R1 inspected. With that correction, only
**4** ORM tables are genuinely missing from the imdf alembic chain:

  1. ``project_members``            — ``models/project.py:69``   (ProjectMember)
  2. ``project_timeline_events``   — ``models/project.py:109``  (ProjectTimelineEvent)
  3. ``requirements``               — ``models/requirement.py:54``  (RequirementRow)
  4. ``requirement_tasks``          — ``models/requirement.py:115`` (TaskRow)

Without this migration, ``init_db()`` (``db/__init__.py``) would create
the tables via ``Base.metadata.create_all()`` (a one-shot at startup) but
the alembic chain would have no record of them. The next ``alembic
upgrade head`` on a fresh database would be a no-op for these tables
**as long as** ``init_db()`` ran first — but on a database that was set
up via the alembic chain alone (PG production path), these four tables
would never exist, and the first ``ProjectMember`` write or
``Requirement`` query would crash with ``relation does not exist``.

Fix:

  * Add ``op.create_table`` (SQLite) or raw ``CREATE TABLE`` (PG) for
    each of the 4 tables, mirroring the column layout defined in
    ``models/project.py`` and ``models/requirement.py``.
  * Add the indexes declared in the model ``__table_args__`` blocks.
  * Cross-dialect JSON columns use ``get_jsonb_column()`` (PG → JSONB,
    SQLite → JSON) so the model and the DDL stay in sync.
  * The migration is **additive** — no existing tables are dropped or
    altered, in line with the alembic append-only convention called out
    in the task hard-rules.

Why one migration and not two:

  * Task spec asks for a single ``0042_add_missing_tables.py`` file.
    Using the project's 4-digit numeric prefix convention, this is
    ``0006_project_center_requirements.py`` so it slots into the
    existing imdf chain as the next revision after ``0005_packs``.

Cross-dialect strategy (mirrors 0003_pg_models.py / 0005_packs.py):

  * ``_dialect_is_pg()`` helper — detects the bound connection's
    dialect so the PG-only ``op.execute("CREATE TABLE ...")`` is only
    reached on PostgreSQL.
  * SQLite falls back to ``op.create_table`` with ``sa.Column`` kwargs
    so SQLAlchemy picks the right ``JSON`` / ``BigInteger`` / etc.
    variant for the file-based engine.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_project_center_requirements"
down_revision: Union[str, None] = "0005_packs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_is_pg() -> bool:
    """Detect the bound connection's dialect — used to switch between
    raw PG ``CREATE TABLE`` (for ``JSONB`` / native types) and SQLite's
    ``op.create_table`` with cross-dialect ``sa.Column`` types.
    """
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _jsonb_column():
    """Return a cross-dialect JSON column type — PG → JSONB, SQLite → JSON.

    Matches ``db.postgres.get_jsonb_column()`` so the model and the DDL
    stay in lock-step. We do not import that helper directly because
    alembic migrations run in their own sys.path and the helper does a
    runtime ``from sqlalchemy.dialects.postgresql import JSONB`` which
    would still resolve, but using the local helper keeps the migration
    self-contained.
    """
    try:
        from sqlalchemy.dialects.postgresql import JSONB
        return sa.JSON().with_variant(JSONB(), "postgresql")
    except Exception:  # pragma: no cover — SQLAlchemy without PG dialect
        return sa.JSON()


def upgrade() -> None:
    is_pg = _dialect_is_pg()

    # ── 1. project_members ─────────────────────────────────────────────────
    if is_pg:
        op.execute("""
            CREATE TABLE project_members (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'member',
                joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_project_members_project_user
                    UNIQUE (project_id, user_id)
            )
        """)
    else:
        op.create_table(
            "project_members",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
            sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        )
    op.create_index("ix_project_members_project", "project_members", ["project_id"])
    op.create_index("ix_project_members_user", "project_members", ["user_id"])

    # ── 2. project_timeline_events ─────────────────────────────────────────
    if is_pg:
        op.execute("""
            CREATE TABLE project_timeline_events (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                actor VARCHAR(64) NOT NULL DEFAULT '',
                ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                message TEXT DEFAULT ''
            )
        """)
    else:
        op.create_table(
            "project_timeline_events",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("ts", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("payload", _jsonb_column(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True, server_default=""),
        )
    op.create_index("ix_project_timeline_project_ts", "project_timeline_events", ["project_id", "ts"])
    op.create_index("ix_project_timeline_event_type", "project_timeline_events", ["event_type"])

    # ── 3. requirements ───────────────────────────────────────────────────
    # Model declares created_at / updated_at / closed_at as ``String(64)``
    # (ISO timestamps) — preserved here to keep wire-format identical.
    if is_pg:
        op.execute("""
            CREATE TABLE requirements (
                id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(500) NOT NULL DEFAULT '',
                type VARCHAR(50) NOT NULL DEFAULT 'data_annotation',
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                priority VARCHAR(8) NOT NULL DEFAULT 'P2',
                created_by VARCHAR(64) NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                acceptance_criteria TEXT DEFAULT '',
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at VARCHAR(64) NOT NULL DEFAULT '',
                updated_at VARCHAR(64) NOT NULL DEFAULT '',
                closed_at VARCHAR(64) DEFAULT '',
                project_id VARCHAR(64),
                pack_id VARCHAR(64),
                qc_status VARCHAR(20),
                delivery_id VARCHAR(64),
                due_date VARCHAR(32) DEFAULT '',
                owner VARCHAR(64) NOT NULL DEFAULT ''
            )
        """)
    else:
        op.create_table(
            "requirements",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("type", sa.String(length=50), nullable=False, server_default="data_annotation"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("priority", sa.String(length=8), nullable=False, server_default="P2"),
            sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=True, server_default=""),
            sa.Column("acceptance_criteria", sa.Text(), nullable=True, server_default=""),
            sa.Column("tags", _jsonb_column(), nullable=True),
            sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("closed_at", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("project_id", sa.String(length=64), nullable=True),
            sa.Column("pack_id", sa.String(length=64), nullable=True),
            sa.Column("qc_status", sa.String(length=20), nullable=True),
            sa.Column("delivery_id", sa.String(length=64), nullable=True),
            sa.Column("due_date", sa.String(length=32), nullable=True, server_default=""),
            sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
        )
    op.create_index("ix_requirements_status", "requirements", ["status"])
    op.create_index("ix_requirements_priority", "requirements", ["priority"])
    op.create_index("ix_requirements_type", "requirements", ["type"])
    op.create_index("ix_requirements_created_by", "requirements", ["created_by"])
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])
    op.create_index("ix_requirements_pack_id", "requirements", ["pack_id"])
    op.create_index("ix_requirements_delivery_id", "requirements", ["delivery_id"])
    op.create_index("ix_requirements_owner", "requirements", ["owner"])

    # ── 4. requirement_tasks ──────────────────────────────────────────────
    if is_pg:
        op.execute("""
            CREATE TABLE requirement_tasks (
                id VARCHAR(64) PRIMARY KEY,
                requirement_id VARCHAR(64) NOT NULL,
                title VARCHAR(500) NOT NULL DEFAULT '',
                assignee VARCHAR(64) NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                acceptance_criteria TEXT DEFAULT '',
                estimated_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
                actual_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
                priority VARCHAR(8) NOT NULL DEFAULT 'P2',
                created_at VARCHAR(64) DEFAULT '',
                completed_at VARCHAR(64) DEFAULT '',
                notes TEXT DEFAULT ''
            )
        """)
    else:
        op.create_table(
            "requirement_tasks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("requirement_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("assignee", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("acceptance_criteria", sa.Text(), nullable=True, server_default=""),
            sa.Column("estimated_hours", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_hours", sa.Float(), nullable=False, server_default="0"),
            sa.Column("priority", sa.String(length=8), nullable=False, server_default="P2"),
            sa.Column("created_at", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("completed_at", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("notes", sa.Text(), nullable=True, server_default=""),
        )
    op.create_index("ix_requirement_tasks_requirement_id", "requirement_tasks", ["requirement_id"])
    op.create_index("ix_requirement_tasks_assignee", "requirement_tasks", ["assignee"])
    op.create_index("ix_requirement_tasks_status", "requirement_tasks", ["status"])
    op.create_index("ix_requirement_tasks_priority", "requirement_tasks", ["priority"])


def downgrade() -> None:
    # Drop in reverse creation order to keep the migration reversible.
    op.drop_index("ix_requirement_tasks_priority", table_name="requirement_tasks")
    op.drop_index("ix_requirement_tasks_status", table_name="requirement_tasks")
    op.drop_index("ix_requirement_tasks_assignee", table_name="requirement_tasks")
    op.drop_index("ix_requirement_tasks_requirement_id", table_name="requirement_tasks")
    op.drop_table("requirement_tasks")

    op.drop_index("ix_requirements_owner", table_name="requirements")
    op.drop_index("ix_requirements_delivery_id", table_name="requirements")
    op.drop_index("ix_requirements_pack_id", table_name="requirements")
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_index("ix_requirements_created_by", table_name="requirements")
    op.drop_index("ix_requirements_type", table_name="requirements")
    op.drop_index("ix_requirements_priority", table_name="requirements")
    op.drop_index("ix_requirements_status", table_name="requirements")
    op.drop_table("requirements")

    op.drop_index("ix_project_timeline_event_type", table_name="project_timeline_events")
    op.drop_index("ix_project_timeline_project_ts", table_name="project_timeline_events")
    op.drop_table("project_timeline_events")

    op.drop_index("ix_project_members_user", table_name="project_members")
    op.drop_index("ix_project_members_project", table_name="project_members")
    op.drop_table("project_members")
