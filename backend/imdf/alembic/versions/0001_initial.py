"""empty message

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22 04:30:00.000000

P2-1-W1 initial schema — 5 核心表: users / projects / tasks / assets / datasets
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("email", sa.String(length=200), nullable=True, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="offline"),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_status", "users", ["status"])

    # ── projects ───────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("owner", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("members", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_owner", "projects", ["owner"])

    # ── tasks ──────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False, server_default="generic"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_owner", "tasks", ["owner"])
    op.create_index("ix_tasks_type", "tasks", ["type"])

    # ── assets ─────────────────────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="image"),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("path", sa.String(length=1000), nullable=True, server_default=""),
        sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_assets_type", "assets", ["type"])
    op.create_index("ix_assets_owner", "assets", ["owner"])

    # ── datasets ───────────────────────────────────────────────────────
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column("files_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_datasets_status", "datasets", ["status"])
    op.create_index("ix_datasets_created_by", "datasets", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_datasets_created_by", table_name="datasets")
    op.drop_index("ix_datasets_status", table_name="datasets")
    op.drop_table("datasets")

    op.drop_index("ix_assets_owner", table_name="assets")
    op.drop_index("ix_assets_type", table_name="assets")
    op.drop_table("assets")

    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_index("ix_tasks_owner", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_projects_owner", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
