#!/usr/bin/env python3
"""
Nanobot Factory - 数据基础设施层
完整整合 PostgreSQL、Redis、RabbitMQ、S3/OSS

@author MiniMax Agent
@date 2026-03-02
@description 企业级数据基础设施，AI驱动的数据管理
"""

import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 基础设施模块版本
__version__ = "1.0.0"

# 导出所有子模块
from infrastructure.database import PostgresManager, get_postgres_manager, init_postgres_manager
from infrastructure.cache import RedisManager, get_redis_manager, init_redis_manager
from infrastructure.queue import RabbitMQManager, get_rabbitmq_manager, init_rabbitmq_manager
from infrastructure.storage import StorageManager, get_storage_manager, init_storage_manager, StorageType

# 导出数据模型
from infrastructure.database import (
    UserRecord,
    AgentRecord,
    TaskRecord,
    AssetRecord,
    WorkflowRecord,
    AgentStatus,
    TaskStatus
)

from infrastructure.queue import (
    TaskMessage,
    EventMessage,
    TaskPriority,
    TaskStatus as QueueTaskStatus,
    QueueName,
    RoutingKey
)

from infrastructure.storage import (
    ObjectMetadata,
    UploadResult,
    DownloadResult,
    StorageClass
)
