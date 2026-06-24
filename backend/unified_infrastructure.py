#!/usr/bin/env python3
"""
Nanobot Factory - 统一基础设施管理器
完整整合 PostgreSQL、Redis、RabbitMQ、S3/OSS 到生产系统

功能:
- 异步PostgreSQL: 高并发、大规模数据存储、向量搜索
- Redis: 会话缓存、状态管理、分布式锁、限流
- RabbitMQ: 异步任务队列、事件驱动
- S3/OSS: 海量对象存储

@author MiniMax Agent
@date 2026-03-02
@description 统一基础设施层，无缝集成所有数据库软件到项目
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

# 导入新基础设施模块
from infrastructure import (
    PostgresManager,
    RedisManager,
    RabbitMQManager,
    StorageManager,
    StorageType,
    UserRecord,
    AgentRecord,
    TaskRecord,
    AssetRecord,
    TaskMessage,
    EventMessage,
    TaskPriority,
    ObjectMetadata,
    UploadResult,
    DownloadResult
)

# 导入现有生产模块
from production_database import ProductionDatabaseManager, DatabaseConfig, get_database
from oss_manager import OSSManager, get_oss_manager, init_oss_manager
from production_agents import ProductionAgentCluster, get_production_cluster

logger = logging.getLogger(__name__)


# ============================================================================
# 配置类
# ============================================================================

class InfrastructureType(str, Enum):
    """基础设施类型"""
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    RABBITMQ = "rabbitmq"
    S3 = "s3"
    OSS = "oss"
    LOCAL = "local"


@dataclass
class InfrastructureConfig:
    """统一基础设施配置"""
    # PostgreSQL配置
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "nanobot_factory"
    postgres_username: str = "nanobot"
    postgres_password: str = ""
    postgres_pool_size: int = 20
    postgres_enable_vector: bool = True

    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_max_connections: int = 50

    # RabbitMQ配置
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_username: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_virtual_host: str = "/"

    # S3/OSS配置
    storage_type: str = "local"  # s3, oss, minio, local
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "nanobot-assets"
    s3_region: str = "us-east-1"
    local_storage_path: str = "./data/assets"

    # 统一开关
    enable_postgres: bool = True
    enable_redis: bool = True
    enable_rabbitmq: bool = True
    enable_storage: bool = True

    @classmethod
    def from_env(cls) -> "InfrastructureConfig":
        """从环境变量创建配置"""
        return cls(
            # PostgreSQL
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_database=os.getenv("POSTGRES_DB", "nanobot_factory"),
            postgres_username=os.getenv("POSTGRES_USER", "nanobot"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            postgres_pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "20")),
            postgres_enable_vector=os.getenv("POSTGRES_ENABLE_VECTOR", "true").lower() == "true",

            # Redis
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD", ""),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            redis_max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),

            # RabbitMQ
            rabbitmq_host=os.getenv("RABBITMQ_HOST", "localhost"),
            rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
            rabbitmq_username=os.getenv("RABBITMQ_USER", "guest"),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            rabbitmq_virtual_host=os.getenv("RABBITMQ_VHOST", "/"),

            # Storage
            storage_type=os.getenv("STORAGE_TYPE", "local"),
            s3_endpoint=os.getenv("S3_ENDPOINT", ""),
            s3_access_key=os.getenv("S3_ACCESS_KEY", ""),
            s3_secret_key=os.getenv("S3_SECRET_KEY", ""),
            s3_bucket=os.getenv("S3_BUCKET", "nanobot-assets"),
            s3_region=os.getenv("S3_REGION", "us-east-1"),
            local_storage_path=os.getenv("LOCAL_STORAGE_PATH", "./data/assets"),

            # Flags
            enable_postgres=os.getenv("ENABLE_POSTGRES", "true").lower() == "true",
            enable_redis=os.getenv("ENABLE_REDIS", "true").lower() == "true",
            enable_rabbitmq=os.getenv("ENABLE_RABBITMQ", "true").lower() == "true",
            enable_storage=os.getenv("ENABLE_STORAGE", "true").lower() == "true",
        )


# ============================================================================
# 统一基础设施管理器
# ============================================================================

class UnifiedInfrastructureManager:
    """
    统一基础设施管理器

    完整整合:
    - PostgreSQL (异步) + SQLite (同步备用)
    - Redis (异步缓存)
    - RabbitMQ (异步队列)
    - S3/OSS (异步存储)

    特性:
    - 异步/同步无缝切换
    - 向量搜索支持 (AI)
    - 分布式锁
    - 任务队列
    - 限流
    """

    def __init__(self, config: InfrastructureConfig = None):
        self.config = config or InfrastructureConfig.from_env()

        # 异步管理器
        self.postgres: Optional[PostgresManager] = None
        self.redis: Optional[RedisManager] = None
        self.rabbitmq: Optional[RabbitMQManager] = None
        self.storage: Optional[StorageManager] = None

        # 同步备用 (production_database)
        self.production_db: Optional[ProductionDatabaseManager] = None

        # 现有OSS管理器 (AI增强版)
        self.oss_manager: Optional[OSSManager] = None

        # Agent集群
        self.agent_cluster: Optional[ProductionAgentCluster] = None

        # 状态
        self._is_initialized = False

    async def initialize(self):
        """
        初始化所有基础设施

        异步初始化所有组件:
        1. PostgreSQL - 高并发数据存储
        2. Redis - 缓存和状态
        3. RabbitMQ - 任务队列
        4. Storage - 对象存储
        """
        if self._is_initialized:
            logger.warning("基础设施已初始化，跳过")
            return

        logger.info("开始初始化统一基础设施...")

        # 1. 初始化PostgreSQL (异步)
        if self.config.enable_postgres:
            try:
                self.postgres = PostgresManager(
                    host=self.config.postgres_host,
                    port=self.config.postgres_port,
                    database=self.config.postgres_database,
                    username=self.config.postgres_username,
                    password=self.config.postgres_password,
                    pool_size=self.config.postgres_pool_size,
                    enable_vector=self.config.postgres_enable_vector
                )
                await self.postgres.connect()
                logger.info("✓ PostgreSQL 异步管理器已初始化")
            except Exception as e:
                logger.error(f"PostgreSQL 初始化失败: {e}")
                # 降级到同步数据库
                self.production_db = get_database(DatabaseConfig.from_env())
                logger.info("✓ 使用同步数据库作为备用")

        # 2. 初始化Redis (异步)
        if self.config.enable_redis:
            try:
                self.redis = RedisManager(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    password=self.config.redis_password if self.config.redis_password else None,
                    db=self.config.redis_db,
                    max_connections=self.config.redis_max_connections
                )
                await self.redis.connect()
                logger.info("✓ Redis 缓存管理器已初始化")
            except Exception as e:
                logger.error(f"Redis 初始化失败: {e}")

        # 3. 初始化RabbitMQ (异步)
        if self.config.enable_rabbitmq:
            try:
                self.rabbitmq = RabbitMQManager(
                    host=self.config.rabbitmq_host,
                    port=self.config.rabbitmq_port,
                    username=self.config.rabbitmq_username,
                    password=self.config.rabbitmq_password
                )
                await self.rabbitmq.connect()
                logger.info("✓ RabbitMQ 队列管理器已初始化")
            except Exception as e:
                logger.error(f"RabbitMQ 初始化失败: {e}")

        # 4. 初始化存储 (异步)
        if self.config.enable_storage:
            try:
                storage_type_map = {
                    "s3": StorageType.S3,
                    "oss": StorageType.OSS,
                    "minio": StorageType.MINIO,
                    "local": StorageType.LOCAL
                }

                self.storage = StorageManager(
                    storage_type=storage_type_map.get(self.config.storage_type, StorageType.LOCAL),
                    endpoint=self.config.s3_endpoint,
                    access_key=self.config.s3_access_key,
                    secret_key=self.config.s3_secret_key,
                    bucket=self.config.s3_bucket,
                    region=self.config.s3_region,
                    local_path=self.config.local_storage_path
                )
                await self.storage.initialize()
                logger.info(f"✓ {self.config.storage_type.upper()} 存储管理器已初始化")
            except Exception as e:
                logger.error(f"存储初始化失败: {e}")

        # 5. 初始化同步数据库备用
        if not self.production_db:
            try:
                self.production_db = get_database(DatabaseConfig.from_env())
                logger.info("✓ 同步数据库已初始化")
            except Exception as e:
                logger.error(f"同步数据库初始化失败: {e}")

        # 6. 初始化现有OSS管理器
        try:
            self.oss_manager = get_oss_manager()
            logger.info("✓ OSS管理器(AI增强版)已加载")
        except Exception as e:
            logger.warning(f"OSS管理器初始化失败: {e}")
            pass

        # 7. 初始化Agent集群
        try:
            self.agent_cluster = get_production_cluster()
            # 连接基础设施到Agent集群
            self.agent_cluster.set_database(self)
            logger.info("✓ Agent集群已连接基础设施")
        except Exception as e:
            logger.error(f"Agent集群初始化失败: {e}")

        self._is_initialized = True
        logger.info("统一基础设施初始化完成!")

    async def close(self):
        """关闭所有连接"""
        if self.postgres:
            await self.postgres.disconnect()
        if self.redis:
            await self.redis.disconnect()
        if self.rabbitmq:
            await self.rabbitmq.disconnect()
        if self.storage:
            await self.storage.close()

        self._is_initialized = False
        logger.info("统一基础设施已关闭")

    # =========================================================================
    # 数据库操作 (自动选择异步/同步)
    # =========================================================================

    async def create_asset(self, asset_data: Dict[str, Any]) -> str:
        """
        创建资产 (自动选择PostgreSQL/同步数据库)

        Args:
            asset_data: 资产数据

        Returns:
            资产ID
        """
        if self.postgres and self.postgres.is_connected():
            # 使用异步PostgreSQL
            asset = AssetRecord(
                asset_id=asset_data.get("id") or str(uuid.uuid4()),
                name=asset_data.get("name", ""),
                asset_type=asset_data.get("asset_type", "image"),
                path=asset_data.get("path", ""),
                url=asset_data.get("url", ""),
                thumbnail_url=asset_data.get("thumbnail_url", ""),
                size=asset_data.get("size", 0),
                width=asset_data.get("width"),
                height=asset_data.get("height"),
                format=asset_data.get("format", ""),
                mime_type=asset_data.get("mime_type", ""),
                tags=asset_data.get("tags", []),
                metadata=asset_data.get("metadata", {}),
                folder_id=asset_data.get("folder_id"),
                project_id=asset_data.get("project_id"),
                user_id=asset_data.get("user_id", "")
            )
            await self.postgres.create_asset(asset)
            return asset.asset_id
        elif self.production_db:
            # 使用同步数据库
            return self.production_db.create_asset(asset_data)
        else:
            raise RuntimeError("没有可用的数据库")

    async def get_asset(self, asset_id: str) -> Optional[Dict]:
        """获取资产"""
        if self.postgres and self.postgres.is_connected():
            return await self.postgres.get_asset(asset_id)
        elif self.production_db:
            return self.production_db.get_asset(asset_id)
        return None

    async def search_assets(
        self,
        query: str = None,
        asset_type: str = None,
        folder_id: str = None,
        project_id: str = None,
        tags: List[str] = None,
        embedding: List[float] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        搜索资产 (支持向量搜索)

        Args:
            query: 文本查询
            asset_type: 资产类型
            folder_id: 文件夹ID
            project_id: 项目ID
            tags: 标签列表
            embedding: 向量嵌入 (用于AI语义搜索)
            limit: 返回数量

        Returns:
            资产列表
        """
        # 如果提供了向量，使用AI语义搜索
        if embedding and self.postgres and self.postgres.is_connected():
            return await self.postgres.search_assets_by_embedding(
                query_embedding=embedding,
                limit=limit
            )

        # 否则使用传统搜索
        if self.production_db:
            return self.production_db.search_assets(
                query=query,
                asset_type=asset_type,
                folder_id=folder_id,
                project_id=project_id,
                tags=tags,
                limit=limit
            )
        return []

    # =========================================================================
    # 缓存操作 (Redis)
    # =========================================================================

    async def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存"""
        if self.redis and self.redis.is_connected():
            return await self.redis.set(key, value, ex=ttl)
        return False

    async def cache_get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if self.redis and self.redis.is_connected():
            return await self.redis.get(key)
        return None

    async def cache_delete(self, key: str) -> int:
        """删除缓存"""
        if self.redis and self.redis.is_connected():
            return await self.redis.delete(key)
        return 0

    # 会话管理
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        data: Dict[str, Any],
        ttl: int = 86400
    ) -> bool:
        """创建会话"""
        if self.redis and self.redis.is_connected():
            return await self.redis.create_session(session_id, user_id, data, ttl)
        return False

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        if self.redis and self.redis.is_connected():
            return await self.redis.get_session(session_id)
        return None

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if self.redis and self.redis.is_connected():
            return await self.redis.delete_session(session_id)
        return False

    # Agent状态管理
    async def set_agent_state(
        self,
        agent_id: str,
        state: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """设置Agent状态"""
        if self.redis and self.redis.is_connected():
            return await self.redis.set_agent_state(agent_id, state, ttl)
        return False

    async def get_agent_state(self, agent_id: str) -> Optional[Dict]:
        """获取Agent状态"""
        if self.redis and self.redis.is_connected():
            return await self.redis.get_agent_state(agent_id)
        return None

    # 分布式锁
    async def acquire_lock(
        self,
        resource: str,
        owner: str,
        ttl: int = 30
    ) -> Optional[str]:
        """获取分布式锁"""
        if self.redis and self.redis.is_connected():
            return await self.redis.acquire_lock(resource, owner, ttl)
        return None

    async def release_lock(self, resource: str, lock_id: str) -> bool:
        """释放分布式锁"""
        if self.redis and self.redis.is_connected():
            return await self.redis.release_lock(resource, lock_id)
        return False

    # 限流
    async def rate_limit(
        self,
        key: str,
        limit: int,
        window: int
    ) -> bool:
        """限流检查"""
        if self.redis and self.redis.is_connected():
            return await self.redis.rate_limit(key, limit, window)
        return True  # 没有Redis时默认允许

    # =========================================================================
    # 任务队列 (RabbitMQ)
    # =========================================================================

    async def publish_task(
        self,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 5
    ) -> bool:
        """
        发布任务到队列

        Args:
            task_id: 任务ID
            task_type: 任务类型
            payload: 任务数据
            priority: 优先级 (1=高, 5=普通, 10=低)

        Returns:
            是否发布成功
        """
        if self.rabbitmq and self.rabbitmq.is_connected():
            task = TaskMessage(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                priority=priority
            )
            return await self.rabbitmq.publish_task(task)
        return False

    async def consume_tasks(
        self,
        queue: str,
        handler: Callable
    ):
        """消费任务队列"""
        if self.rabbitmq and self.rabbitmq.is_connected():
            await self.rabbitmq.consume_tasks(queue, handler)

    async def publish_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any]
    ) -> bool:
        """发布事件"""
        if self.rabbitmq and self.rabbitmq.is_connected():
            event = EventMessage(
                event_type=event_type,
                source=source,
                data=data
            )
            return await self.rabbitmq.publish_event(event)
        return False

    # =========================================================================
    # 存储操作 (S3/OSS)
    # =========================================================================

    async def upload_file(
        self,
        file_path: str,
        key: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[str]:
        """
        上传文件

        Args:
            file_path: 本地文件路径
            key: 存储键
            metadata: 元数据

        Returns:
            文件URL或None
        """
        if self.storage:
            result = await self.storage.upload_file(file_path, key, metadata)
            if result:
                return result.url
        return None

    async def upload_data(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream"
    ) -> bool:
        """上传二进制数据"""
        if self.storage:
            return await self.storage.upload_data(data, key, content_type)
        return False

    async def download_file(self, key: str, local_path: str) -> bool:
        """下载文件"""
        if self.storage:
            return await self.storage.download_file(key, local_path)
        return False

    async def get_presigned_url(self, key: str, expires: int = 3600) -> Optional[str]:
        """获取预签名URL"""
        if self.storage:
            return await self.storage.get_presigned_url(key, expires)
        return None

    async def delete_file(self, key: str) -> bool:
        """删除文件"""
        if self.storage:
            return await self.storage.delete_file(key)
        return False

    async def list_files(self, prefix: str = "", max_keys: int = 100) -> List[ObjectMetadata]:
        """列出文件"""
        if self.storage:
            return await self.storage.list_files(prefix, max_keys)
        return []

    # =========================================================================
    # Agent集群集成
    # =========================================================================

    def get_agent_cluster(self) -> Optional[ProductionAgentCluster]:
        """获取Agent集群"""
        return self.agent_cluster

    async def submit_agent_task(
        self,
        agent_type: str,
        input_data: Dict[str, Any]
    ) -> str:
        """
        提交Agent任务

        Args:
            agent_type: Agent类型 (prompt_optimizer, prompt_generator, etc.)
            input_data: 输入数据

        Returns:
            任务ID
        """
        if self.agent_cluster:
            # 导入AgentType
            from production_agents import AgentType
            agent_type_enum = AgentType[agent_type.upper()]
            return await self.agent_cluster.submit_task(agent_type_enum, input_data)
        return ""

    def get_agent_status(self) -> List[Dict[str, Any]]:
        """获取所有Agent状态"""
        if self.agent_cluster:
            return self.agent_cluster.get_all_agents_status()
        return []

    # =========================================================================
    # 状态查询
    # =========================================================================

    def is_connected(self, infra_type: InfrastructureType = None) -> Union[bool, Dict]:
        """
        检查连接状态

        Args:
            infra_type: 特定基础设施类型，为None时返回所有状态

        Returns:
            连接状态
        """
        if infra_type:
            if infra_type == InfrastructureType.POSTGRESQL:
                return self.postgres.is_connected() if self.postgres else False
            elif infra_type == InfrastructureType.REDIS:
                return self.redis.is_connected() if self.redis else False
            elif infra_type == InfrastructureType.RABBITMQ:
                return self.rabbitmq.is_connected() if self.rabbitmq else False
            elif infra_type in [InfrastructureType.S3, InfrastructureType.OSS, InfrastructureType.LOCAL]:
                return self.storage is not None

        # 返回所有状态
        return {
            "postgresql": self.postgres.is_connected() if self.postgres else False,
            "redis": self.redis.is_connected() if self.redis else False,
            "rabbitmq": self.rabbitmq.is_connected() if self.rabbitmq else False,
            "storage": self.storage is not None,
            "production_db": self.production_db is not None,
            "oss_manager": self.oss_manager is not None,
            "agent_cluster": self.agent_cluster is not None
        }

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "connections": self.is_connected(),
            "timestamp": datetime.now().isoformat()
        }

        # Redis统计
        if self.redis and self.redis.is_connected():
            try:
                stats["redis"] = await self.redis.get_stats()
            except Exception as e:
                logger.warning(f"获取Redis统计失败: {e}")
                pass

        # RabbitMQ统计
        if self.rabbitmq and self.rabbitmq.is_connected():
            try:
                stats["rabbitmq"] = await self.rabbitmq.get_stats()
            except Exception as e:
                logger.warning(f"获取RabbitMQ统计失败: {e}")
                pass

        return stats


# ============================================================================
# 单例实例
# ============================================================================

_infrastructure_manager: Optional[UnifiedInfrastructureManager] = None


def get_infrastructure_manager() -> UnifiedInfrastructureManager:
    """获取统一基础设施管理器单例"""
    global _infrastructure_manager
    if _infrastructure_manager is None:
        _infrastructure_manager = UnifiedInfrastructureManager()
    return _infrastructure_manager


async def init_infrastructure(config: InfrastructureConfig = None) -> UnifiedInfrastructureManager:
    """
    初始化统一基础设施

    Args:
        config: 配置文件

    Returns:
        统一基础设施管理器实例
    """
    global _infrastructure_manager
    _infrastructure_manager = UnifiedInfrastructureManager(config)
    await _infrastructure_manager.initialize()
    return _infrastructure_manager


# ============================================================================
# 便捷函数 (兼容现有代码)
# ============================================================================

async def get_db_manager() -> Union[PostgresManager, ProductionDatabaseManager, None]:
    """获取数据库管理器 (自动选择异步/同步)"""
    infra = get_infrastructure_manager()
    if infra.postgres and infra.postgres.is_connected():
        return infra.postgres
    return infra.production_db


async def get_cache_manager() -> Optional[RedisManager]:
    """获取缓存管理器"""
    return get_infrastructure_manager().redis


async def get_queue_manager() -> Optional[RabbitMQManager]:
    """获取队列管理器"""
    return get_infrastructure_manager().rabbitmq


async def get_storage() -> Optional[StorageManager]:
    """获取存储管理器"""
    return get_infrastructure_manager().storage


def get_oss() -> Optional[OSSManager]:
    """获取OSS管理器 (AI增强版)"""
    return get_infrastructure_manager().oss_manager


def get_agents() -> Optional[ProductionAgentCluster]:
    """获取Agent集群"""
    return get_infrastructure_manager().agent_cluster
