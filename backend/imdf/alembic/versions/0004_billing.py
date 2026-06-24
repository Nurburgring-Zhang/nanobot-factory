"""P4-10-W1 — Billing tables: orders, subscriptions, usage_log.

Revision ID: 0004_billing
Revises: 0003_pg_models
Create Date: 2026-06-24 04:00:00.000000

设计:
- billing_orders: 订单 (含 status / payment_method / amount / currency)
- billing_subscriptions: 订阅 (含 current_period_start/end / status)
- billing_usage_log: 用量日志 (per user+dimension+period)
- 跨 DB 兼容: PG 用 JSONB / TIMESTAMP, SQLite 用 JSON / TIMESTAMP
- 复合索引覆盖高频查询
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_billing"
down_revision: Union[str, None] = "0003_pg_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_is_pg() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ── 1. billing_orders ────────────────────────────────────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE billing_orders (
                order_id VARCHAR(40) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                plan_id VARCHAR(40) NOT NULL,
                amount_cents BIGINT NOT NULL DEFAULT 0,
                currency VARCHAR(8) NOT NULL DEFAULT 'USD',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                payment_method VARCHAR(20) NOT NULL DEFAULT 'mock',
                external_ref VARCHAR(120) DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                fulfilled_at TIMESTAMP,
                refunded_at TIMESTAMP,
                refund_reason TEXT DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
    else:
        op.create_table(
            "billing_orders",
            sa.Column("order_id", sa.String(length=40), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("plan_id", sa.String(length=40), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("payment_method", sa.String(length=20), nullable=False, server_default="mock"),
            sa.Column("external_ref", sa.String(length=120), nullable=True, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
            sa.Column("refunded_at", sa.DateTime(), nullable=True),
            sa.Column("refund_reason", sa.Text(), nullable=True, server_default=""),
            sa.Column("metadata", sa.JSON(), nullable=True),
        )
    op.create_index("ix_billing_orders_user_id", "billing_orders", ["user_id"])
    op.create_index("ix_billing_orders_plan_id", "billing_orders", ["plan_id"])
    op.create_index("ix_billing_orders_status", "billing_orders", ["status"])
    op.create_index("ix_billing_orders_created_at", "billing_orders", ["created_at"])
    op.create_index("ix_billing_orders_user_status", "billing_orders", ["user_id", "status"])

    # ── 2. billing_subscriptions ──────────────────────────────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE billing_subscriptions (
                subscription_id VARCHAR(40) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                plan_id VARCHAR(40) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                current_period_start TIMESTAMP NOT NULL,
                current_period_end TIMESTAMP NOT NULL,
                cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_renewal_attempt_at TIMESTAMP,
                last_renewal_order_id VARCHAR(40) DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
    else:
        op.create_table(
            "billing_subscriptions",
            sa.Column("subscription_id", sa.String(length=40), primary_key=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("plan_id", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("current_period_start", sa.DateTime(), nullable=False),
            sa.Column("current_period_end", sa.DateTime(), nullable=False),
            sa.Column("cancel_at_period_end", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("last_renewal_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("last_renewal_order_id", sa.String(length=40), nullable=True, server_default=""),
            sa.Column("metadata", sa.JSON(), nullable=True),
        )
    op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions", ["user_id"])
    op.create_index("ix_billing_subscriptions_plan_id", "billing_subscriptions", ["plan_id"])
    op.create_index("ix_billing_subscriptions_status", "billing_subscriptions", ["status"])
    op.create_index("ix_billing_subscriptions_period_end", "billing_subscriptions", ["current_period_end"])
    op.create_unique_index("ux_billing_subscriptions_user", "billing_subscriptions", ["user_id"])

    # ── 3. billing_usage_log ──────────────────────────────────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE billing_usage_log (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                dimension VARCHAR(40) NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                period VARCHAR(8) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        op.create_table(
            "billing_usage_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("dimension", sa.String(length=40), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("period", sa.String(length=8), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    op.create_index("ix_billing_usage_log_user_dim_period", "billing_usage_log",
                    ["user_id", "dimension", "period"])
    op.create_index("ix_billing_usage_log_period", "billing_usage_log", ["period"])


def downgrade() -> None:
    op.drop_index("ix_billing_usage_log_period", table_name="billing_usage_log")
    op.drop_index("ix_billing_usage_log_user_dim_period", table_name="billing_usage_log")
    op.drop_table("billing_usage_log")

    op.drop_index("ux_billing_subscriptions_user", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_period_end", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_status", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_plan_id", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_user_id", table_name="billing_subscriptions")
    op.drop_table("billing_subscriptions")

    op.drop_index("ix_billing_orders_user_status", table_name="billing_orders")
    op.drop_index("ix_billing_orders_created_at", table_name="billing_orders")
    op.drop_index("ix_billing_orders_status", table_name="billing_orders")
    op.drop_index("ix_billing_orders_plan_id", table_name="billing_orders")
    op.drop_index("ix_billing_orders_user_id", table_name="billing_orders")
    op.drop_table("billing_orders")
