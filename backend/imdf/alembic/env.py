"""Alembic env — 配置 target_metadata + sqlalchemy.url。

P2-1-W1:
- 把 ``backend/imdf`` 加到 sys.path (这样 ``from db import Base`` / ``from models import ...`` 都能 import)
- 动态从 ``IMDF_P2_DB_URL`` 环境变量读 URL (默认是 ``data/imdf_p2.db``)
- ``target_metadata = db.Base.metadata``, 这样 ``alembic revision --autogenerate`` 能感知到 5 个表
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# ── 把 backend/imdf 加到 sys.path ─────────────────────────────────────────
_BACKEND_IMDF = Path(__file__).resolve().parent.parent
if str(_BACKEND_IMDF) not in sys.path:
    sys.path.insert(0, str(_BACKEND_IMDF))

# 现在可以 import db 和 models
from db import Base, IMDF_P2_DB_URL  # noqa: E402
from models import register_all  # noqa: E402,E501  (import 副作用: 注册 5 个 model 到 Base.metadata)

# ── Alembic Config ────────────────────────────────────────────────────────
config = context.config

# 让 alembic 用我们 runtime 算出来的 URL (而不是 ini 里的占位)
config.set_main_option("sqlalchemy.url", IMDF_P2_DB_URL)

# 加载 ini 的 logging 配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── target_metadata ──────────────────────────────────────────────────────
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL 不连 DB)。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER 兼容
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (连 DB 真跑)。"""
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER 兼容
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
