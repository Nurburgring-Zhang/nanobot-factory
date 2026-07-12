"""PostgreSQL + pgvector specific DB utilities — P3-1-W1.

本模块**仅在** ``IMDF_P2_DB_URL`` 指向 PostgreSQL 时被 import, 提供:
- ``install_vector_extension()`` — 跑 ``CREATE EXTENSION IF NOT EXISTS vector``
- ``get_vector_column(dimensions)`` — 跨方言 Vector 类型 (PG → pgvector, SQLite → JSON fallback)
- ``is_postgres_url(url)`` — 简单 URL scheme 探测
- ``normalize_pg_url(url)`` — 把 ``postgres://`` 规范成 ``postgresql+psycopg2://``

设计:
- 跨 DB 兼容: SQLite 没 vector 类型, Embedding 表用 JSON 字段降级存数组。
- 部署态: ``IMDF_P2_DB_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/imdf``
  → 启动时 ``install_vector_extension()`` 调一次。
- 测试态: 默认 ``sqlite:///data/imdf_p2.db`` → 该模块不被 import。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ── URL 探测 / 规范化 ─────────────────────────────────────────────────────
def is_postgres_url(url: str) -> bool:
    """URL scheme 是 ``postgres`` / ``postgresql`` 系列 → True。"""
    if not url:
        return False
    s = url.strip().lower()
    return s.startswith("postgres://") or s.startswith("postgresql://") or s.startswith("postgresql+")


def normalize_pg_url(url: str) -> str:
    """把 ``postgres://`` / ``postgresql://`` 规范成 ``postgresql+psycopg2://``。

    - ``postgres://``          → ``postgresql+psycopg2://``
    - ``postgresql://``        → ``postgresql+psycopg2://``
    - ``postgresql+psycopg2://`` → 原样返回
    - ``postgresql+asyncpg://`` → 原样返回 (async, 留给未来)
    """
    if not url:
        return url
    s = url.strip()
    sl = s.lower()
    if sl.startswith("postgres://"):
        return "postgresql+psycopg2://" + s[len("postgres://"):]
    if sl.startswith("postgresql://"):
        return "postgresql+psycopg2://" + s[len("postgresql://"):]
    return s


# ── pgvector Vector 列类型 ─────────────────────────────────────────────────
def get_vector_column(dimensions: int = 1024):
    """返回一个跨方言 ORM 列类型 — PG 用 ``pgvector.sqlalchemy.Vector``, 其他用 ``JSON`` 降级。

    用法::

        from sqlalchemy.orm import mapped_column
        from db.postgres import get_vector_column

        class Embedding(Base):
            vector: Mapped[Any] = mapped_column(get_vector_column(1024))

    设计取舍:
    - pgvector Vector 列在 PG 上是 ``vector(1024)`` 强类型, 写入时必须是
      ``list[float]`` 长度 = 1024, 否则抛 ``DataError``。
    - SQLite 降级: 用 ``JSON`` 存 ``[0.1, 0.2, ...]``, 失去 cosine 距离索引。
      对开发 / 单测够用; 生产必须用 PG。
    - 关键: 必须用 ``with_variant`` — 同一个 Type 对象在不同方言上自动切换。
      **不能**直接返回 ``Vector(dim=...)`` 类, 因为在 SQLite 上 SA 不知道如何渲染它
      (会抛 ``Compiler can't render element of type VECTOR``)。
    """
    from sqlalchemy import JSON
    try:
        from pgvector.sqlalchemy import Vector  # type: ignore
        # Vector 是 PG-only 类 → 用 with_variant 让 SA 在非 PG 方言上回退到 JSON
        return JSON().with_variant(Vector(dim=dimensions), "postgresql")
    except Exception as e:  # pragma: no cover - pgvector 未装时
        logger.warning(f"pgvector not available, using plain JSON column: {e}")
        return JSON


# ── pgvector 扩展安装 ────────────────────────────────────────────────────
def install_vector_extension(engine: Engine) -> bool:
    """在 PostgreSQL 上跑 ``CREATE EXTENSION IF NOT EXISTS vector``。

    必须在 alembic upgrade head 之前 / 同步执行, 否则 vector 列 DDL 会失败。
    本函数幂等 — extension 已存在时 no-op。
    """
    if not is_postgres_url(str(engine.url)):
        logger.debug("Not a PostgreSQL engine, skipping CREATE EXTENSION vector")
        return False
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            # 注意: extension 必须 superuser 才能 CREATE。
            # 普通用户在初始化时会失败, 此时需手动在 PG 内预先建好。
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("PostgreSQL extension 'vector' installed (or already exists)")
        return True
    except Exception as e:
        logger.error(f"Failed to CREATE EXTENSION vector: {e}")
        logger.error(
            "  → 解决方法: 在 PG 内手动跑 'CREATE EXTENSION vector;' (需 superuser)\n"
            "  → 或用 docker: 'docker run --name pgvector -e POSTGRES_PASSWORD=postgres "
            "-p 5432:5432 -d pgvector/pgvector:pg16'"
        )
        return False


# ── PG 引擎配置 ──────────────────────────────────────────────────────────
def build_pg_engine_kwargs(url: str) -> dict:
    """给 create_engine 用 — PG 专用 pool 参数。

    P13-C1 调优 (2026-06-26):
      - ``pool_recycle`` 从硬编码 1800 改为 env 可调 (IMDF_PG_POOL_RECYCLE)
      - 新增 ``server_settings.statement_timeout`` (默认 30s, 防慢 SQL 拖死池)
      - 新增 ``server_settings.idle_in_transaction_session_timeout`` (60s)
      - 新增 ``pool_timeout`` (默认 30s, 排队拿连接的超时)
    """
    return {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("IMDF_PG_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("IMDF_PG_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.environ.get("IMDF_PG_POOL_RECYCLE", "1800")),
        "pool_timeout": int(os.environ.get("IMDF_PG_POOL_TIMEOUT", "30")),
        "connect_args": {
            "connect_timeout": int(os.environ.get("IMDF_PG_CONNECT_TIMEOUT", "10")),
            "application_name": "imdf-backend",
            "options": (
                f"-c statement_timeout={os.environ.get('IMDF_PG_STATEMENT_TIMEOUT_MS', '30000')}"
                f" -c idle_in_transaction_session_timeout={os.environ.get('IMDF_PG_IDLE_IN_TXN_TIMEOUT_MS', '60000')}"
            ),
        },
    }


# ── 辅助: 把 JSON 字段在 PG 上明确映射到 JSONB ────────────────────────────
def get_jsonb_column():
    """跨方言 JSON 字段 — PG 用 ``JSONB`` (binary JSON, 索引 + GIN 友好), 其他用 ``JSON``。

    用法::

        from sqlalchemy.orm import mapped_column
        from db.postgres import get_jsonb_column

        meta: Mapped[dict] = mapped_column(get_jsonb_column(), default=dict)

    关键实现: 用 ``with_variant`` 让同一个类型对象在 PG 上渲染为 ``JSONB``,
    在 SQLite / MySQL 等降级为 ``JSON``。直接返回 ``JSONB`` 类会导致 SQLite 上
    ``Compiler can't render element of type JSONB`` 错误。
    """
    from sqlalchemy import JSON
    try:
        from sqlalchemy.dialects.postgresql import JSONB
        return JSON().with_variant(JSONB(), "postgresql")
    except Exception:  # pragma: no cover
        return JSON


# ── 测试用 helper ───────────────────────────────────────────────────────
def detect_dialect(url: str) -> str:
    """``postgresql+psycopg2`` → ``postgresql``; ``sqlite:///`` → ``sqlite``。"""
    if not url:
        return "unknown"
    s = url.strip().lower()
    if s.startswith("postgresql"):
        return "postgresql"
    if s.startswith("postgres"):
        return "postgresql"
    if s.startswith("sqlite"):
        return "sqlite"
    return "unknown"


# ── P13-C1: pg_stat_statements top-20 慢查询抓取 ────────────────────────
TOP_QUERIES_SQL = """
SELECT
    queryid,
    -- 截断到 200 字符, 避免长 query 撑爆返回
    LEFT(query, 200) AS query,
    calls,
    ROUND((total_exec_time)::numeric, 2)  AS total_time_ms,
    ROUND((mean_exec_time)::numeric, 2)   AS mean_time_ms,
    ROUND((max_exec_time)::numeric, 2)    AS max_time_ms,
    ROUND((stddev_exec_time)::numeric, 2) AS stddev_time_ms,
    ROUND((total_exec_time / NULLIF(SUM(total_exec_time) OVER (), 0) * 100)::numeric, 2)
        AS pct_of_total,
    shared_blks_hit,
    shared_blks_read,
    rows
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat_statements%'   -- 排除自身
  AND query NOT ILIKE '%explain%'             -- 排除 EXPLAIN 类
ORDER BY total_exec_time DESC
LIMIT :limit
"""


def get_top_slow_queries(engine: Engine, limit: int = 20) -> list:
    """P13-C1: 返回 pg_stat_statements top-N 慢查询。

    Args:
        engine: SQLAlchemy Engine (必须是 PG 引擎, 否则返回空列表)
        limit: 返回条数, 默认 20

    Returns:
        list[dict]: 每条 {queryid, query, calls, total_time_ms, mean_time_ms,
                          max_time_ms, stddev_time_ms, pct_of_total, ...}

    在 SQLite 上返回空列表 + warning log (开发环境无 pg_stat_statements)。
    """
    if not is_postgres_url(str(engine.url)):
        logger.warning(
            "get_top_slow_queries: 非 PG 引擎 (%s), 返回空列表",
            engine.url,
        )
        return []

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(TOP_QUERIES_SQL), {"limit": limit}).fetchall()
            return [dict(r._mapping) for r in rows]
    except Exception as exc:  # pragma: no cover - 需要 PG + extension
        logger.warning("get_top_slow_queries failed (extension 未装?): %s", exc)
        return []


# ── P13-C1: 缺失索引建议 (基于 pg_stat_user_tables) ─────────────────────
MISSING_INDEX_SQL = """
SELECT
    schemaname || '.' || relname        AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup                          AS row_estimate,
    CASE
        WHEN idx_scan IS NULL OR idx_scan = 0 THEN 'CRITICAL — 全表扫描, 0 索引命中'
        WHEN seq_scan > idx_scan        THEN 'WARN — seq 扫描 > idx 扫描'
        ELSE 'OK'
    END                                 AS verdict
FROM pg_stat_user_tables
WHERE n_live_tup > 1000
ORDER BY seq_scan DESC
LIMIT 20
"""


def get_missing_index_hints(engine: Engine) -> list:
    """P13-C1: 返回全表扫描多、索引命中少的表 (添加索引的优先级排序)。

    PG only; SQLite / 其他返回空列表。
    """
    if not is_postgres_url(str(engine.url)):
        return []

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(MISSING_INDEX_SQL)).fetchall()
            return [dict(r._mapping) for r in rows]
    except Exception as exc:  # pragma: no cover
        logger.warning("get_missing_index_hints failed: %s", exc)
        return []


# ── P13-C1: 池利用率实时监控 (通过 pg_stat_activity) ────────────────────
POOL_USAGE_SQL = """
SELECT
    state,
    COUNT(*) AS n,
    ROUND(AVG(EXTRACT(EPOCH FROM (now() - state_change)) * 1000)::numeric, 1) AS avg_age_ms
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state
ORDER BY n DESC
"""


def get_pool_usage(engine: Engine) -> list:
    """P13-C1: 返回 PG 端 connection 状态分布 (idle / active / idle in txn)。

    用法: 通过 ``active / total`` 估算池利用率, 触发 pool 调优.
    PG only; 其他返回空列表。
    """
    if not is_postgres_url(str(engine.url)):
        return []

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(POOL_USAGE_SQL)).fetchall()
            return [dict(r._mapping) for r in rows]
    except Exception as exc:  # pragma: no cover
        logger.warning("get_pool_usage failed: %s", exc)
        return []


__all__ = [
    "is_postgres_url",
    "normalize_pg_url",
    "get_vector_column",
    "install_vector_extension",
    "build_pg_engine_kwargs",
    "get_jsonb_column",
    "detect_dialect",
    "get_top_slow_queries",
    "get_missing_index_hints",
    "get_pool_usage",
]
