"""⚠️  DEPRECATED — legacy chain (P21 P2 P5, 2026-07-11) ⚠️

This file lives in the **legacy alembic chain** at ``backend/alembic/``.
Per ``reports/p21_r2_audit_db.md`` §N1, the canonical chain is
``backend/imdf/alembic/``.  The project_members and
project_timeline_events tables this file creates are now also created
by ``0006_project_center_requirements.py`` in the imdf chain (the
canonical one) and that migration is the one operators should run.

This file is kept in place (not deleted) because some test DBs stamp
its revision into ``alembic_version``.  Use the imdf chain instead.

P5-R1-T1: ProjectCenter — 项目表 4 字段扩展 + project_members + project_timeline_events

Goals (per P5-R1-T1 spec, 2026-06-28):
  1. 扩展 ``projects`` 表 4 字段: priority / tags / start_date / due_date
     - 全部 nullable + 默认值, 不破坏 legacy p1_c_w1 数据
  2. 创建 ``project_members`` 关联表:
     - id (str PK) / project_id (FK projects) / user_id / role / joined_at
     - 唯一约束 (project_id, user_id)
  3. 创建 ``project_timeline_events`` 事件流:
     - id (str PK) / project_id (FK projects) / event_type / actor / ts / payload (JSON) / message
     - 复合索引 (project_id, ts)

跨方言:
  - SQLite: 用 String + JSON (TEXT)
  - PostgreSQL: 同样 String, JSON 列用 JSONB
  - 用 ``bind.dialect.name`` 检测后分派

Revision ID: p5_r1_t1_project_center
Revises: p13_c1_p99_db
Create Date: 2026-06-28 00:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "p5_r1_t1_project_center"
down_revision = "p13_c1_p99_db"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    """检测列是否已存在 (幂等迁移)。"""
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    cols = {c["name"] for c in insp.get_columns(table)}
    return column in cols


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _json_column() -> sa.types.TypeEngine:
    """PG → JSONB, 其他 → JSON。"""
    return sa.JSON().with_variant(
        # PostgreSQL JSONB
        __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB(),
        "postgresql",
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    is_postgres = bind.dialect.name == "postgresql"

    # ── 1. 扩展 projects 表 (4 字段) ─────────────────────────────────────
    # priority
    if not _has_column("projects", "priority"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "priority",
                    sa.String(length=8),
                    nullable=False,
                    server_default="P1",
                )
            )
            batch_op.create_index("ix_projects_priority", ["priority"])

    # tags (JSON / JSONB)
    if not _has_column("projects", "tags"):
        col_type = _json_column()
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "tags",
                    col_type,
                    nullable=True,
                )
            )

    # start_date / due_date — 用 String 兼容 SQLite + PG
    for col_name in ("start_date", "due_date"):
        if not _has_column("projects", col_name):
            with op.batch_alter_table("projects") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        col_name,
                        sa.String(length=32),
                        nullable=True,
                        server_default="",
                    )
                )

    # ── 2. project_members 表 ────────────────────────────────────────────
    if not _has_table("project_members"):
        op.create_table(
            "project_members",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
            sa.Column("joined_at", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"],
                ondelete="CASCADE", name="fk_project_members_project",
            ),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        )
        op.create_index("ix_project_members_project", "project_members", ["project_id"])
        op.create_index("ix_project_members_user", "project_members", ["user_id"])

    # ── 3. project_timeline_events 表 ────────────────────────────────────
    if not _has_table("project_timeline_events"):
        op.create_table(
            "project_timeline_events",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False, server_default="updated"),
            sa.Column("actor", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("ts", sa.String(length=32), nullable=False),
            sa.Column("payload", _json_column(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True, server_default=""),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"],
                ondelete="CASCADE", name="fk_project_timeline_project",
            ),
        )
        op.create_index(
            "ix_project_timeline_project_ts",
            "project_timeline_events",
            ["project_id", "ts"],
        )
        op.create_index(
            "ix_project_timeline_event_type",
            "project_timeline_events",
            ["event_type"],
        )

    # ── 4. ANALYZE (PG only) ─────────────────────────────────────────────
    if is_postgres:
        op.execute("ANALYZE projects")
        op.execute("ANALYZE project_members")
        op.execute("ANALYZE project_timeline_events")


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 删表
    if _has_table("project_timeline_events"):
        op.drop_index("ix_project_timeline_event_type", table_name="project_timeline_events")
        op.drop_index("ix_project_timeline_project_ts", table_name="project_timeline_events")
        op.drop_table("project_timeline_events")

    if _has_table("project_members"):
        op.drop_index("ix_project_members_user", table_name="project_members")
        op.drop_index("ix_project_members_project", table_name="project_members")
        op.drop_table("project_members")

    # 删 projects 扩展字段
    with op.batch_alter_table("projects") as batch_op:
        for col_name in ("due_date", "start_date", "tags", "priority"):
            try:
                batch_op.drop_column(col_name)
            except Exception:
                pass

    if not is_sqlite:
        op.execute("ANALYZE projects")