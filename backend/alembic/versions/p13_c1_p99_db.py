"""⚠️  DEPRECATED — legacy chain (P21 P2 P5, 2026-07-11) ⚠️

This file lives in the **legacy alembic chain** at ``backend/alembic/``.
Per ``reports/p21_r2_audit_db.md`` §N1, the canonical chain is
``backend/imdf/alembic/``.  This file's GIN index on
``audit_chain_entries.extra`` (line 97-100) is dead code in the legacy
chain because the legacy env.py's MetaData has no
``audit_chain_entries`` table.  The imdf chain now ships an equivalent
GIN index in ``0007_unify_audit_extra_type.py``.

This file is kept in place (not deleted) because some test DBs stamp
its revision into ``alembic_version``.  Use the imdf chain instead.

P13-C1: P99 DB Optimization — HNSW + GIN + extra B-tree + pg_stat_statements.

Goals (per P13-C1 spec, 2026-06-26):
  1. Replace legacy ``ivfflat`` vector indexes with modern ``hnsw`` (faster
     recall, no training step, supports concurrent inserts).
  2. Add GIN indexes on JSONB columns that are commonly searched
     (``agent_tasks.payload``, ``usage_logs.extra``, ``workflows.dag_json``,
     ``audit_chain_entries.extra``) to enable ``@>``, ``?`` and ``@@`` ops.
  3. Add covering B-tree indexes for high-frequency filter columns missing
     from existing index set (``audit_chain_entries.occurred_at`` composite,
     ``embeddings.created_at`` composite).
  4. Enable ``pg_stat_statements`` extension (no-op on SQLite) so future
     deployments can run ``SELECT * FROM pg_stat_statements ORDER BY total_time
     DESC LIMIT 20`` to surface top-20 slow queries.

Revision ID: p13_c1_p99_db
Revises: p4_4_w1_metadata
Create Date: 2026-06-26 17:05:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "p13_c1_p99_db"
down_revision = "p4_4_w1_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    is_postgres = bind.dialect.name == "postgresql"

    # ── 0. pgvector + pg_stat_statements extensions (PG only) ────────────────
    if is_postgres:
        # pgvector 已在 P3-1-W1 装过, 幂等
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # pg_stat_statements 用于 P99 慢查询 top-20 抓取
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")

    # ── 1. HNSW 替换 ivfflat (PG only) ──────────────────────────────────────
    # ivfflat 缺点: 需要预先训练 (build time O(N)), 召回率受 lists 参数影响大,
    #               insert 时需要 rebuild.  HNSW 无训练, 召回更稳.
    if is_postgres:
        # 删旧 ivfflat
        op.execute("DROP INDEX IF EXISTS idx_agents_vector")
        op.execute("DROP INDEX IF EXISTS idx_assets_vector")
        # 加新 hnsw (m=16, ef_construction=64 是 pgvector 推荐默认)
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_memory_hnsw "
            "ON agents USING hnsw (memory_vector vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_embedding_hnsw "
            "ON assets USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        # embeddings 表 (imdf 新栈) 同样加
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_embeddings_vector_hnsw "
            "ON embeddings USING hnsw (vector vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # ── 2. GIN 索引 for JSONB 高频搜索列 ──────────────────────────────────
    # 仅在 PG 上有意义 (SQLite 无 GIN); 用 IF NOT EXISTS 保证幂等
    if is_postgres:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_payload_gin "
            "ON agent_tasks USING GIN (payload jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_result_gin "
            "ON agent_tasks USING GIN (result jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_error_gin "
            "ON agent_tasks USING GIN (error jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_meta_gin "
            "ON agent_tasks USING GIN (meta jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_usage_logs_extra_gin "
            "ON usage_logs USING GIN (extra jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_workflows_dag_gin "
            "ON workflows USING GIN (dag_json jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_audit_chain_extra_gin "
            "ON audit_chain_entries USING GIN (extra jsonb_path_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_embeddings_meta_gin "
            "ON embeddings USING GIN (meta jsonb_path_ops)"
        )

    # ── 3. 复合 B-tree 覆盖索引 (跨方言) ───────────────────────────────────
    # audit_chain_entries: WHERE method = ? AND path = ? ORDER BY seq DESC
    op.create_index(
        "ix_audit_chain_method_path_seq",
        "audit_chain_entries",
        ["method", "path", "seq"],
        unique=False,
    )
    # embeddings: WHERE entity_type = ? AND entity_id = ? ORDER BY created_at DESC
    # (entity_type + entity_id 已有 Index("ix_embeddings_entity"), 此处补 created_at)
    op.create_index(
        "ix_embeddings_entity_created",
        "embeddings",
        ["entity_type", "entity_id", "created_at"],
        unique=False,
    )
    # agent_tasks: WHERE status = 'queued' AND priority <= ? ORDER BY queued_at
    # (status + priority 单列索引已有, 加 queued_at 让范围扫描免排序)
    op.create_index(
        "ix_agent_tasks_status_priority_queued",
        "agent_tasks",
        ["status", "priority", "queued_at"],
        unique=False,
    )
    # workflows: WHERE owner = ? AND status = ? ORDER BY updated_at DESC
    op.create_index(
        "ix_workflows_owner_status_updated",
        "workflows",
        ["owner", "status", "updated_at"],
        unique=False,
    )
    # usage_logs: WHERE provider_id = ? AND kind = ? AND created_at >= ?
    op.create_index(
        "ix_usage_logs_provider_kind_created",
        "usage_logs",
        ["provider_id", "kind", "created_at"],
        unique=False,
    )

    # ── 4. 统计信息刷新 (PG only) ─────────────────────────────────────────
    if is_postgres:
        op.execute("ANALYZE agent_tasks")
        op.execute("ANALYZE embeddings")
        op.execute("ANALYZE usage_logs")
        op.execute("ANALYZE workflows")
        op.execute("ANALYZE audit_chain_entries")


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 复合 B-tree
    op.drop_index("ix_usage_logs_provider_kind_created", table_name="usage_logs")
    op.drop_index("ix_workflows_owner_status_updated", table_name="workflows")
    op.drop_index("ix_agent_tasks_status_priority_queued", table_name="agent_tasks")
    op.drop_index("ix_embeddings_entity_created", table_name="embeddings")
    op.drop_index("ix_audit_chain_method_path_seq", table_name="audit_chain_entries")

    # GIN (PG only)
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_embeddings_meta_gin")
        op.execute("DROP INDEX IF EXISTS ix_audit_chain_extra_gin")
        op.execute("DROP INDEX IF EXISTS ix_workflows_dag_gin")
        op.execute("DROP INDEX IF EXISTS ix_usage_logs_extra_gin")
        op.execute("DROP INDEX IF EXISTS ix_agent_tasks_meta_gin")
        op.execute("DROP INDEX IF EXISTS ix_agent_tasks_error_gin")
        op.execute("DROP INDEX IF EXISTS ix_agent_tasks_result_gin")
        op.execute("DROP INDEX IF EXISTS ix_agent_tasks_payload_gin")

        # HNSW 回退到 ivfflat
        op.execute("DROP INDEX IF EXISTS ix_embeddings_vector_hnsw")
        op.execute("DROP INDEX IF EXISTS idx_assets_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS idx_agents_memory_hnsw")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_vector "
            "ON agents USING ivfflat (memory_vector vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_vector "
            "ON assets USING ivfflat (embedding vector_cosine_ops)"
        )
        # 不卸载 pg_stat_statements (可能被其他库使用)
