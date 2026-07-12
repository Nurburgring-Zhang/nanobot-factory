#!/usr/bin/env python3
"""
Nanobot Factory - PostgreSQL 数据库模块
完整的数据管理，支持向量存储和AI驱动查询

@author MiniMax Agent
@date 2026-03-02
@description 基于 asyncpg + SQLAlchemy 2.0 的异步PostgreSQL管理
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import asynccontextmanager
from enum import Enum

# 异步数据库驱动
try:
    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select, update, delete, text
    from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logging.warning("PostgreSQL 驱动未安装: pip install asyncpg sqlalchemy[asyncio]")

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class AgentStatus(Enum):
    """Agent状态"""
    IDLE = "idle"
    RUNNING = "running"
    BUSY = "busy"
    ERROR = "error"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UserRecord:
    """用户记录"""
    user_id: str
    username: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRecord:
    """Agent记录"""
    agent_id: str
    agent_type: str
    name: str
    status: str = AgentStatus.IDLE.value
    config: Dict[str, Any] = field(default_factory=dict)
    memory_vector: List[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class TaskRecord:
    """任务记录"""
    task_id: str
    agent_id: str
    task_type: str
    input_data: Dict[str, Any]
    status: str = TaskStatus.PENDING.value
    result: Any = None
    error: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class AssetRecord:
    """资产记录"""
    asset_id: str
    asset_type: str
    name: str
    url: str
    size: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: List[float] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowRecord:
    """工作流记录"""
    workflow_id: str
    name: str
    description: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    status: str = "draft"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ============================================================================
# PostgreSQL 管理器
# ============================================================================

class PostgresManager:
    """
    PostgreSQL 异步管理器
    支持连接池、向量存储、AI查询
    """

    def __init__(
        self,
        dsn: str = None,
        pool_size: int = None,
        max_overflow: int = None,
        pool_recycle: int = None,
        statement_timeout_ms: int = None,
        echo: bool = False
    ):
        """
        初始化 PostgreSQL 管理器

        P13-C1 调优: pool_size / max_overflow / pool_recycle / statement_timeout
        都从环境变量读取, 允许 ops 调优, 默认值见函数体.

        Args:
            dsn: PostgreSQL 连接字符串
            pool_size: 连接池大小 (默认 IMDF_PG_POOL_SIZE=10)
            max_overflow: 最大溢出连接数 (默认 IMDF_PG_MAX_OVERFLOW=20)
            pool_recycle: 连接回收秒数 (默认 1800s = 30min, 避免 stale conn)
            statement_timeout_ms: SQL 超时 (默认 30000ms = 30s, 防止慢 SQL 拖死池)
            echo: 是否打印SQL语句
        """
        self.dsn = dsn or os.getenv(
            "POSTGRES_DSN",
            "postgresql://nanobot:nanobot@localhost:5432/nanobot"
        )

        # 创建异步引擎
        self.engine = None
        self.pool = None
        self.pool_size = pool_size or int(os.getenv("IMDF_PG_POOL_SIZE", "10"))
        self.max_overflow = max_overflow or int(os.getenv("IMDF_PG_MAX_OVERFLOW", "20"))
        self.pool_recycle = pool_recycle or int(os.getenv("IMDF_PG_POOL_RECYCLE", "1800"))
        self.statement_timeout_ms = statement_timeout_ms or int(
            os.getenv("IMDF_PG_STATEMENT_TIMEOUT_MS", "30000")
        )
        self.echo = echo

        # 连接池
        self._connection = None
        self._is_connected = False

        # 会话工厂
        self.session_factory = None

    async def connect(self):
        """建立数据库连接"""
        if not POSTGRES_AVAILABLE:
            raise RuntimeError("PostgreSQL 驱动未安装")

        try:
            # 创建连接池 (P13-C1: 加 min_size + max_inactive_connection_lifetime + command_timeout)
            self._connection = await asyncpg.create_pool(
                self.dsn,
                min_size=int(os.getenv("IMDF_PG_POOL_MIN", "2")),
                max_size=self.pool_size,
                max_inactive_connection_lifetime=self.pool_recycle,
                command_timeout=self.statement_timeout_ms / 1000.0,
            )

            # 创建SQLAlchemy引擎（用于ORM）
            # 转换 dsn 格式 (postgresql:// -> postgresql+asyncpg://)
            async_dsn = self.dsn.replace("postgresql://", "postgresql+asyncpg://")

            # P13-C1: pool_recycle + connect_args server_settings (statement_timeout 等)
            self.engine = create_async_engine(
                async_dsn,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=self.pool_recycle,
                echo=self.echo,
                pool_pre_ping=True,
                connect_args={
                    "server_settings": {
                        "application_name": "imdf-backend",
                        "statement_timeout": str(self.statement_timeout_ms),
                        "idle_in_transaction_session_timeout": "60000",
                    },
                },
            )

            # 创建会话工厂
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            self._is_connected = True
            logger.info(f"PostgreSQL 连接成功: {self.dsn.split('@')[1] if '@' in self.dsn else 'localhost'}")

            # 初始化表结构
            await self._init_tables()

        except Exception as e:
            logger.error(f"PostgreSQL 连接失败: {e}")
            raise

    async def disconnect(self):
        """关闭数据库连接"""
        if self._connection:
            await self._connection.close()
        if self.engine:
            await self.engine.dispose()
        self._is_connected = False
        logger.info("PostgreSQL 连接已关闭")

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._is_connected

    async def _init_tables(self):
        """初始化表结构"""
        # 使用原始SQL创建表（支持向量扩展）
        create_tables_sql = """
        -- 启用向量扩展
        CREATE EXTENSION IF NOT EXISTS vector;

        -- 用户表
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB DEFAULT '{}'
        );

        -- Agent表
        CREATE TABLE IF NOT EXISTS agents (
            agent_id VARCHAR(255) PRIMARY KEY,
            agent_type VARCHAR(100) NOT NULL,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'idle',
            config JSONB DEFAULT '{}',
            memory_vector VECTOR(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 任务表
        CREATE TABLE IF NOT EXISTS tasks (
            task_id VARCHAR(255) PRIMARY KEY,
            agent_id VARCHAR(255) REFERENCES agents(agent_id),
            task_type VARCHAR(100) NOT NULL,
            input_data JSONB NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            result JSONB,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        -- 资产表
        CREATE TABLE IF NOT EXISTS assets (
            asset_id VARCHAR(255) PRIMARY KEY,
            asset_type VARCHAR(100) NOT NULL,
            name VARCHAR(255) NOT NULL,
            url TEXT NOT NULL,
            size BIGINT,
            metadata JSONB DEFAULT '{}',
            embedding VECTOR(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 工作流表
        CREATE TABLE IF NOT EXISTS workflows (
            workflow_id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            nodes JSONB NOT NULL,
            edges JSONB NOT NULL,
            status VARCHAR(50) DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 向量索引（用于AI语义搜索）
        CREATE INDEX IF NOT EXISTS idx_agents_vector ON agents USING ivfflat (memory_vector vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS idx_assets_vector ON assets USING ivfflat (embedding vector_cosine_ops);

        -- JSONB 索引
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id);
        CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(agent_type);
        """

        await self.execute_raw(create_tables_sql)
        logger.info("数据库表结构初始化完成")

    # =========================================================================
    # 基础操作
    # =========================================================================

    async def execute_raw(self, query: str, *args) -> Any:
        """
        执行原始SQL

        Args:
            query: SQL语句
            *args: 参数

        Returns:
            查询结果
        """
        async with self._connection.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, params: dict = None) -> List[Dict]:
        """
        执行SQL并返回结果

        Args:
            query: SQL语句
            params: 参数

        Returns:
            结果列表
        """
        async with self._connection.acquire() as conn:
            if params:
                result = await conn.fetch(query, *params.values())
            else:
                result = await conn.fetch(query)

            # 转换为字典列表
            return [dict(row) for row in result]

    # =========================================================================
    # 用户操作
    # =========================================================================

    async def create_user(self, user: UserRecord) -> bool:
        """创建用户"""
        query = """
        INSERT INTO users (user_id, username, email, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
            username = EXCLUDED.username,
            email = EXCLUDED.email,
            metadata = EXCLUDED.metadata
        """
        await self._connection.execute(
            query,
            user.user_id,
            user.username,
            user.email,
            json.dumps(user.metadata),
            user.created_at
        )
        return True

    async def get_user(self, user_id: str) -> Optional[Dict]:
        """获取用户"""
        query = "SELECT * FROM users WHERE user_id = $1"
        result = await self.execute(query, {"user_id": user_id})
        return result[0] if result else None

    async def list_users(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """列出用户"""
        query = "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2"
        return await self.execute(query, {"limit": limit, "offset": offset})

    async def update_user(self, user_id: str, data: Dict) -> bool:
        """更新用户"""
        set_clauses = []
        params = {"user_id": user_id}
        for key, value in data.items():
            if key != "user_id":
                set_clauses.append(f"{key} = ${len(params) + 1}")
                params[key] = json.dumps(value) if isinstance(value, (dict, list)) else value

        if set_clauses:
            query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = $1"
            await self.execute(query, params)
        return True

    async def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        query = "DELETE FROM users WHERE user_id = $1"
        await self.execute(query, {"user_id": user_id})
        return True

    # =========================================================================
    # Agent操作
    # =========================================================================

    async def create_agent(self, agent: AgentRecord) -> bool:
        """创建Agent"""
        query = """
        INSERT INTO agents (agent_id, agent_type, name, status, config, memory_vector, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (agent_id) DO UPDATE SET
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            config = EXCLUDED.config,
            memory_vector = EXCLUDED.memory_vector,
            updated_at = CURRENT_TIMESTAMP
        """
        vector_str = json.dumps(agent.memory_vector) if agent.memory_vector else None

        await self._connection.execute(
            query,
            agent.agent_id,
            agent.agent_type,
            agent.name,
            agent.status,
            json.dumps(agent.config),
            vector_str,
            agent.created_at,
            agent.updated_at
        )
        return True

    async def get_agent(self, agent_id: str) -> Optional[Dict]:
        """获取Agent"""
        query = "SELECT * FROM agents WHERE agent_id = $1"
        result = await self.execute(query, {"agent_id": agent_id})
        return result[0] if result else None

    async def list_agents(
        self,
        agent_type: str = None,
        status: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """列出Agent"""
        conditions = []
        params = {"limit": limit}

        if agent_type:
            conditions.append("agent_type = $1")
            params["agent_type"] = agent_type
            param_idx = 2
        else:
            param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM agents {where_clause} ORDER BY created_at DESC LIMIT $1"

        return await self.execute(query, params)

    async def update_agent_status(self, agent_id: str, status: str) -> bool:
        """更新Agent状态"""
        query = "UPDATE agents SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE agent_id = $2"
        await self.execute(query, {"status": status, "agent_id": agent_id})
        return True

    async def update_agent_memory(self, agent_id: str, memory_vector: List[float]) -> bool:
        """更新Agent记忆向量"""
        query = "UPDATE agents SET memory_vector = $1, updated_at = CURRENT_TIMESTAMP WHERE agent_id = $2"
        await self.execute(query, {"memory_vector": json.dumps(memory_vector), "agent_id": agent_id})
        return True

    async def search_agents_by_memory(
        self,
        query_vector: List[float],
        limit: int = 10
    ) -> List[Dict]:
        """通过记忆向量搜索Agent（语义搜索）"""
        query = """
        SELECT *, 1 - (memory_vector <=> $1) as similarity
        FROM agents
        WHERE memory_vector IS NOT NULL
        ORDER BY memory_vector <=> $1
        LIMIT $2
        """
        return await self.execute(query, {"query_vector": json.dumps(query_vector), "limit": limit})

    # =========================================================================
    # 任务操作
    # =========================================================================

    async def create_task(self, task: TaskRecord) -> bool:
        """创建任务"""
        query = """
        INSERT INTO tasks (task_id, agent_id, task_type, input_data, status, result, error, created_at, completed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (task_id) DO UPDATE SET
            status = EXCLUDED.status,
            result = EXCLUDED.result,
            error = EXCLUDED.error,
            completed_at = EXCLUDED.completed_at
        """
        await self._connection.execute(
            query,
            task.task_id,
            task.agent_id,
            task.task_type,
            json.dumps(task.input_data),
            task.status,
            json.dumps(task.result) if task.result else None,
            task.error,
            task.created_at,
            task.completed_at
        )
        return True

    async def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务"""
        query = "SELECT * FROM tasks WHERE task_id = $1"
        result = await self.execute(query, {"task_id": task_id})
        return result[0] if result else None

    async def list_tasks(
        self,
        agent_id: str = None,
        status: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """列出任务"""
        conditions = []
        params = {"limit": limit, "offset": offset}

        if agent_id:
            conditions.append("agent_id = $1")
            params["agent_id"] = agent_id
            param_idx = 2
        else:
            param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        # P13-C1: 修复 typo — 原 OFFSET 2 应为 OFFSET $2 (字面 2 永远只跳过 2 行)
        query = f"SELECT * FROM tasks {where_clause} ORDER BY created_at DESC LIMIT $1 OFFSET $2"

        return await self.execute(query, params)

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        error: str = None
    ) -> bool:
        """更新任务状态"""
        completed_at = datetime.now().isoformat() if status in ["completed", "failed"] else None

        query = """
        UPDATE tasks SET
            status = $1,
            result = $2,
            error = $3,
            completed_at = $4
        WHERE task_id = $5
        """
        await self.execute(query, {
            "status": status,
            "result": json.dumps(result) if result else None,
            "error": error,
            "completed_at": completed_at,
            "task_id": task_id
        })
        return True

    # =========================================================================
    # 资产操作
    # =========================================================================

    async def create_asset(self, asset: AssetRecord) -> bool:
        """创建资产"""
        query = """
        INSERT INTO assets (asset_id, asset_type, name, url, size, metadata, embedding, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (asset_id) DO UPDATE SET
            name = EXCLUDED.name,
            url = EXCLUDED.url,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding
        """
        embedding_str = json.dumps(asset.embedding) if asset.embedding else None

        await self._connection.execute(
            query,
            asset.asset_id,
            asset.asset_type,
            asset.name,
            asset.url,
            asset.size,
            json.dumps(asset.metadata),
            embedding_str,
            asset.created_at
        )
        return True

    async def get_asset(self, asset_id: str) -> Optional[Dict]:
        """获取资产"""
        query = "SELECT * FROM assets WHERE asset_id = $1"
        result = await self.execute(query, {"asset_id": asset_id})
        return result[0] if result else None

    async def list_assets(
        self,
        asset_type: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """列出资产"""
        if asset_type:
            query = "SELECT * FROM assets WHERE asset_type = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"
            return await self.execute(query, {"asset_type": asset_type, "limit": limit, "offset": offset})
        else:
            query = "SELECT * FROM assets ORDER BY created_at DESC LIMIT $1 OFFSET $2"
            return await self.execute(query, {"limit": limit, "offset": offset})

    async def search_assets_by_embedding(
        self,
        query_embedding: List[float],
        asset_type: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """通过向量搜索资产（相似图片搜索）"""
        conditions = "embedding IS NOT NULL"
        params = {"query_embedding": json.dumps(query_embedding), "limit": limit}

        if asset_type:
            conditions += " AND asset_type = $3"
            params["asset_type"] = asset_type

        query = f"""
        SELECT *, 1 - (embedding <=> $1) as similarity
        FROM assets
        WHERE {conditions}
        ORDER BY embedding <=> $1
        LIMIT $2
        """
        return await self.execute(query, params)

    async def delete_asset(self, asset_id: str) -> bool:
        """删除资产"""
        query = "DELETE FROM assets WHERE asset_id = $1"
        await self.execute(query, {"asset_id": asset_id})
        return True

    # =========================================================================
    # 工作流操作
    # =========================================================================

    async def create_workflow(self, workflow: WorkflowRecord) -> bool:
        """创建工作流"""
        query = """
        INSERT INTO workflows (workflow_id, name, description, nodes, edges, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (workflow_id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            nodes = EXCLUDED.nodes,
            edges = EXCLUDED.edges,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP
        """
        await self._connection.execute(
            query,
            workflow.workflow_id,
            workflow.name,
            workflow.description,
            json.dumps(workflow.nodes),
            json.dumps(workflow.edges),
            workflow.status,
            workflow.created_at,
            workflow.updated_at
        )
        return True

    async def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """获取工作流"""
        query = "SELECT * FROM workflows WHERE workflow_id = $1"
        result = await self.execute(query, {"workflow_id": workflow_id})
        return result[0] if result else None

    async def list_workflows(self, status: str = None, limit: int = 100) -> List[Dict]:
        """列出工作流"""
        if status:
            query = "SELECT * FROM workflows WHERE status = $1 ORDER BY created_at DESC LIMIT $2"
            return await self.execute(query, {"status": status, "limit": limit})
        else:
            query = "SELECT * FROM workflows ORDER BY created_at DESC LIMIT $1"
            return await self.execute(query, {"limit": limit})

    async def update_workflow_status(self, workflow_id: str, status: str) -> bool:
        """更新工作流状态"""
        query = "UPDATE workflows SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE workflow_id = $2"
        await self.execute(query, {"status": status, "workflow_id": workflow_id})
        return True

    # =========================================================================
    # AI驱动查询
    # =========================================================================

    async def text_to_sql(self, natural_language: str) -> Dict[str, Any]:
        """
        自然语言转SQL（AI驱动）

        这个功能需要LLM支持，这里返回SQL建议
        实际执行需要谨慎处理防止SQL注入
        """
        # 这是一个占位实现
        # 实际生产中应该使用LLM根据数据库schema生成安全的SQL
        return {
            "suggested_query": f"-- 自然语言: {natural_language}\n-- 请使用LLM生成安全的SQL查询",
            "warning": "此功能需要LLM支持，请使用 Agents 进行数据查询"
        }

    async def execute_analytics(self, query: str) -> Dict[str, Any]:
        """执行分析查询"""
        try:
            result = await self.execute(query)
            return {
                "success": True,
                "data": result,
                "count": len(result)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # =========================================================================
    # 事务支持
    # =========================================================================

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        async with self._connection.acquire() as conn:
            async with conn.transaction():
                yield conn


# ============================================================================
# 单例实例
# ============================================================================

_postgres_manager: PostgresManager = None


def get_postgres_manager() -> PostgresManager:
    """获取PostgreSQL管理器单例"""
    global _postgres_manager
    if _postgres_manager is None:
        _postgres_manager = PostgresManager()
    return _postgres_manager


def init_postgres_manager(dsn: str = None) -> PostgresManager:
    """初始化PostgreSQL管理器"""
    global _postgres_manager
    _postgres_manager = PostgresManager(dsn=dsn)
    return _postgres_manager
