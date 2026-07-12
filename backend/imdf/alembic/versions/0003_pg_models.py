"""P3-1-W1 — 5 new models: embeddings, workflows, agent_tasks, audit_chain_entries.

Revision ID: 0003_pg_models
Revises: 0002_usage_log
Create Date: 2026-06-22 11:30:00.000000

设计要点:
- 跨 DB 兼容: ``sa.JSON()`` 在 PG 上自动用 JSON, 在 SQLite 上存 TEXT。
  pgvector ``Vector(1024)`` 走 ``op.execute()`` 走原生 SQL (alembic 不知道 ``pgvector`` 类型)。
- ``server_default=sa.text("CURRENT_TIMESTAMP")`` 跨 PG/SQLite 通用。
- 复合索引 ``(entity_type, entity_id)`` / ``(status, priority)`` 覆盖高频查询。

风险点:
- 如果当前 DB 不是 PG, 装 pgvector 的 SQL 会 fail — 但 ``op.execute()`` 走 ``IF NOT EXISTS``
  + dialect 检测, SQLite 上会 skip。
- ``Vector(1024)`` DDL 仅在 PG 上执行, 走 ``op.execute()`` 显式 SQL (不能用 ``sa.Column(..., Vector(1024))``,
  alembic 不知道 pgvector 类型)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_pg_models"
down_revision: Union[str, None] = "0002_usage_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_is_pg() -> bool:
    """检测当前 connection 方言 — 仅 PG 跑 pgvector 专属 DDL。"""
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ── 0. (PG only) CREATE EXTENSION vector ─────────────────────────────
    if _dialect_is_pg():
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            # 已存在 / 无 superuser → 跳过, 后续 Vector 列可能 fail
            pass

    # ── 1. embeddings ───────────────────────────────────────────────────
    if _dialect_is_pg():
        # PG: 用 pgvector Vector(1024) + JSONB
        op.execute("""
            CREATE TABLE embeddings (
                id VARCHAR(64) PRIMARY KEY,
                entity_type VARCHAR(40) NOT NULL,
                entity_id VARCHAR(64) NOT NULL,
                vector vector(1024) NOT NULL,
                model VARCHAR(120) NOT NULL DEFAULT 'bge-large-zh',
                meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                chunk_text TEXT DEFAULT '',
                extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        # SQLite: 用 JSON 存 vector 数组
        op.create_table(
            "embeddings",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("entity_type", sa.String(length=40), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=False),
            sa.Column("vector", sa.JSON(), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False, server_default="bge-large-zh"),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("chunk_text", sa.Text(), nullable=True, server_default=""),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    op.create_index("ix_embeddings_entity_type", "embeddings", ["entity_type"])
    op.create_index("ix_embeddings_entity_id", "embeddings", ["entity_id"])
    op.create_index("ix_embeddings_model", "embeddings", ["model"])
    op.create_index("ix_embeddings_created_at", "embeddings", ["created_at"])
    op.create_index("ix_embeddings_entity", "embeddings", ["entity_type", "entity_id"])
    # (PG only) 在 vector 列上加 ivfflat / hnsw 索引 — 后续按需开, 这里先不加
    # CREATE INDEX ix_embeddings_vector ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);

    # ── 2. workflows ────────────────────────────────────────────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE workflows (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                owner VARCHAR(64) NOT NULL DEFAULT '',
                project_id VARCHAR(64) DEFAULT '',
                dag_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                steps_count INTEGER NOT NULL DEFAULT 0,
                last_run_at TIMESTAMP,
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                config JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        op.create_table(
            "workflows",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("project_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("dag_json", sa.JSON(), nullable=True),
            sa.Column("steps_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    op.create_index("ix_workflows_status", "workflows", ["status"])
    op.create_index("ix_workflows_owner", "workflows", ["owner"])
    op.create_index("ix_workflows_project_id", "workflows", ["project_id"])
    op.create_index("ix_workflows_created_at", "workflows", ["created_at"])

    # ── 3. agent_tasks ──────────────────────────────────────────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE agent_tasks (
                id VARCHAR(64) PRIMARY KEY,
                agent_type VARCHAR(40) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 5,
                user_id VARCHAR(64) DEFAULT '',
                org_id VARCHAR(64) DEFAULT '',
                project_id VARCHAR(64) DEFAULT '',
                workflow_id VARCHAR(64) DEFAULT '',
                parent_id VARCHAR(64) DEFAULT '',
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                result JSONB,
                error JSONB,
                trace_id VARCHAR(64) DEFAULT '',
                idempotency_key VARCHAR(80) DEFAULT '',
                celery_task_id VARCHAR(80) DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                queued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                expires_at TIMESTAMP,
                error_message TEXT DEFAULT ''
            )
        """)
    else:
        op.create_table(
            "agent_tasks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("agent_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("user_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("org_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("project_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("workflow_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("parent_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.JSON(), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True, server_default=""),
            sa.Column("idempotency_key", sa.String(length=80), nullable=True, server_default=""),
            sa.Column("celery_task_id", sa.String(length=80), nullable=True, server_default=""),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("queued_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True, server_default=""),
        )
    op.create_index("ix_agent_tasks_agent_type", "agent_tasks", ["agent_type"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_priority", "agent_tasks", ["priority"])
    op.create_index("ix_agent_tasks_user_id", "agent_tasks", ["user_id"])
    op.create_index("ix_agent_tasks_org_id", "agent_tasks", ["org_id"])
    op.create_index("ix_agent_tasks_project_id", "agent_tasks", ["project_id"])
    op.create_index("ix_agent_tasks_workflow_id", "agent_tasks", ["workflow_id"])
    op.create_index("ix_agent_tasks_parent_id", "agent_tasks", ["parent_id"])
    op.create_index("ix_agent_tasks_trace_id", "agent_tasks", ["trace_id"])
    op.create_index("ix_agent_tasks_idempotency_key", "agent_tasks", ["idempotency_key"])
    op.create_index("ix_agent_tasks_celery_task_id", "agent_tasks", ["celery_task_id"])
    op.create_index("ix_agent_tasks_queued_at", "agent_tasks", ["queued_at"])
    op.create_index("ix_agent_tasks_status_priority", "agent_tasks", ["status", "priority"])
    op.create_index("ix_agent_tasks_user_queued", "agent_tasks", ["user_id", "queued_at"])
    op.create_index("ix_agent_tasks_workflow", "agent_tasks", ["workflow_id"])

    # ── 4. audit_chain_entries (PG mirror of audit_chain.py) ─────────────
    if _dialect_is_pg():
        op.execute("""
            CREATE TABLE audit_chain_entries (
                id BIGSERIAL PRIMARY KEY,
                seq BIGINT NOT NULL UNIQUE,
                timestamp VARCHAR(40) NOT NULL,
                occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                method VARCHAR(10) NOT NULL,
                path VARCHAR(500) NOT NULL,
                user VARCHAR(120) DEFAULT '',
                body_hash VARCHAR(80) DEFAULT '',
                status_code BIGINT NOT NULL DEFAULT 0,
                actor VARCHAR(120) DEFAULT '',
                prev_hash VARCHAR(80) NOT NULL,
                entry_hash VARCHAR(80) NOT NULL,
                signature VARCHAR(80) NOT NULL,
                -- P21 P2 P1: was TEXT — p13_c1_p99_db:97-100 creates a GIN
                -- index on this column using ``jsonb_path_ops`` which only
                -- works on JSONB. Switching the column to JSONB so the GIN
                -- index becomes a real, queryable index.
                extra JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
    else:
        # SQLite: 必须 sa.Integer() (而非 BigInteger) 才能触发 ROWID autoincrement
        op.create_table(
            "audit_chain_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("seq", sa.Integer(), nullable=False, unique=True),
            sa.Column("timestamp", sa.String(length=40), nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("method", sa.String(length=10), nullable=False),
            sa.Column("path", sa.String(length=500), nullable=False),
            sa.Column("user", sa.String(length=120), nullable=True, server_default=""),
            sa.Column("body_hash", sa.String(length=80), nullable=True, server_default=""),
            sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("actor", sa.String(length=120), nullable=True, server_default=""),
            sa.Column("prev_hash", sa.String(length=80), nullable=False),
            sa.Column("entry_hash", sa.String(length=80), nullable=False),
            sa.Column("signature", sa.String(length=80), nullable=False),
            # P21 P2 P1: was ``sa.Text()``. Switched to ``sa.JSON()`` so the
            # column type matches the model (``get_jsonb_column()``) and the
            # cross-dialect behaviour is consistent. The GIN index in
            # p13_c1_p99_db:97-100 is PG-only, so SQLite is unaffected.
            sa.Column("extra", sa.JSON(), nullable=True),
        )
    op.create_index("ix_audit_chain_entries_timestamp", "audit_chain_entries", ["timestamp"])
    op.create_index("ix_audit_chain_entries_occurred_at", "audit_chain_entries", ["occurred_at"])
    op.create_index("ix_audit_chain_entries_method", "audit_chain_entries", ["method"])
    op.create_index("ix_audit_chain_entries_user", "audit_chain_entries", ["user"])
    op.create_index("ix_audit_chain_entries_seq", "audit_chain_entries", ["seq"], unique=True)
    op.create_index("ix_audit_chain_entries_method_path", "audit_chain_entries", ["method", "path"])
    op.create_index("ix_audit_chain_entries_user_time", "audit_chain_entries", ["user", "timestamp"])


def downgrade() -> None:
    # 按创建顺序反向 drop
    op.drop_index("ix_audit_chain_entries_user_time", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_method_path", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_seq", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_user", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_method", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_occurred_at", table_name="audit_chain_entries")
    op.drop_index("ix_audit_chain_entries_timestamp", table_name="audit_chain_entries")
    op.drop_table("audit_chain_entries")

    op.drop_index("ix_agent_tasks_workflow", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_user_queued", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_status_priority", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_queued_at", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_celery_task_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_idempotency_key", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_trace_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_parent_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_workflow_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_project_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_org_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_user_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_priority", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_status", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_agent_type", table_name="agent_tasks")
    op.drop_table("agent_tasks")

    op.drop_index("ix_workflows_created_at", table_name="workflows")
    op.drop_index("ix_workflows_project_id", table_name="workflows")
    op.drop_index("ix_workflows_owner", table_name="workflows")
    op.drop_index("ix_workflows_status", table_name="workflows")
    op.drop_table("workflows")

    op.drop_index("ix_embeddings_entity", table_name="embeddings")
    op.drop_index("ix_embeddings_created_at", table_name="embeddings")
    op.drop_index("ix_embeddings_model", table_name="embeddings")
    op.drop_index("ix_embeddings_entity_id", table_name="embeddings")
    op.drop_index("ix_embeddings_entity_type", table_name="embeddings")
    op.drop_table("embeddings")
