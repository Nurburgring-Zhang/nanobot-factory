"""Add UsageLog table — P2-3-W2 AI provider usage + billing.

Revision ID: 0002_usage_log
Revises: 0001_initial
Create Date: 2026-06-22 10:36:00.000000

设计:
- 主键 ``id`` (String 64) — 业务侧 ``ul_<12-hex>``。
- ``user_id`` 必填 (soft-ref, 不强制 FK)。
- ``created_at`` 必填, 默认 ``CURRENT_TIMESTAMP``, 加索引。
- 复合索引 ``(user_id, created_at)`` / ``(org_id, created_at)`` 覆盖"用户本月消耗"聚合查询。
- ``provider_id`` / ``status`` 单列索引。
- ``cost_usd`` Float — 单条记录 4-6 位小数足够。
- ``extra`` JSON — 后续扩展字段 (response_id / model_version / trace_id 等)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_usage_log"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=True, server_default=""),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("protocol", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=240), nullable=True, server_default=""),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="chat"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=60), nullable=True, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=True, server_default=""),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_usage_logs_created_at", "usage_logs", ["created_at"])
    op.create_index("ix_usage_logs_user_created", "usage_logs", ["user_id", "created_at"])
    op.create_index("ix_usage_logs_org_created", "usage_logs", ["org_id", "created_at"])
    op.create_index("ix_usage_logs_provider", "usage_logs", ["provider_id"])
    op.create_index("ix_usage_logs_status", "usage_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_usage_logs_status", table_name="usage_logs")
    op.drop_index("ix_usage_logs_provider", table_name="usage_logs")
    op.drop_index("ix_usage_logs_org_created", table_name="usage_logs")
    op.drop_index("ix_usage_logs_user_created", table_name="usage_logs")
    op.drop_index("ix_usage_logs_created_at", table_name="usage_logs")
    op.drop_table("usage_logs")
