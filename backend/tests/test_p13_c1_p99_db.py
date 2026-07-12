"""P13-C1: P99 DB Optimization — 连接池 + 慢查询分析回归测试.

测什么:
  1. build_pg_engine_kwargs 默认值正确
  2. env 覆盖 pool_size / max_overflow / pool_recycle / statement_timeout
  3. SQLite fallback 路径不挂 (无 PG 也能 import)
  4. get_top_slow_queries / get_missing_index_hints / get_pool_usage 在 SQLite
     上返回空列表 (不抛错)
  5. detect_dialect 边界 (大小写、空串、未知 scheme)
  6. is_postgres_url 兼容 postgresql:// / postgres:// / postgresql+psycopg2://

不在这里测:
  - 真 PG 端 pg_stat_statements 数据 (需要 live PG, 见 reports/p13_c1_p99_db.md)
  - alembic 迁移 (需要 PG, 见 reports/p13_c1_p99_db.md §3.3)
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── 路径注入 (跟 conftest 一致, 允许单文件跑) ──────────────────────────
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent  # backend/
_IMDF = _BACKEND / "imdf"
# backend/ 必须在 imdf/* 之前 (跟 conftest 一致)
if str(_BACKEND) in sys.path:
    sys.path.remove(str(_BACKEND))
sys.path.insert(0, str(_BACKEND))
# imdf/api/, imdf/engines/, imdf/common/ 单独加入 (供 P1 测试用)
for sub in ("common", "engines", "api"):  # reverse order, api on top
    p = str(_IMDF / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
# imdf/ 顶层不加入 sys.path (会 shadow backend/core). 用 importlib 直接加载
# imdf/db/postgres.py 即可 (它本身没有 import 链依赖于 imdf.db.__init__,
# 只需要 sqlalchemy + pgvector 可选).


def _load_postgres_module():
    """用 importlib 直接加载 ``imdf/db/postgres.py``, 绕过 imdf.db.__init__.

    为什么: ``imdf/db/__init__.py`` 用 ``from db.postgres import`` 这种
    非标准 self-referential 写法, 只能在 imdf/ 是 cwd 或在 sys.path 时工作.
    conftest.py 为了避免 imdf/ shadow backend/core, 故意把 imdf/ 移出 sys.path,
    导致 ``from imdf.db.postgres import X`` 在测试里走不通.
    直接用 importlib.util 加载 .py 文件, 跳过 __init__ 的副作用.
    """
    fpath = str(_IMDF / "db" / "postgres.py")
    spec = importlib.util.spec_from_file_location("_p13c1_db_postgres", fpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PG = _load_postgres_module()


# ── 1. build_pg_engine_kwargs 默认值 ───────────────────────────────────
class TestBuildPgEngineKwargs:
    def test_default_pool_size_10(self, monkeypatch):
        # 清除所有 IMDF_PG_* env, 验证默认
        for k in list(os.environ):
            if k.startswith("IMDF_PG_"):
                monkeypatch.delenv(k, raising=False)
        kw = _PG.build_pg_engine_kwargs("postgresql://u:p@h:5432/d")
        assert kw["pool_size"] == 10
        assert kw["max_overflow"] == 20
        assert kw["pool_recycle"] == 1800
        assert kw["pool_pre_ping"] is True
        assert kw["pool_timeout"] == 30  # P13-C1 新增

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("IMDF_PG_POOL_SIZE", "25")
        monkeypatch.setenv("IMDF_PG_MAX_OVERFLOW", "50")
        monkeypatch.setenv("IMDF_PG_POOL_RECYCLE", "600")
        monkeypatch.setenv("IMDF_PG_POOL_TIMEOUT", "5")
        monkeypatch.setenv("IMDF_PG_STATEMENT_TIMEOUT_MS", "5000")
        monkeypatch.setenv("IMDF_PG_IDLE_IN_TXN_TIMEOUT_MS", "30000")
        kw = _PG.build_pg_engine_kwargs("postgresql://u:p@h:5432/d")
        assert kw["pool_size"] == 25
        assert kw["max_overflow"] == 50
        assert kw["pool_recycle"] == 600
        assert kw["pool_timeout"] == 5
        opts = kw["connect_args"]["options"]
        assert "statement_timeout=5000" in opts
        assert "idle_in_transaction_session_timeout=30000" in opts

    def test_postgres_scheme_normalized(self):
        assert _PG.normalize_pg_url("postgres://u:p@h/d").startswith("postgresql+psycopg2://")
        assert _PG.normalize_pg_url("postgresql://u:p@h/d").startswith("postgresql+psycopg2://")
        assert _PG.normalize_pg_url("postgresql+psycopg2://u:p@h/d") == "postgresql+psycopg2://u:p@h/d"
        assert _PG.normalize_pg_url("sqlite:///foo.db") == "sqlite:///foo.db"

    def test_statement_timeout_in_connect_args(self, monkeypatch):
        for k in list(os.environ):
            if k.startswith("IMDF_PG_"):
                monkeypatch.delenv(k, raising=False)
        kw = _PG.build_pg_engine_kwargs("postgresql://u:p@h/d")
        opts = kw["connect_args"]["options"]
        assert "statement_timeout=30000" in opts
        assert "idle_in_transaction_session_timeout=60000" in opts


# ── 2. SQLite / 非 PG 路径上 helper 优雅降级 ──────────────────────────
class TestSqliteFallback:
    def test_top_slow_queries_returns_empty_on_sqlite(self):
        fake_eng = MagicMock()
        fake_eng.url = "sqlite:///foo.db"
        assert _PG.get_top_slow_queries(fake_eng) == []

    def test_missing_index_hints_returns_empty_on_sqlite(self):
        fake_eng = MagicMock()
        fake_eng.url = "sqlite:///foo.db"
        assert _PG.get_missing_index_hints(fake_eng) == []

    def test_pool_usage_returns_empty_on_sqlite(self):
        fake_eng = MagicMock()
        fake_eng.url = "sqlite:///foo.db"
        assert _PG.get_pool_usage(fake_eng) == []

    def test_top_slow_queries_handles_missing_extension(self):
        """PG URL 但 pg_stat_statements 未装时, 应捕获异常返回空 (不挂)."""
        fake_eng = MagicMock()
        fake_eng.url = "postgresql://u:p@h:5432/d"
        fake_conn = MagicMock()
        fake_conn.__enter__ = MagicMock(return_value=fake_conn)
        fake_conn.__exit__ = MagicMock(return_value=False)
        fake_conn.execute.side_effect = Exception("extension not installed")
        fake_eng.connect.return_value = fake_conn

        assert _PG.get_top_slow_queries(fake_eng) == []


# ── 3. detect_dialect / is_postgres_url 边界 ──────────────────────────
class TestUrlHelpers:
    @pytest.mark.parametrize("url,expected", [
        ("postgresql://u@h/d", "postgresql"),
        ("postgresql+psycopg2://u@h/d", "postgresql"),
        ("postgresql+asyncpg://u@h/d", "postgresql"),
        ("postgres://u@h/d", "postgresql"),
        ("POSTGRES://U@H/D", "postgresql"),  # 大小写
        ("sqlite:///foo.db", "sqlite"),
        ("sqlite:////abs/path.db", "sqlite"),
        ("mysql://u@h/d", "unknown"),
        ("", "unknown"),
    ])
    def test_detect_dialect(self, url, expected):
        assert _PG.detect_dialect(url) == expected

    @pytest.mark.parametrize("url,expected", [
        ("postgres://u@h/d", True),
        ("postgresql://u@h/d", True),
        ("postgresql+psycopg2://u@h/d", True),
        ("sqlite:///foo.db", False),
        ("mysql://u@h/d", False),
        ("", False),
    ])
    def test_is_postgres_url(self, url, expected):
        assert _PG.is_postgres_url(url) is expected


# ── 4. infrastructure/database.py 池配置 (mock, 不连真 PG) ─────────────
class TestPostgresManagerPool:
    def test_pool_size_default_from_env(self, monkeypatch):
        monkeypatch.setenv("IMDF_PG_POOL_SIZE", "7")
        for k in ("IMDF_PG_MAX_OVERFLOW", "IMDF_PG_POOL_RECYCLE",
                  "IMDF_PG_POOL_MIN", "IMDF_PG_STATEMENT_TIMEOUT_MS"):
            monkeypatch.delenv(k, raising=False)

        # 跳过 POSTGRES_AVAILABLE 检查
        import infrastructure.database as db_mod
        monkeypatch.setattr(db_mod, "POSTGRES_AVAILABLE", True)

        mgr = db_mod.PostgresManager(dsn="postgresql://x@y/z")
        assert mgr.pool_size == 7
        assert mgr.max_overflow == 20  # default
        assert mgr.pool_recycle == 1800  # default
        assert mgr.statement_timeout_ms == 30000  # default

    def test_all_overrides(self, monkeypatch):
        monkeypatch.setenv("IMDF_PG_POOL_SIZE", "15")
        monkeypatch.setenv("IMDF_PG_MAX_OVERFLOW", "30")
        monkeypatch.setenv("IMDF_PG_POOL_RECYCLE", "900")
        monkeypatch.setenv("IMDF_PG_STATEMENT_TIMEOUT_MS", "15000")
        import infrastructure.database as db_mod
        monkeypatch.setattr(db_mod, "POSTGRES_AVAILABLE", True)
        mgr = db_mod.PostgresManager(dsn="postgresql://x@y/z")
        assert mgr.pool_size == 15
        assert mgr.max_overflow == 30
        assert mgr.pool_recycle == 900
        assert mgr.statement_timeout_ms == 15000

    def test_explicit_kwargs_override_env(self, monkeypatch):
        monkeypatch.setenv("IMDF_PG_POOL_SIZE", "7")
        import infrastructure.database as db_mod
        monkeypatch.setattr(db_mod, "POSTGRES_AVAILABLE", True)
        mgr = db_mod.PostgresManager(
            dsn="postgresql://x@y/z",
            pool_size=99,
            max_overflow=88,
        )
        assert mgr.pool_size == 99  # 显式覆盖 env
        assert mgr.max_overflow == 88


# ── 5. list_tasks OFFSET typo 修复 (集成测试) ─────────────────────────
class TestListTasksOffsetFix:
    """P13-C1 修复: list_tasks 原写 OFFSET 2 (字面), 现在 OFFSET $2.

    这个测试用 mock engine 验证 SQL 字符串含 OFFSET $2 而不是 OFFSET 2.
    """

    def test_offset_uses_parameter(self, monkeypatch):
        import infrastructure.database as db_mod
        monkeypatch.setattr(db_mod, "POSTGRES_AVAILABLE", True)

        mgr = db_mod.PostgresManager(dsn="postgresql://x@y/z")

        # 抓出 list_tasks 实际拼出来的 query 字符串
        with patch.object(mgr, "execute") as mock_exec:
            import asyncio
            asyncio.run(mgr.list_tasks(agent_id="a1", limit=5, offset=10))
            # 拿 mock 收到的 query
            assert mock_exec.called
            call_args = mock_exec.call_args
            sent_query = call_args[0][0]  # 第一个位置参数
            assert "OFFSET $2" in sent_query, f"OFFSET $2 missing in: {sent_query}"
            assert "OFFSET 2 " not in sent_query and not sent_query.rstrip().endswith("OFFSET 2"), (
                f"字面 OFFSET 2 不应出现: {sent_query}"
            )
