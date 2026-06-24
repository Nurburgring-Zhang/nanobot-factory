"""DB package — SQLAlchemy base, engine, session, dependency.

P2-1-W1: SQLite + Alembic 初始实现 (in-memory + JSON 持久化 → SQLite 升级)。
P3-1-W1: 双模式引擎 — 自动探测 URL, PostgreSQL 走 pgvector + JSONB, SQLite 走降级方案。

本包对外只暴露 5 个核心符号:
- ``Base``           declarative_base — 所有 ORM 模型的元基类
- ``engine``         全局 SQLAlchemy Engine (单例, 整个进程复用)
- ``SessionLocal``   sessionmaker 工厂
- ``get_db()``       FastAPI Depends — 每次请求一个 Session
- ``ping()``         健康检查 (SELECT 1)

设计要点 (P3-1-W1):
1. **DB URL 探测** — ``IMDF_P2_DB_URL`` 形如 ``postgresql+psycopg2://...`` 时走 PG,
   ``sqlite:///...`` 时走 SQLite。``db.postgres`` 仅在 PG 模式下被 import。
2. **pgvector** — PG 模式下 import 时自动 ``CREATE EXTENSION IF NOT EXISTS vector``。
3. **跨 DB JSON** — ``db.postgres.get_jsonb_column()`` 返回 PG 上 JSONB, 其他 JSON。
4. **跨 DB Vector** — ``db.postgres.get_vector_column(1024)`` 返回 PG 上 vector(1024), 其他 JSON。
5. **Alembic 兼容** — ``target_metadata = Base.metadata``, alembic/env.py 已用。
6. **回退策略** — ``get_db()`` 失败时记录 warning 但不抛 (避免拖垮登录流)。

用法::

    from db import Base, get_db, engine
    from models import User  # 5 旧模型 + 5 新模型

    @router.get("/users")
    def list_users(db: Session = Depends(get_db)):
        return db.query(User).all()
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# ── DB URL 解析 ─────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _BACKEND_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DEFAULT_DB_FILE = _DATA_DIR / "imdf_p2.db"

_DEFAULT_DB_URL = f"sqlite:///{_DEFAULT_DB_FILE.as_posix()}"

_env_url = os.environ.get("IMDF_P2_DB_URL", "").strip()
IMDF_P2_DB_URL: str = _env_url or _DEFAULT_DB_URL
"""可通过环境变量 ``IMDF_P2_DB_URL`` 覆盖。

支持:
- ``sqlite:///absolute/path.db`` (默认)
- ``sqlite:///:memory:`` (内存, 测试用)
- ``postgresql+psycopg2://user:pass@host:5432/db`` (生产)
- ``postgresql://...`` / ``postgres://...`` (自动规范化成 +psycopg2)
"""


# ── 引擎构造 (按 URL scheme 分派) ─────────────────────────────────────────
def _build_engine(url: str) -> Engine:
    """构造 Engine — 按 URL 自动选 SQLite / PostgreSQL 配置。"""
    # 延后 import: db.postgres 仅在 PG 时才加载 pgvector / psycopg2
    from db.postgres import (
        build_pg_engine_kwargs,
        detect_dialect,
        install_vector_extension,
        is_postgres_url,
        normalize_pg_url,
    )

    if is_postgres_url(url):
        norm_url = normalize_pg_url(url)
        logger.info(f"Building PostgreSQL engine: dialect={detect_dialect(norm_url)}")
        kwargs = build_pg_engine_kwargs(norm_url)
        engine = create_engine(norm_url, **kwargs)
        # 启动时确保 vector extension 存在 (幂等)
        try:
            install_vector_extension(engine)
        except Exception as e:  # pragma: no cover
            logger.warning(f"install_vector_extension 调用失败 (非阻塞): {e}")
        return engine

    # SQLite 默认
    logger.info(f"Building SQLite engine: url={url}")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine: Engine = _build_engine(IMDF_P2_DB_URL)
"""全局 SQLAlchemy Engine — 单例, 跨请求复用。

启动时按 ``IMDF_P2_DB_URL`` 自动选方言:
- ``postgresql+psycopg2://...``  →  PG + pgvector + JSONB
- ``sqlite:///...``              →  SQLite + JSON 降级
"""


# ── SessionLocal ────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)
"""Session 工厂。``expire_on_commit=False`` 避免 commit 后属性访问触发 lazy load。"""


# ── Base ────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """所有 ORM 模型的元基类 (DeclarativeBase v2 风格)。"""

    pass


# ── FastAPI Depends ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖: 每个请求一个 Session, try/finally 关闭。"""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception as e:
        try:
            db.rollback()
        except Exception:  # pragma: no cover
            pass
        logger.warning(f"get_db() 中途异常, 已 rollback: {e}")
        raise
    finally:
        try:
            db.close()
        except Exception:  # pragma: no cover
            pass


def ping() -> bool:
    """快速健康检查 — ``SELECT 1`` 走一遍。"""
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        return result == 1
    except Exception as e:  # pragma: no cover
        logger.error(f"DB ping failed: {e}")
        return False


# ── 启动时自动建表 (开发友好, 生产用 alembic upgrade head) ───────────────
def init_db() -> None:
    """基于 ``Base.metadata`` 在 ``engine`` 上 ``create_all``。

    警告: 仅供开发 / 测试 / smoke 验证使用。生产必须用 ``alembic upgrade head``。
    """
    from models import register_all  # type: ignore  # noqa: F401

    register_all()
    Base.metadata.create_all(bind=engine)
    logger.info(f"init_db() 完成, URL={IMDF_P2_DB_URL}, tables={list(Base.metadata.tables.keys())}")


# ── DB 元信息查询 ─────────────────────────────────────────────────────────
def db_dialect() -> str:
    """当前 engine 的方言名 — ``postgresql`` / ``sqlite`` / 其他。"""
    return engine.dialect.name


def db_has_vector_extension() -> bool:
    """检查 PG 上是否安装了 vector extension (仅 PG 方言有意义)。"""
    if engine.dialect.name != "postgresql":
        return False
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).first()
        return row is not None
    except Exception as e:  # pragma: no cover
        logger.error(f"db_has_vector_extension failed: {e}")
        return False


__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "ping",
    "init_db",
    "IMDF_P2_DB_URL",
    "db_dialect",
    "db_has_vector_extension",
]
