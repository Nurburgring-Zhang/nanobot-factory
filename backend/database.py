#!/usr/bin/env python3
"""
Nanobot Factory - Database Management (Optimized)
High-performance multimedia database for AI training data

@author MiniMax Agent
@date 2026-02-25
@description 优化版本：修复SQL注入、添加连接池、优化N+1查询
              PostgreSQL + SQLite 双引擎支持 (2026-06-12)
"""

import os
import sqlite3
import json
import logging
import hashlib
import threading
import queue
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# =============================================================================
# Database Engine Configuration - from environment variables
# =============================================================================

class DatabaseEngineConfig:
    """
    Database engine configuration read from environment variables.
    
    - Set DATABASE_URL to a postgresql:// URL to enable PostgreSQL (asyncpg)
    - Leave DATABASE_URL unset / not postgresql:// to use SQLite (default)
    - SQLITE_PATH controls the SQLite database file path
    - DB_POOL_SIZE controls connection pool size
    """
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    USE_POSTGRES = DATABASE_URL.startswith("postgresql://") if DATABASE_URL else False
    SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "data", "nanobot.db"))
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

    # PostgreSQL-specific settings
    PG_MIN_CONNECTIONS = int(os.getenv("PG_MIN_CONNECTIONS", "1"))
    PG_MAX_CONNECTIONS = int(os.getenv("PG_MAX_CONNECTIONS", "10"))


# Lazy imports for PostgreSQL (only when needed)
_asyncpg_available = False
_sqlalchemy_available = False

try:
    import asyncpg  # noqa: F401
    _asyncpg_available = True
except ImportError:
    pass

try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine  # noqa: F401
    _sqlalchemy_available = True
except ImportError:
    pass


@dataclass
class Asset:
    """Represents a multimedia asset - 完整Eagle风格资产管理"""
    id: str
    name: str
    type: str  # image, video, 3d, text, audio, document
    path: str
    size: int
    hash: str  # 文件哈希 - 用于重复检测
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    aesthetic_score: float = 0.0
    nsfw_score: float = 0.0
    clip_score: float = 0.0
    # ===== Eagle 核心功能字段 =====
    rating: int = 0              # 0-5星评分
    color: str = ''              # 颜色标签 (#FF0000等)
    palette: List[str] = field(default_factory=list)  # 提取的调色板
    primary_color: str = ''      # 主色调
    annotation: str = ''         # 注释/描述
    folder_id: str = ''         # 所属文件夹ID
    favorite: bool = False       # 收藏标记
    width: int = 0              # 宽度/分辨率
    height: int = 0             # 高度
    duration: int = 0           # 视频/音频时长(秒)
    format: str = ''            # 文件格式
    mime_type: str = ''         # MIME类型
    orientation: int = 1         # 旋转方向
    # 元数据
    source_url: str = ''        # 来源URL
    author: str = ''            # 作者
    copyright: str = ''         # 版权信息
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # 扩展
    thumbnail_path: str = ''     # 缩略图路径
    import_source: str = ''      # 导入来源


@dataclass
class Folder:
    """文件夹 - 支持层级结构和智能文件夹"""
    id: str
    name: str
    path: str = ''              # 文件夹路径
    parent_id: str = ''          # 父文件夹ID (空为根目录)
    is_smart: bool = False      # 是否为智能文件夹
    smart_rules: Dict[str, Any] = field(default_factory=dict)  # 智能文件夹规则
    color: str = ''             # 文件夹颜色
    icon: str = ''              # 文件夹图标
    sort_order: int = 0        # 排序顺序
    is_system: bool = False     # 系统文件夹
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Tag:
    """标签 - 支持标签组和层级"""
    id: str
    name: str
    group_id: str = ''           # 标签组ID
    parent_id: str = ''         # 父标签ID (支持层级标签)
    color: str = ''             # 标签颜色
    count: int = 0              # 使用次数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TagGroup:
    """标签组"""
    id: str
    name: str
    color: str = ''             # 组颜色
    sort_order: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class DatabaseConfig:
    """Database configuration"""
    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._local = threading.local()


class ConnectionPool:
    """Thread-safe connection pool for SQLite"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: queue.Queue = queue.Queue(maxsize=config.pool_size)
        self._init_pool()

    def _init_pool(self):
        """Initialize connection pool"""
        for _ in range(self.config.pool_size):
            conn = self._create_connection()
            self.pool.put(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection"""
        conn = sqlite3.connect(
            self.config.db_path,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=10000')
        conn.execute('PRAGMA temp_store=MEMORY')
        return conn

    @contextmanager
    def get_connection(self):
        """Get connection from pool (context manager)"""
        conn = None
        try:
            conn = self.pool.get(timeout=5.0)
            yield conn
        except queue.Empty:
            # Pool exhausted, create temporary connection
            conn = self._create_connection()
            yield conn
            conn.close()
        finally:
            if conn and self.pool.qsize() < self.config.pool_size:
                self.pool.put(conn)

    def close_all(self):
        """Close all connections in pool"""
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except queue.Empty:
                break


class PostgresConnectionPool:
    """
    Connection pool wrapper for PostgreSQL using asyncpg.
    
    Provides the same contextmanager interface as ConnectionPool
    so that DatabaseManager can use it transparently.
    Note: This wraps synchronous-style access; actual asyncpg pools
    are used under the hood via run_sync for compatibility.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None
        self._dsn = DatabaseEngineConfig.DATABASE_URL

    async def _get_or_create_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=DatabaseEngineConfig.PG_MIN_CONNECTIONS,
                max_size=DatabaseEngineConfig.PG_MAX_CONNECTIONS,
            )
        return self._pool

    @contextmanager
    def get_connection(self):
        """
        Synchronous context manager that acquires an asyncpg connection
        and adapts it to the sqlite3.Row-like interface expected by DatabaseManager.
        
        This is a compatibility shim -- it uses a synchronous wrapper around
        the async pool. For full async usage, refactor DatabaseManager to be async.
        """
        import asyncio
        import asyncpg

        conn_wrapper = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            pool = loop.run_until_complete(self._get_or_create_pool())
            pg_conn = loop.run_until_complete(pool.acquire())
            conn_wrapper = _PostgresConnectionWrapper(pg_conn, pool, loop)
            yield conn_wrapper
        except Exception as e:
            logger.error(f"PostgreSQL connection error: {e}")
            raise
        finally:
            if conn_wrapper is not None:
                try:
                    conn_wrapper._release()
                except Exception:
                    pass

    def close_all(self):
        """Close the PostgreSQL connection pool"""
        if self._pool is not None:
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._pool.close())
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL pool: {e}")
            self._pool = None
            logger.info("PostgreSQL connection pool closed")


class _PostgresConnectionWrapper:
    """
    Wraps an asyncpg connection to provide a sqlite3.Row-like interface
    and cursor() / execute() / fetchone() / fetchall() / commit() / rollback() methods.
    """

    def __init__(self, pg_conn, pool, loop):
        self._conn = pg_conn
        self._pool = pool
        self._loop = loop

    def cursor(self):
        return _PostgresCursorWrapper(self._conn, self._loop)

    def execute(self, query, params=None):
        """Execute a query. params can be a list or tuple."""
        cursor = self.cursor()
        return cursor.execute(query, params)

    def executescript(self, script):
        """Execute multiple SQL statements separated by semicolons."""
        cursor = self.cursor()
        statements = [s.strip() for s in script.split(';') if s.strip()]
        for stmt in statements:
            cursor.execute(stmt)
        return self

    def commit(self):
        """PostgreSQL is auto-commit by default; this is a no-op for compatibility."""
        pass

    def rollback(self):
        """Rollback is a no-op by default."""
        pass

    def close(self):
        self._release()

    def _release(self):
        """Release the connection back to the pool."""
        if self._conn is not None:
            try:
                self._loop.run_until_complete(self._pool.release(self._conn))
            except Exception:
                pass
            self._conn = None


class _PostgresCursorWrapper:
    """Mimics sqlite3.Cursor but backed by asyncpg."""

    def __init__(self, pg_conn, loop):
        self._conn = pg_conn
        self._loop = loop
        self._rows = []
        self._row_index = 0
        self._description = None
        self._rowcount = -1

    def execute(self, query, params=None):
        import asyncpg

        # Convert params: if it's a list/tuple, use as positional args
        if params is not None and not isinstance(params, (list, tuple)):
            params = (params,)

        try:
            result = self._loop.run_until_complete(
                self._conn.fetch(query, *params) if params else self._conn.fetch(query)
            )
            # Convert asyncpg Records to dict-like objects
            self._rows = [dict(r) for r in result]
            self._row_index = 0
            self._rowcount = len(self._rows) if result else 0
        except asyncpg.exceptions.UniqueViolationError:
            # For INSERT OR REPLACE / INSERT OR IGNORE compatibility:
            # PostgreSQL uses ON CONFLICT, so we fall back to that
            fallback_query = self._translate_on_conflict(query)
            if fallback_query != query:
                # Retry with translated query
                result = self._loop.run_until_complete(
                    self._conn.fetch(fallback_query, *params) if params else self._conn.fetch(fallback_query)
                )
                self._rows = [dict(r) for r in result] if result else []
                self._row_index = 0
                self._rowcount = len(self._rows) if result else 1
            else:
                raise
        except Exception as e:
            logger.error(f"PostgreSQL cursor execute error: {e}")
            raise
        return self

    def executemany(self, query, seq_of_params):
        for params in seq_of_params:
            self.execute(query, params)
        return self

    def fetchone(self):
        if self._row_index < len(self._rows):
            row = self._rows[self._row_index]
            self._row_index += 1
            return _PostgresRow(row)
        return None

    def fetchall(self):
        results = [_PostgresRow(r) for r in self._rows]
        self._row_index = len(self._rows)
        return results

    @property
    def rowcount(self):
        return self._rowcount

    @staticmethod
    def _translate_on_conflict(query):
        """
        Translate SQLite-specific INSERT OR REPLACE / INSERT OR IGNORE
        to PostgreSQL ON CONFLICT syntax.
        """
        import re
        # INSERT OR REPLACE INTO ... → INSERT INTO ... ON CONFLICT DO UPDATE SET ...
        if re.match(r'INSERT\s+OR\s+REPLACE\s+INTO', query, re.IGNORECASE):
            # Simple fallback: just do INSERT ... ON CONFLICT DO NOTHING
            # Full translation is complex; for now use DO NOTHING for inserts
            stripped = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', query, flags=re.IGNORECASE)
            return stripped + ' ON CONFLICT DO NOTHING'
        # INSERT OR IGNORE INTO ... → INSERT INTO ... ON CONFLICT DO NOTHING
        if re.match(r'INSERT\s+OR\s+IGNORE\s+INTO', query, re.IGNORECASE):
            stripped = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', query, flags=re.IGNORECASE)
            return stripped + ' ON CONFLICT DO NOTHING'
        return query


class _PostgresRow:
    """
    Mimics sqlite3.Row: supports both dict-like key access and integer index access.
    """

    def __init__(self, data: dict):
        self._data = data
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, (int,)):
            return self._data[self._keys[key]]
        return self._data[key]

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"No such column: {name}")

    def keys(self):
        return self._keys

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self):
        return len(self._data)


class DatabaseManager:
    """High-performance multimedia database manager with connection pool"""

    def __init__(self, db_path: str = None, pool_size: int = 5):
        """
        Initialize DatabaseManager with SQLite or PostgreSQL engine.
        
        When DatabaseEngineConfig.USE_POSTGRES is True, db_path is ignored
        and the PostgreSQL connection pool is used instead.
        """
        self.use_postgres = DatabaseEngineConfig.USE_POSTGRES

        # Select engine
        if self.use_postgres:
            # Use PostgreSQL
            pg_path = DatabaseEngineConfig.DATABASE_URL
            self.db_path = pg_path
            self.config = DatabaseConfig(pg_path, pool_size)
            self.pool = PostgresConnectionPool(self.config)
            logger.info(f"Using PostgreSQL engine: {pg_path[:40]}...")
        else:
            # Use SQLite (default) - 零改动现有逻辑
            if db_path is None:
                db_path = DatabaseEngineConfig.SQLITE_PATH
            self.db_path = db_path
            self.config = DatabaseConfig(db_path, pool_size)
            self.pool = ConnectionPool(self.config)

        # 内存缓存 - 用于快速访问
        self.assets: Dict[str, Asset] = {}
        self.datasets: Dict[str, Any] = {}
        self._initialize_database()
        # 从数据库加载现有数据到内存
        self._load_to_memory()

    def _initialize_database(self):
        """Initialize database schema - 完整Eagle风格 (SQLite + PostgreSQL compatible)"""
        if self.use_postgres:
            self._initialize_postgres_schema()
        else:
            self._initialize_sqlite_schema()

    def _initialize_sqlite_schema(self):
        """Initialize SQLite-specific schema (original logic, zero changes)"""
        with self.pool.get_connection() as conn:
            conn.executescript('''
                -- Assets table - 完整Eagle风格字段
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    -- Tags and metadata (stored as JSON)
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    -- AI评分
                    quality_score REAL DEFAULT 0.0,
                    aesthetic_score REAL DEFAULT 0.0,
                    nsfw_score REAL DEFAULT 0.0,
                    clip_score REAL DEFAULT 0.0,
                    -- ===== Eagle 核心功能字段 =====
                    rating INTEGER DEFAULT 0,          -- 0-5星评分
                    color TEXT DEFAULT '',              -- 颜色标签
                    palette TEXT DEFAULT '',          -- 调色板 (JSON数组)
                    primary_color TEXT DEFAULT '',     -- 主色调
                    annotation TEXT DEFAULT '',        -- 注释/描述
                    folder_id TEXT DEFAULT '',         -- 所属文件夹
                    favorite INTEGER DEFAULT 0,        -- 收藏标记
                    width INTEGER DEFAULT 0,          -- 宽度
                    height INTEGER DEFAULT 0,         -- 高度
                    duration INTEGER DEFAULT 0,       -- 视频/音频时长
                    format TEXT DEFAULT '',            -- 格式
                    mime_type TEXT DEFAULT '',         -- MIME类型
                    orientation INTEGER DEFAULT 1,     -- 旋转方向
                    -- 元数据
                    source_url TEXT DEFAULT '',       -- 来源URL
                    author TEXT DEFAULT '',            -- 作者
                    copyright TEXT DEFAULT '',         -- 版权
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    -- 扩展
                    thumbnail_path TEXT DEFAULT '',    -- 缩略图
                    import_source TEXT DEFAULT ''      -- 导入来源
                );

                -- 文件夹表 - 支持层级结构
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id TEXT DEFAULT '',          -- 父文件夹
                    is_smart INTEGER DEFAULT 0,       -- 是否智能文件夹
                    smart_rules TEXT DEFAULT '{}',    -- 智能规则
                    color TEXT DEFAULT '',             -- 文件夹颜色
                    icon TEXT DEFAULT '',              -- 文件夹图标
                    sort_order INTEGER DEFAULT 0,     -- 排序
                    is_system INTEGER DEFAULT 0,      -- 系统文件夹
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- 标签组表
                CREATE TABLE IF NOT EXISTS tag_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    color TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                -- 标签表 - 支持层级
                CREATE TABLE IF NOT EXISTS tags (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    group_id TEXT DEFAULT '',         -- 标签组
                    parent_id TEXT DEFAULT '',        -- 父标签
                    color TEXT DEFAULT '',            -- 标签颜色
                    count INTEGER DEFAULT 0,         -- 使用次数
                    created_at TEXT NOT NULL
                );

                -- Asset-Folder 关系 (多对多)
                CREATE TABLE IF NOT EXISTS asset_folders (
                    asset_id TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    PRIMARY KEY (asset_id, folder_id),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
                );

                -- Asset-Tag 关系 (多对多)
                CREATE TABLE IF NOT EXISTS asset_tags (
                    asset_id TEXT NOT NULL,
                    tag_id TEXT NOT NULL,
                    PRIMARY KEY (asset_id, tag_id),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );

                -- 扩展元数据表
                CREATE TABLE IF NOT EXISTS metadata (
                    asset_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (asset_id, key),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                -- 数据集表
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    asset_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- 智能文件夹表
                CREATE TABLE IF NOT EXISTS smart_folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    sort_by TEXT DEFAULT 'created_at',
                    sort_order TEXT DEFAULT 'desc',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- 数据集资产关联表
                CREATE TABLE IF NOT EXISTS dataset_assets (
                    dataset_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, asset_id),
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                -- FTS5全文搜索索引
                CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
                    id, name, tags, metadata_content,
                    content='assets', content_rowid='rowid'
                );

                -- ===== 创建索引以优化查询 =====
                CREATE INDEX IF NOT EXISTS idx_assets_rating ON assets(rating);
                CREATE INDEX IF NOT EXISTS idx_assets_color ON assets(color);
                CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
                CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(folder_id);
                CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite);
                CREATE INDEX IF NOT EXISTS idx_assets_hash ON assets(hash);  -- 用于重复检测
                CREATE INDEX IF NOT EXISTS idx_assets_created ON assets(created_at);
                CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name);
                CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
                CREATE INDEX IF NOT EXISTS idx_tags_group ON tags(group_id);
            ''')

    def _initialize_postgres_schema(self):
        """Initialize PostgreSQL schema (no FTS5 virtual table, no PRAGMA)"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    quality_score DOUBLE PRECISION DEFAULT 0.0,
                    aesthetic_score DOUBLE PRECISION DEFAULT 0.0,
                    nsfw_score DOUBLE PRECISION DEFAULT 0.0,
                    clip_score DOUBLE PRECISION DEFAULT 0.0,
                    rating INTEGER DEFAULT 0,
                    color TEXT DEFAULT '',
                    palette TEXT DEFAULT '',
                    primary_color TEXT DEFAULT '',
                    annotation TEXT DEFAULT '',
                    folder_id TEXT DEFAULT '',
                    favorite INTEGER DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    duration INTEGER DEFAULT 0,
                    format TEXT DEFAULT '',
                    mime_type TEXT DEFAULT '',
                    orientation INTEGER DEFAULT 1,
                    source_url TEXT DEFAULT '',
                    author TEXT DEFAULT '',
                    copyright TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    thumbnail_path TEXT DEFAULT '',
                    import_source TEXT DEFAULT ''
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id TEXT DEFAULT '',
                    is_smart INTEGER DEFAULT 0,
                    smart_rules TEXT DEFAULT '{}',
                    color TEXT DEFAULT '',
                    icon TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    is_system INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tag_groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    color TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    group_id TEXT DEFAULT '',
                    parent_id TEXT DEFAULT '',
                    color TEXT DEFAULT '',
                    count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS asset_folders (
                    asset_id TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    PRIMARY KEY (asset_id, folder_id),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS asset_tags (
                    asset_id TEXT NOT NULL,
                    tag_id TEXT NOT NULL,
                    PRIMARY KEY (asset_id, tag_id),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    asset_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (asset_id, key),
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    asset_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS smart_folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    sort_by TEXT DEFAULT 'created_at',
                    sort_order TEXT DEFAULT 'desc',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dataset_assets (
                    dataset_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, asset_id),
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
                )
            ''')
            # Create indexes (same as SQLite, no FTS5 for Postgres)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_rating ON assets(rating)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_color ON assets(color)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(folder_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_hash ON assets(hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_created ON assets(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_group ON tags(group_id)')
            logger.info("PostgreSQL schema initialized")

    def _load_to_memory(self):
        """Load assets and datasets from database to memory for fast access"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()

                # Load assets
                cursor.execute("SELECT * FROM assets")
                rows = cursor.fetchall()
                for row in rows:
                    asset = Asset(
                        id=row['id'],
                        name=row['name'],
                        type=row['type'],
                        path=row['path'],
                        size=row['size'],
                        hash=row['hash'],
                        quality_score=row['quality_score'] or 0.0,
                        aesthetic_score=row['aesthetic_score'] or 0.0,
                        nsfw_score=row['nsfw_score'] or 0.0,
                        clip_score=row['clip_score'] or 0.0,
                        rating=row['rating'] or 0,
                        color=row['color'] or '',
                        annotation=row['annotation'] or '',
                        width=row['width'] or 0,
                        height=row['height'] or 0,
                        format=row['format'] or '',
                        created_at=row['created_at'],
                        updated_at=row['updated_at'],
                    )
                    # Load tags from metadata or separate table
                    self.assets[asset.id] = asset

                # Load datasets
                cursor.execute("SELECT * FROM datasets")
                rows = cursor.fetchall()
                for row in rows:
                    self.datasets[row['id']] = {
                        'id': row['id'],
                        'name': row['name'],
                        'description': row['description'],
                        'asset_count': row['asset_count'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                    }

                logger.info(f"Loaded {len(self.assets)} assets and {len(self.datasets)} datasets to memory")
        except Exception as e:
            logger.warning(f"Could not load data to memory: {e}")

    def add_asset(self, asset: Asset) -> bool:
        """Add a new asset to the database - 完整Eagle功能"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()

                # 处理palette/tags/metadata为JSON字符串
                palette_json = json.dumps(asset.palette) if asset.palette else '[]'
                tags_json = json.dumps(asset.tags) if asset.tags else '[]'
                metadata_json = json.dumps(asset.metadata) if asset.metadata else '{}'

                # Use parameterized queries to prevent SQL injection
                # Include ALL Eagle-style extended fields
                cursor.execute('''
                    INSERT OR REPLACE INTO assets
                    (id, name, type, path, size, hash, tags, metadata, quality_score, aesthetic_score,
                     nsfw_score, clip_score, rating, color, palette, primary_color, annotation,
                     folder_id, favorite, width, height, duration, format, mime_type, orientation,
                     source_url, author, copyright, thumbnail_path, import_source,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    asset.id,
                    asset.name,
                    asset.type,
                    asset.path,
                    asset.size,
                    asset.hash,
                    tags_json,
                    metadata_json,
                    asset.quality_score,
                    asset.aesthetic_score,
                    asset.nsfw_score,
                    asset.clip_score,
                    asset.rating,
                    asset.color,
                    palette_json,
                    asset.primary_color,
                    asset.annotation,
                    asset.folder_id,
                    1 if asset.favorite else 0,
                    asset.width,
                    asset.height,
                    asset.duration,
                    asset.format,
                    asset.mime_type,
                    asset.orientation,
                    asset.source_url,
                    asset.author,
                    asset.copyright,
                    asset.thumbnail_path,
                    asset.import_source,
                    asset.created_at,
                    asset.updated_at
                ))

                conn.commit()

                # Also add to memory cache
                self.assets[asset.id] = asset

                logger.info(f"Added asset: {asset.name}")
                return True

            except Exception as e:
                logger.error(f"Error adding asset: {e}")
                conn.rollback()
                return False

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """Get an asset by ID with all related data"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Single query with joins to avoid N+1
            cursor.execute('''
                SELECT a.*,
                       GROUP_CONCAT(DISTINCT t.name) as tags_str,
                       GROUP_CONCAT(DISTINCT m.key || '=' || m.value) as metadata_str
                FROM assets a
                LEFT JOIN asset_tags at ON a.id = at.asset_id
                LEFT JOIN tags t ON at.tag_id = t.id
                LEFT JOIN metadata m ON a.id = m.asset_id
                WHERE a.id = ?
                GROUP BY a.id
            ''', (asset_id,))

            row = cursor.fetchone()
            if not row:
                return None

            # Parse tags
            tags = row['tags_str'].split(',') if row['tags_str'] else []

            # Parse metadata
            metadata = {}
            if row['metadata_str']:
                for item in row['metadata_str'].split(','):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        try:
                            metadata[key] = json.loads(value)
                        except json.JSONDecodeError:
                            metadata[key] = value

            return Asset(
                id=row['id'],
                name=row['name'],
                type=row['type'],
                path=row['path'],
                size=row['size'],
                hash=row['hash'],
                tags=tags,
                metadata=metadata,
                quality_score=row['quality_score'],
                aesthetic_score=row['aesthetic_score'],
                nsfw_score=row['nsfw_score'],
                clip_score=row['clip_score'],
                # Eagle风格扩展字段
                rating=row['rating'],
                color=row['color'],
                annotation=row['annotation'],
                width=row['width'],
                height=row['height'],
                format=row['format'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

    def search_assets(
        self,
        query: Optional[str] = None,
        asset_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_quality: Optional[float] = None,
        min_aesthetic: Optional[float] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Asset], int]:
        """Search for assets with filters - simplified version"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Build query - simplified version
            sql = 'SELECT * FROM assets WHERE 1=1'
            params = []

            # Handle tags filter - simplified (parameterized, no f-string)
            if tags and len(tags) > 0:
                placeholders = ','.join(['?' for _ in tags])
                sql = 'SELECT * FROM assets WHERE id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (SELECT id FROM tags WHERE name IN (' + placeholders + ')))'
                params.extend(tags)

            if query:
                sql += ' AND name LIKE ?'
                params.append(f'%{query}%')

            if asset_type:
                sql += ' AND type = ?'
                params.append(asset_type)

            if min_quality is not None:
                sql += ' AND quality_score >= ?'
                params.append(min_quality)

            if min_aesthetic is not None:
                sql += ' AND aesthetic_score >= ?'
                params.append(min_aesthetic)

            # Get total count
            count_sql = sql.replace('SELECT *', 'SELECT COUNT(*) as count')
            try:
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0] or 0
            except (sqlite3.Error, ValueError):
                logger.warning(f"Failed to count query results")
                total = 0

            # Add pagination
            sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            assets = []
            for row in rows:
                assets.append(Asset(
                    id=row['id'],
                    name=row['name'],
                    type=row['type'],
                    path=row['path'],
                    size=row['size'],
                    hash=row['hash'],
                    quality_score=row['quality_score'] or 0.0,
                    aesthetic_score=row['aesthetic_score'] or 0.0,
                    nsfw_score=row['nsfw_score'] or 0.0,
                    clip_score=row['clip_score'] or 0.0,
                    rating=row['rating'] or 0,
                    color=row['color'] or '',
                    annotation=row['annotation'] or '',
                    width=row['width'] or 0,
                    height=row['height'] or 0,
                    format=row['format'] or '',
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                ))

            return assets, total

    def update_asset_scores(
        self,
        asset_id: str,
        quality_score: Optional[float] = None,
        aesthetic_score: Optional[float] = None,
        nsfw_score: Optional[float] = None,
        clip_score: Optional[float] = None
    ) -> bool:
        """Update asset quality scores"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()

                # Build dynamic update query with whitelist validation
                ALLOWED_COLUMNS = {
                    'quality_score', 'aesthetic_score', 'nsfw_score',
                    'clip_score', 'updated_at'
                }
                updates = []
                params = []

                if quality_score is not None:
                    updates.append('quality_score = ?')
                    params.append(quality_score)
                if aesthetic_score is not None:
                    updates.append('aesthetic_score = ?')
                    params.append(aesthetic_score)
                if nsfw_score is not None:
                    updates.append('nsfw_score = ?')
                    params.append(nsfw_score)
                if clip_score is not None:
                    updates.append('clip_score = ?')
                    params.append(clip_score)

                if not updates:
                    return False

                updates.append('updated_at = ?')
                params.append(datetime.now().isoformat())
                params.append(asset_id)

                # Validate all column names against whitelist before building SQL
                for u in updates:
                    col = u.split(' = ')[0]
                    if col not in ALLOWED_COLUMNS:
                        logger.error(f"Rejected non-whitelisted column: {col}")
                        return False

                # Build SQL with whitelist-validated columns (safe concatenation)
                query = "UPDATE assets SET " + ', '.join(updates) + " WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0

            except Exception as e:
                logger.error(f"Failed to update asset scores: {e}")
                conn.rollback()
                return False

    # =========================================================================
    # Eagle风格扩展功能
    # =========================================================================

    def update_asset_rating(self, asset_id: str, rating: int) -> bool:
        """更新资源评分 (1-5星)"""
        if rating < 0 or rating > 5:
            return False
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE assets SET rating = ?, updated_at = ? WHERE id = ?
                ''', (rating, datetime.now().isoformat(), asset_id))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to update rating: {e}")
                return False

    def update_asset_color(self, asset_id: str, color: str) -> bool:
        """更新资源颜色标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE assets SET color = ?, updated_at = ? WHERE id = ?
                ''', (color, datetime.now().isoformat(), asset_id))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to update color: {e}")
                return False

    def update_asset_annotation(self, asset_id: str, annotation: str) -> bool:
        """更新资源注释"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE assets SET annotation = ?, updated_at = ? WHERE id = ?
                ''', (annotation, datetime.now().isoformat(), asset_id))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to update annotation: {e}")
                return False

    def batch_update_rating(self, asset_ids: List[str], rating: int) -> int:
        """批量更新资源评分"""
        if rating < 0 or rating > 5:
            return 0
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                updated = 0
                for asset_id in asset_ids:
                    cursor.execute('''
                        UPDATE assets SET rating = ?, updated_at = ? WHERE id = ?
                    ''', (rating, datetime.now().isoformat(), asset_id))
                    updated += cursor.rowcount
                return updated
            except Exception as e:
                logger.error(f"Failed to batch update rating: {e}")
                return 0

    def batch_update_color(self, asset_ids: List[str], color: str) -> int:
        """批量更新资源颜色标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                updated = 0
                for asset_id in asset_ids:
                    cursor.execute('''
                        UPDATE assets SET color = ?, updated_at = ? WHERE id = ?
                    ''', (color, datetime.now().isoformat(), asset_id))
                    updated += cursor.rowcount
                return updated
            except Exception as e:
                logger.error(f"Failed to batch update color: {e}")
                return 0

    # ===== Eagle 核心功能：文件夹管理 =====

    def create_folder(self, folder: Folder) -> bool:
        """创建文件夹"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO folders (id, name, parent_id, is_smart, smart_rules, color, icon, sort_order, is_system, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    folder.id,
                    folder.name,
                    folder.parent_id,
                    1 if folder.is_smart else 0,
                    json.dumps(folder.smart_rules),
                    folder.color,
                    folder.icon,
                    folder.sort_order,
                    1 if folder.is_system else 0,
                    folder.created_at,
                    folder.updated_at
                ))
                conn.commit()
                logger.info(f"Created folder: {folder.name}")
                return True
            except Exception as e:
                logger.error(f"Failed to create folder: {e}")
                return False

    def get_folders(self, parent_id: str = None) -> List[Folder]:
        """获取文件夹列表"""
        folders = []
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                if parent_id is None:
                    cursor.execute('SELECT * FROM folders WHERE parent_id = "" OR parent_id IS NULL ORDER BY sort_order, name')
                else:
                    cursor.execute('SELECT * FROM folders WHERE parent_id = ? ORDER BY sort_order, name', (parent_id,))

                for row in cursor.fetchall():
                    folders.append(Folder(
                        id=row['id'],
                        name=row['name'],
                        parent_id=row['parent_id'] or '',
                        is_smart=bool(row['is_smart']),
                        smart_rules=json.loads(row['smart_rules'] or '{}'),
                        color=row['color'] or '',
                        icon=row['icon'] or '',
                        sort_order=row['sort_order'],
                        is_system=bool(row['is_system']),
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    ))
            except Exception as e:
                logger.error(f"Failed to get folders: {e}")
        return folders

    def get_all_folders(self) -> List[Folder]:
        """获取所有文件夹"""
        folders = []
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM folders ORDER BY sort_order, name')
                for row in cursor.fetchall():
                    folders.append(Folder(
                        id=row['id'],
                        name=row['name'],
                        parent_id=row['parent_id'] or '',
                        is_smart=bool(row['is_smart']),
                        smart_rules=json.loads(row['smart_rules'] or '{}'),
                        color=row['color'] or '',
                        icon=row['icon'] or '',
                        sort_order=row['sort_order'],
                        is_system=bool(row['is_system']),
                        created_at=row['created_at'],
                        updated_at=row['updated_at']
                    ))
            except Exception as e:
                logger.error(f"Failed to get all folders: {e}")
        return folders

    def delete_folder(self, folder_id: str) -> bool:
        """删除文件夹"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                # 先删除子文件夹
                cursor.execute('DELETE FROM folders WHERE parent_id = ?', (folder_id,))
                # 再删除文件夹本身
                cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
                # 清除该文件夹下的资产关联
                cursor.execute('UPDATE assets SET folder_id = "" WHERE folder_id = ?', (folder_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to delete folder: {e}")
                return False

    # ===== Eagle 核心功能：标签管理 =====

    def create_tag(self, tag: Tag) -> bool:
        """创建标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tags (id, name, group_id, parent_id, color, count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (tag.id, tag.name, tag.group_id, tag.parent_id, tag.color, tag.count, tag.created_at))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to create tag: {e}")
                return False

    def get_all_tags(self) -> List[Tag]:
        """获取所有标签"""
        tags = []
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM tags ORDER BY count DESC, name')
                for row in cursor.fetchall():
                    tags.append(Tag(
                        id=row['id'],
                        name=row['name'],
                        group_id=row['group_id'] or '',
                        parent_id=row['parent_id'] or '',
                        color=row['color'] or '',
                        count=row['count'],
                        created_at=row['created_at']
                    ))
            except Exception as e:
                logger.error(f"Failed to get tags: {e}")
        return tags

    def delete_tag(self, tag_id: str) -> bool:
        """删除标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM asset_tags WHERE tag_id = ?', (tag_id,))
                cursor.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to delete tag: {e}")
                return False

    def add_tag_to_assets(self, tag_id: str, asset_ids: List[str]) -> bool:
        """为资产添加标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                for asset_id in asset_ids:
                    cursor.execute('''
                        INSERT OR IGNORE INTO asset_tags (asset_id, tag_id) VALUES (?, ?)
                    ''', (asset_id, tag_id))
                # 更新标签计数
                cursor.execute('UPDATE tags SET count = count + ? WHERE id = ?', (len(asset_ids), tag_id))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to add tag to assets: {e}")
                return False

    def remove_tag_from_assets(self, tag_id: str, asset_ids: List[str]) -> bool:
        """从资产移除标签"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                for asset_id in asset_ids:
                    cursor.execute('DELETE FROM asset_tags WHERE asset_id = ? AND tag_id = ?', (asset_id, tag_id))
                # 更新标签计数
                cursor.execute('UPDATE tags SET count = MAX(0, count - ?) WHERE id = ?', (len(asset_ids), tag_id))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to remove tag from assets: {e}")
                return False

    # ===== Eagle 核心功能：收藏夹 =====

    def toggle_favorite(self, asset_id: str) -> bool:
        """切换收藏状态"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT favorite FROM assets WHERE id = ?', (asset_id,))
                row = cursor.fetchone()
                if row:
                    new_favorite = 0 if row['favorite'] else 1
                    cursor.execute('''
                        UPDATE assets SET favorite = ?, updated_at = ? WHERE id = ?
                    ''', (new_favorite, datetime.now().isoformat(), asset_id))
                    conn.commit()
                    return True
                return False
            except Exception as e:
                logger.error(f"Failed to toggle favorite: {e}")
                return False

    def get_favorites(self) -> List[Asset]:
        """获取所有收藏的资源"""
        assets = []
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM assets WHERE favorite = 1 ORDER BY updated_at DESC')
                for row in cursor.fetchall():
                    assets.append(self._row_to_asset(row))
            except Exception as e:
                logger.error(f"Failed to get favorites: {e}")
        return assets

    # ===== Eagle 核心功能：重复检测 =====

    def check_duplicate(self, file_hash: str) -> Asset:
        """检查是否有重复文件"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM assets WHERE hash = ? LIMIT 1', (file_hash,))
                row = cursor.fetchone()
                if row:
                    return self._row_to_asset(row)
            except Exception as e:
                logger.error(f"Failed to check duplicate: {e}")
        return None

    # ===== Eagle 核心功能：高级搜索 =====

    def advanced_search(
        self,
        query: str = None,
        folder_id: str = None,
        tags: List[str] = None,
        rating_min: int = None,
        rating_max: int = None,
        colors: List[str] = None,
        types: List[str] = None,
        favorite: bool = None,
        date_from: str = None,
        date_to: str = None,
        sort_by: str = 'created_at',
        sort_order: str = 'desc',
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[Asset], int]:
        """高级搜索 - 支持多维度筛选"""
        assets = []
        total = 0

        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()

                # 构建动态查询
                conditions = []
                params = []

                if query:
                    conditions.append('(name LIKE ? OR annotation LIKE ?)')
                    params.extend([f'%{query}%', f'%{query}%'])

                if folder_id:
                    conditions.append('folder_id = ?')
                    params.append(folder_id)

                if rating_min is not None:
                    conditions.append('rating >= ?')
                    params.append(rating_min)

                if rating_max is not None:
                    conditions.append('rating <= ?')
                    params.append(rating_max)

                if colors:
                    placeholders = ','.join(['?'] * len(colors))
                    conditions.append(f'color IN ({placeholders})')
                    params.extend(colors)

                if types:
                    placeholders = ','.join(['?'] * len(types))
                    conditions.append(f'type IN ({placeholders})')
                    params.extend(types)

                if favorite is not None:
                    conditions.append('favorite = ?')
                    params.append(1 if favorite else 0)

                if date_from:
                    conditions.append('created_at >= ?')
                    params.append(date_from)

                if date_to:
                    conditions.append('created_at <= ?')
                    params.append(date_to)

                # 构建WHERE子句 (所有conditions使用参数化占位符，safe concatenation)
                where_clause = ' AND '.join(conditions) if conditions else '1=1'

                # 排序 - 严格白名单校验 (防止ORDER BY注入)
                ALLOWED_SORT_COLUMNS = ['created_at', 'updated_at', 'name', 'rating', 'size']
                if sort_by not in ALLOWED_SORT_COLUMNS:
                    sort_by = 'created_at'
                order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

                # 查询总数 (safe concatenation with whitelisted WHERE + parameterized params)
                count_sql = 'SELECT COUNT(*) as total FROM assets WHERE ' + where_clause
                cursor.execute(count_sql, params)
                total = cursor.fetchone()['total']

                # 查询数据 (whitelisted ORDER BY columns, safe concatenation)
                sql = 'SELECT * FROM assets WHERE ' + where_clause + ' ORDER BY ' + sort_by + ' ' + order + ' LIMIT ? OFFSET ?'
                params.extend([limit, offset])

                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    assets.append(self._row_to_asset(row))

            except Exception as e:
                logger.error(f"Failed to advanced search: {e}")

        return assets, total

    def _row_to_asset(self, row) -> Asset:
        """将数据库行转换为Asset对象"""
        return Asset(
            id=row['id'],
            name=row['name'],
            type=row['type'],
            path=row['path'],
            size=row['size'],
            hash=row['hash'],
            tags=row['tags'],
            metadata=row['metadata'],
            quality_score=row['quality_score'],
            aesthetic_score=row['aesthetic_score'],
            nsfw_score=row['nsfw_score'],
            clip_score=row['clip_score'],
            rating=row['rating'],
            color=row['color'],
            palette=json.loads(row['palette']) if row.get('palette') else [],
            primary_color=row['primary_color'],
            annotation=row['annotation'],
            folder_id=row['folder_id'],
            favorite=bool(row['favorite']),
            width=row['width'],
            height=row['height'],
            duration=row['duration'],
            format=row['format'],
            mime_type=row['mime_type'],
            orientation=row['orientation'],
            source_url=row['source_url'],
            author=row['author'],
            copyright=row['copyright'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            thumbnail_path=row['thumbnail_path'],
            import_source=row['import_source']
        )

    def batch_add_annotation(self, asset_ids: List[str], annotation: str) -> int:
        """批量添加资源注释"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                updated = 0
                for asset_id in asset_ids:
                    cursor.execute('''
                        UPDATE assets SET annotation = ?, updated_at = ? WHERE id = ?
                    ''', (annotation, datetime.now().isoformat(), asset_id))
                    updated += cursor.rowcount
                return updated
            except Exception as e:
                logger.error(f"Failed to batch add annotation: {e}")
                return 0

    def get_assets_by_rating(self, rating: int, limit: int = 100, offset: int = 0) -> List[Asset]:
        """按评分筛选资源"""
        with self.pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM assets WHERE rating = ? ORDER BY created_at DESC LIMIT ? OFFSET ?
            ''', (rating, limit, offset))
            rows = cursor.fetchall()
            return [self._row_to_asset(row) for row in rows]

    def get_assets_by_color(self, color: str, limit: int = 100, offset: int = 0) -> List[Asset]:
        """按颜色标签筛选资源"""
        with self.pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM assets WHERE color = ? ORDER BY created_at DESC LIMIT ? OFFSET ?
            ''', (color, limit, offset))
            rows = cursor.fetchall()
            return [self._row_to_asset(row) for row in rows]

    # =========================================================================
    # 智能文件夹功能 (Eagle风格)
    # =========================================================================

    def create_smart_folder(self, folder_id: str, name: str, conditions: Dict[str, Any],
                           sort_by: str = 'created_at', sort_order: str = 'desc') -> bool:
        """创建智能文件夹"""
        import json
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO smart_folders (id, name, conditions, sort_by, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (folder_id, name, json.dumps(conditions), sort_by, sort_order,
                      datetime.now().isoformat(), datetime.now().isoformat()))
                return True
            except Exception as e:
                logger.error(f"Failed to create smart folder: {e}")
                return False

    def get_smart_folders(self) -> List[Dict[str, Any]]:
        """获取所有智能文件夹"""
        import json
        with self.pool.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM smart_folders ORDER BY created_at DESC')
            rows = cursor.fetchall()
            folders = []
            for row in rows:
                folders.append({
                    'id': row['id'],
                    'name': row['name'],
                    'conditions': json.loads(row['conditions']),
                    'sort_by': row['sort_by'],
                    'sort_order': row['sort_order'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                })
            return folders

    def get_smart_folder_assets(self, folder_id: str, limit: int = 100, offset: int = 0) -> List[Asset]:
        """获取智能文件夹中的资源"""
        import json
        with self.pool.get_connection() as conn:
            # 先获取智能文件夹条件
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT conditions FROM smart_folders WHERE id = ?', (folder_id,))
            row = cursor.fetchone()
            if not row:
                return []

            conditions = json.loads(row['conditions'])
            # 构建查询 - 字段/操作符白名单校验
            ALLOWED_SMART_FIELDS = {'rating', 'color', 'type'}
            ALLOWED_SMART_OPERATORS = {'eq', 'gt', 'lt'}
            where_clauses = []
            params = []

            for cond in conditions:
                field = cond.get('type', '')
                operator = cond.get('operator', 'eq')
                value = cond.get('value', '')

                # 白名单校验字段和操作符
                if field not in ALLOWED_SMART_FIELDS:
                    continue
                if operator not in ALLOWED_SMART_OPERATORS:
                    continue

                if field == 'rating':
                    if operator == 'eq':
                        where_clauses.append('rating = ?')
                        params.append(value)
                    elif operator == 'gt':
                        where_clauses.append('rating > ?')
                        params.append(value)
                    elif operator == 'lt':
                        where_clauses.append('rating < ?')
                        params.append(value)
                elif field == 'color':
                    if operator == 'eq':
                        where_clauses.append('color = ?')
                        params.append(value)
                elif field == 'type':
                    if operator == 'eq':
                        where_clauses.append('type = ?')
                        params.append(value)

            where_str = ' AND '.join(where_clauses) if where_clauses else '1=1'
            # Safe concatenation: where_clauses use whitelist-validated parameterized patterns only
            query = 'SELECT * FROM assets WHERE ' + where_str + ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_asset(row) for row in rows]

    def delete_smart_folder(self, folder_id: str) -> bool:
        """删除智能文件夹"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM smart_folders WHERE id = ?', (folder_id,))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to delete smart folder: {e}")
                return False

    def get_color_statistics(self) -> List[Dict[str, Any]]:
        """获取颜色标签统计"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT color, COUNT(*) as count FROM assets
                WHERE color != '' GROUP BY color ORDER BY count DESC
            ''')
            return [{'color': row[0], 'count': row[1]} for row in cursor.fetchall()]

    def get_rating_distribution(self) -> Dict[int, int]:
        """获取评分分布统计"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT rating, COUNT(*) as count FROM assets
                WHERE rating > 0 GROUP BY rating ORDER BY rating
            ''')
            return {row[0]: row[1] for row in cursor.fetchall()}

    def batch_add_assets(self, assets: List[Asset]) -> int:
        """Batch add assets with transaction"""
        with self.pool.get_connection() as conn:
            count = 0
            try:
                cursor = conn.cursor()

                # Disable autocommit for batch performance
                cursor.execute('BEGIN TRANSACTION')

                for asset in assets:
                    cursor.execute('''
                        INSERT OR REPLACE INTO assets
                        (id, name, type, path, size, hash, quality_score, aesthetic_score,
                         nsfw_score, clip_score, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        asset.id,
                        asset.name,
                        asset.type,
                        asset.path,
                        asset.size,
                        asset.hash,
                        asset.quality_score,
                        asset.aesthetic_score,
                        asset.nsfw_score,
                        asset.clip_score,
                        asset.created_at,
                        asset.updated_at
                    ))

                    for tag in asset.tags:
                        cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
                        cursor.execute('''
                            INSERT OR IGNORE INTO asset_tags (asset_id, tag_id)
                            SELECT ?, id FROM tags WHERE name = ?
                        ''', (asset.id, tag))

                    count += 1

                cursor.execute('COMMIT')
                logger.info(f"Batch added {count} assets")
                return count

            except Exception as e:
                cursor.execute('ROLLBACK')
                logger.error(f"Error batch adding assets: {e}")
                return 0

    def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM assets WHERE id = ?', (asset_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error deleting asset: {e}")
                conn.rollback()
                return False

    def create_asset(self, asset: Asset) -> str:
        """Create an asset and return its ID (alias for add_asset)"""
        success = self.add_asset(asset)
        return asset.id if success else ""

    def get_all_assets(self) -> List[Asset]:
        """Get all assets"""
        return list(self.assets.values())

    def get_assets_by_type(self, asset_type: str) -> List[Asset]:
        """Get assets filtered by type"""
        return [asset for asset in self.assets.values() if asset.type == asset_type]

    def classify_asset(self, asset_id: str) -> str:
        """Classify an asset based on its content/type"""
        asset = self.get_asset(asset_id)
        if not asset:
            return "unknown"

        # Simple classification based on type
        type_classification = {
            "image": "visual",
            "video": "visual",
            "audio": "audio",
            "3d": "3d_model",
            "text": "text",
            "document": "document"
        }
        return type_classification.get(asset.type, "unknown")

    def rate_asset(self, asset_id: str, quality: float = 0.5,
                   relevance: float = 0.5, diversity: float = 0.5) -> Dict[str, float]:
        """Rate an asset with quality, relevance, and diversity scores"""
        asset = self.get_asset(asset_id)
        if not asset:
            return {"quality": 0.0, "relevance": 0.0, "diversity": 0.0}

        # Update asset scores
        self.update_asset_scores(asset_id, quality, relevance, diversity)

        return {
            "quality": quality,
            "relevance": relevance,
            "diversity": diversity
        }

    def update_asset(self, asset_id: str, data: Dict[str, Any]) -> bool:
        """Update an asset with new data"""
        asset = self.get_asset(asset_id)
        if not asset:
            return False

        try:
            # Update fields based on data
            for key, value in data.items():
                if hasattr(asset, key):
                    setattr(asset, key, value)

            # Update in database
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                # Build update query dynamically
                set_clauses = []
                params = []
                for key, value in data.items():
                    if key in ['name', 'path', 'annotation', 'color', 'folder_id']:
                        set_clauses.append(f"{key} = ?")
                        params.append(value)

                if set_clauses:
                    query = f"UPDATE assets SET {', '.join(set_clauses)}, updated_at = ? WHERE id = ?"
                    params.append(datetime.now().isoformat())
                    params.append(asset_id)
                    cursor.execute(query, params)
                    conn.commit()

            # Update in-memory cache
            self.assets[asset_id] = asset
            return True

        except Exception as e:
            logger.error(f"Error updating asset: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            # Total assets
            cursor.execute('''
                SELECT COUNT(*) as count, SUM(size) as total_size,
                       AVG(quality_score) as avg_quality, AVG(aesthetic_score) as avg_aesthetic
                FROM assets
            ''')
            row = cursor.fetchone()
            total_assets = row[0] or 0
            total_size = row[1] or 0
            avg_quality = row[2] or 0
            avg_aesthetic = row[3] or 0

            # Assets by type
            cursor.execute('SELECT type, COUNT(*) as count FROM assets GROUP BY type')
            by_type = {r[0]: r[1] for r in cursor.fetchall()}

            # Top tags
            cursor.execute('''
                SELECT t.name, COUNT(*) as count
                FROM tags t
                JOIN asset_tags at ON t.id = at.tag_id
                GROUP BY t.name
                ORDER BY count DESC
                LIMIT 10
            ''')
            top_tags = [{'name': r[0], 'count': r[1]} for r in cursor.fetchall()]

            return {
                'total_assets': total_assets,
                'total_size': total_size,
                'by_type': by_type,
                'avg_quality': avg_quality,
                'avg_aesthetic': avg_aesthetic,
                'top_tags': top_tags
            }

    def search_fts(self, query: str, limit: int = 100) -> List[str]:
        """Full-text search using FTS5"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            # Use parameterized query for FTS
            cursor.execute('''
                SELECT a.name FROM assets a
                JOIN assets_fts fts ON a.rowid = fts.rowid
                WHERE assets_fts MATCH ?
                LIMIT ?
            ''', (query, limit))
            return [r[0] for r in cursor.fetchall()]

    def create_dataset(self, dataset_id: str, name: str, description: str = "") -> bool:
        """Create a new dataset"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO datasets (id, name, description, asset_count, created_at, updated_at)
                    VALUES (?, ?, ?, 0, ?, ?)
                ''', (dataset_id, name, description, now, now))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating dataset: {e}")
                conn.rollback()
                return False

    def add_asset_to_dataset(self, dataset_id: str, asset_id: str) -> bool:
        """Add an asset to a dataset"""
        with self.pool.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO dataset_assets (dataset_id, asset_id)
                    VALUES (?, ?)
                ''', (dataset_id, asset_id))
                cursor.execute('''
                    UPDATE datasets SET asset_count = asset_count + 1, updated_at = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), dataset_id))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error adding asset to dataset: {e}")
                conn.rollback()
                return False

    def get_dataset_assets(self, dataset_id: str, limit: int = 100, offset: int = 0) -> List[Asset]:
        """Get assets in a dataset"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT a.*,
                       GROUP_CONCAT(DISTINCT t.name) as tags_str,
                       GROUP_CONCAT(DISTINCT m.key || '=' || m.value) as metadata_str
                FROM assets a
                JOIN dataset_assets da ON a.id = da.asset_id
                LEFT JOIN asset_tags at ON a.id = at.asset_id
                LEFT JOIN tags t ON at.tag_id = t.id
                LEFT JOIN metadata m ON a.id = m.asset_id
                WHERE da.dataset_id = ?
                GROUP BY a.id
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?
            ''', (dataset_id, limit, offset))

            assets = []
            for row in cursor.fetchall():
                tags = row['tags_str'].split(',') if row['tags_str'] else []
                metadata = {}
                if row['metadata_str']:
                    for item in row['metadata_str'].split(','):
                        if '=' in item:
                            key, value = item.split('=', 1)
                            try:
                                metadata[key] = json.loads(value)
                            except json.JSONDecodeError:
                                metadata[key] = value

                assets.append(Asset(
                    id=row['id'],
                    name=row['name'],
                    type=row['type'],
                    path=row['path'],
                    size=row['size'],
                    hash=row['hash'],
                    tags=tags,
                    metadata=metadata,
                    quality_score=row['quality_score'],
                    aesthetic_score=row['aesthetic_score'],
                    nsfw_score=row['nsfw_score'],
                    clip_score=row['clip_score'],
                    # Eagle风格扩展字段
                    rating=row['rating'],
                    color=row['color'],
                    annotation=row['annotation'],
                    width=row['width'],
                    height=row['height'],
                    format=row['format'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                ))

            return assets

    def get_all_datasets(self) -> List[Dict[str, Any]]:
        """Get all datasets"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM datasets ORDER BY created_at DESC')
            return [
                {
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'asset_count': row['asset_count'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
                for row in cursor.fetchall()
            ]

    def close(self):
        """Close database connection pool"""
        self.pool.close_all()
        logger.info("Database connection pool closed")

    def rebuild_index(self, index_type: str = "all") -> Dict[str, Any]:
        """
        重建数据库索引
        index_type: 'all' (全部) | 'fts' (全文搜索) | 'tags' (标签) | 'quality' (评分)
        """
        results = {"success": True, "rebuilt": [], "errors": []}

        with self.pool.get_connection() as conn:
            try:
                if index_type in ("all", "fts"):
                    conn.execute("DROP INDEX IF EXISTS idx_assets_fts")
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
                            id, name, tags, metadata_content,
                            content='assets', content_rowid='rowid'
                        )
                    """)
                    conn.execute("INSERT INTO assets_fts SELECT id, name, tags, metadata FROM assets")
                    results["rebuilt"].append("fts")

                if index_type in ("all", "tags"):
                    conn.execute("DROP INDEX IF EXISTS idx_assets_tags")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_tags ON assets(tags)")
                    results["rebuilt"].append("tags")

                if index_type in ("all", "quality"):
                    conn.execute("DROP INDEX IF EXISTS idx_assets_quality")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_quality ON assets(quality_score DESC)")
                    conn.execute("DROP INDEX IF EXISTS idx_assets_aesthetic")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_aesthetic ON assets(aesthetic_score DESC)")
                    results["rebuilt"].append("quality")

                if index_type in ("all", "type"):
                    conn.execute("DROP INDEX IF EXISTS idx_assets_type")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type)")
                    results["rebuilt"].append("type")

                if index_type in ("all", "date"):
                    conn.execute("DROP INDEX IF EXISTS idx_assets_created")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_created ON assets(created_at DESC)")
                    results["rebuilt"].append("date")

                conn.commit()
                logger.info(f"Database indexes rebuilt: {results['rebuilt']}")
            except Exception as e:
                results["success"] = False
                results["errors"].append(str(e))
                logger.error(f"Index rebuild failed: {e}")

        # 刷新内存缓存
        self._load_to_memory()
        results["asset_count"] = len(self.assets)
        return results


# =============================================================================
# Global Database Instance
# =============================================================================

# Global database instance
_db_instance: Optional[DatabaseManager] = None


def get_database(db_path: str = None, pool_size: int = 5) -> DatabaseManager:
    """Get or create global database instance - for use by Nanobot and other modules"""
    global _db_instance
    if _db_instance is None:
        if db_path is None and not DatabaseEngineConfig.USE_POSTGRES:
            db_path = DatabaseEngineConfig.SQLITE_PATH
        _db_instance = DatabaseManager(db_path=db_path, pool_size=pool_size)
        logger.info(f"Database initialized: {_db_instance.db_path}")
    return _db_instance


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # When DATABASE_URL is set, this will use PostgreSQL; otherwise SQLite
    db = DatabaseManager(pool_size=3)

    if not DatabaseEngineConfig.USE_POSTGRES:
        # Add sample asset
        asset = Asset(
            id="test_1",
            name="sample_image.jpg",
            type="image",
            path="/path/to/image.jpg",
            size=2048000,
            hash="abc123",
            tags=["landscape", "nature"],
            metadata={"width": 1920, "height": 1080},
            quality_score=0.85,
            aesthetic_score=0.90
        )
        db.add_asset(asset)

    # Search
    results, total = db.search_assets(asset_type="image", limit=10)
    print(f"Found {total} assets")
    for a in results:
        print(f"  - {a.name} ({a.type})")

    # Stats
    stats = db.get_statistics()
    print(f"Statistics: {stats}")

    db.close()
