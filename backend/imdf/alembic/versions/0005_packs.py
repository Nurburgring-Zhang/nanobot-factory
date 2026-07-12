"""P5-R1-T3 Pack tables: packs + pack_assets.

Revision ID: 0005_packs
Revises: 0004_billing
Create Date: 2026-06-28 00:32:00.000000

表:
- packs: 数据包/任务包 (type/has_data/source/status + 状态机 + 路由历史 + 元数据)
- pack_assets: 包 ↔ 资产多对多关联表
- 双 DB 兼容: PG 用 JSONB/TIMESTAMP, SQLite 用 JSON/TIMESTAMP
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_packs"
down_revision: Union[str, None] = "0004_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_is_pg() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ====== 1. packs 主表 ======
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE packs (
                id VARCHAR(40) PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                type VARCHAR(20) NOT NULL DEFAULT 'data_pack',
                has_data SMALLINT NOT NULL DEFAULT 0,
                source VARCHAR(20) NOT NULL DEFAULT 'upload',
                status VARCHAR(20) NOT NULL DEFAULT 'created',
                requirement_id VARCHAR(40) DEFAULT '',
                project_id VARCHAR(40) DEFAULT '',
                asset_count INTEGER NOT NULL DEFAULT 0,
                dataset_id VARCHAR(40) DEFAULT '',
                task_type VARCHAR(40) DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                route_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        op.create_table(
            "packs",
            sa.Column("id", sa.String(length=40), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("type", sa.String(length=20), nullable=False, server_default="data_pack"),
            sa.Column("has_data", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="upload"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
            sa.Column("requirement_id", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("project_id", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("asset_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dataset_id", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("task_type", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("route_history", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    op.create_index("ix_packs_requirement", "packs", ["requirement_id"])
    op.create_index("ix_packs_project", "packs", ["project_id"])
    op.create_index("ix_packs_type", "packs", ["type"])
    op.create_index("ix_packs_status", "packs", ["status"])
    op.create_index("ix_packs_requirement_status", "packs", ["requirement_id", "status"])

    # ====== 2. pack_assets 关联表 ======
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE pack_assets (
                id BIGSERIAL PRIMARY KEY,
                pack_id VARCHAR(40) NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
                asset_id VARCHAR(64) NOT NULL,
                asset_type VARCHAR(20) DEFAULT 'image',
                position INTEGER NOT NULL DEFAULT 0,
                added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pack_id, asset_id)
            )
        """)
    else:
        op.create_table(
            "pack_assets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("pack_id", sa.String(length=40), nullable=False),
            sa.Column("asset_id", sa.String(length=64), nullable=False),
            sa.Column("asset_type", sa.String(length=20), nullable=True, server_default="image"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("pack_id", "asset_id", name="uq_pack_assets_pack_asset"),
        )
        # SQLite 外键 (PRAGMA foreign_keys=ON 在连接层开启)
        try:
            op.create_foreign_key(
                "fk_pack_assets_pack_id", "pack_assets", "packs",
                ["pack_id"], ["id"], ondelete="CASCADE",
            )
        except Exception:
            pass

    op.create_index("ix_pack_assets_pack", "pack_assets", ["pack_id"])
    op.create_index("ix_pack_assets_asset", "pack_assets", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_pack_assets_asset", table_name="pack_assets")
    op.drop_index("ix_pack_assets_pack", table_name="pack_assets")
    op.drop_table("pack_assets")
    op.drop_index("ix_packs_requirement_status", table_name="packs")
    op.drop_index("ix_packs_status", table_name="packs")
    op.drop_index("ix_packs_type", table_name="packs")
    op.drop_index("ix_packs_project", table_name="packs")
    op.drop_index("ix_packs_requirement", table_name="packs")
    op.drop_table("packs")