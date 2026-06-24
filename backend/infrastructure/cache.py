#!/usr/bin/env python3
"""
Nanobot Factory - Redis 缓存模块
完整的异步 Redis 管理，支持会话、缓存、分布式锁

@author MiniMax Agent
@date 2026-03-02
@description 基于 redis-py 异步驱动的缓存管理
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Union, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib

# Redis 异步驱动
try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import redis
        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False
        logging.warning("Redis 驱动未安装: pip install redis")

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================

class CacheKey:
    """缓存键前缀"""
    USER_SESSION = "user:session:"
    AGENT_STATE = "agent:state:"
    TASK_RESULT = "task:result:"
    CACHE_PREFIX = "nanobot:"
    RATE_LIMIT = "rate:limit:"
    LOCK_PREFIX = "lock:"


class CacheTTL:
    """缓存TTL常量（秒）"""
    SHORT = 60           # 1分钟
    MEDIUM = 300         # 5分钟
    LONG = 3600          # 1小时
    DAY = 86400          # 1天
    WEEK = 604800        # 1周


@dataclass
class SessionData:
    """会话数据"""
    session_id: str
    user_id: str
    data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None


@dataclass
class LockData:
    """分布式锁数据"""
    lock_id: str
    resource: str
    owner: str
    expires_at: datetime
    acquired_at: datetime = field(default_factory=datetime.now)


# ============================================================================
# Redis 管理器
# ============================================================================

class RedisManager:
    """
    Redis 异步管理器
    支持会话、缓存、分布式锁、发布订阅
    """

    def __init__(
        self,
        url: str = None,
        host: str = "localhost",
        port: int = 6379,
        password: str = None,
        db: int = 0,
        decode_responses: bool = True,
        max_connections: int = 50
    ):
        """
        初始化 Redis 管理器

        Args:
            url: Redis 连接 URL
            host: 主机地址
            port: 端口
            password: 密码
            db: 数据库编号
            decode_responses: 是否解码响应
            max_connections: 最大连接数
        """
        self.url = url or os.getenv("REDIS_URL", f"redis://{host}:{port}")
        self.host = host
        self.port = port
        self.password = password or os.getenv("REDIS_PASSWORD")
        self.db = db
        self.decode_responses = decode_responses
        self.max_connections = max_connections

        self._client: Optional[Redis] = None
        self._is_connected = False

    async def connect(self):
        """建立 Redis 连接"""
        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis 驱动未安装")

        try:
            # 创建连接池
            self._client = redis.from_url(
                self.url,
                db=self.db,
                password=self.password,
                decode_responses=self.decode_responses,
                max_connections=self.max_connections,
                encoding="utf-8",
                encoding_errors="ignore"
            )

            # 测试连接
            await self._client.ping()

            self._is_connected = True
            logger.info(f"Redis 连接成功: {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            raise

    async def disconnect(self):
        """关闭 Redis 连接"""
        if self._client:
            await self._client.close()
        self._is_connected = False
        logger.info("Redis 连接已关闭")

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._is_connected

    # =========================================================================
    # 基础操作
    # =========================================================================

    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        if not self._client:
            return None
        return await self._client.get(key)

    async def set(
        self,
        key: str,
        value: Union[str, Dict, List],
        ex: int = None,
        px: int = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """设置值"""
        if not self._client:
            return False

        # 序列化
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)

        return await self._client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    async def delete(self, *keys: str) -> int:
        """删除键"""
        if not self._client:
            return 0
        return await self._client.delete(*keys)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self._client:
            return False
        return await self._client.exists(key) > 0

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        if not self._client:
            return False
        return await self._client.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        if not self._client:
            return -2
        return await self._client.ttl(key)

    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配的键"""
        if not self._client:
            return []
        return await self._client.keys(pattern)

    # =========================================================================
    # Hash 操作
    # =========================================================================

    async def hset(self, name: str, key: str = None, value: any = None, mapping: Dict = None) -> int:
        """设置 Hash"""
        if not self._client:
            return 0

        if mapping:
            return await self._client.hset(name, mapping=mapping)
        elif key and value:
            return await self._client.hset(name, key, value)
        return 0

    async def hget(self, name: str, key: str) -> Optional[str]:
        """获取 Hash 字段"""
        if not self._client:
            return None
        return await self._client.hget(name, key)

    async def hgetall(self, name: str) -> Dict[str, str]:
        """获取所有 Hash 字段"""
        if not self._client:
            return {}
        return await self._client.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        """删除 Hash 字段"""
        if not self._client:
            return 0
        return await self._client.hdel(name, *keys)

    async def hexists(self, name: str, key: str) -> bool:
        """检查 Hash 字段是否存在"""
        if not self._client:
            return False
        return await self._client.hexists(name, key)

    # =========================================================================
    # List 操作
    # =========================================================================

    async def lpush(self, key: str, *values: str) -> int:
        """左推入列表"""
        if not self._client:
            return 0
        return await self._client.lpush(key, *values)

    async def rpush(self, key: str, *values: str) -> int:
        """右推入列表"""
        if not self._client:
            return 0
        return await self._client.rpush(key, *values)

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[str]:
        """获取列表范围"""
        if not self._client:
            return []
        return await self._client.lrange(key, start, end)

    async def lpop(self, key: str) -> Optional[str]:
        """左弹出列表"""
        if not self._client:
            return None
        return await self._client.lpop(key)

    # =========================================================================
    # Set 操作
    # =========================================================================

    async def sadd(self, key: str, *values: str) -> int:
        """添加 Set 成员"""
        if not self._client:
            return 0
        return await self._client.sadd(key, *values)

    async def smembers(self, key: str) -> Set[str]:
        """获取 Set 所有成员"""
        if not self._client:
            return set()
        return await self._client.smembers(key)

    async def sismember(self, key: str, value: str) -> bool:
        """检查 Set 成员"""
        if not self._client:
            return False
        return await self._client.sismember(key, value)

    async def srem(self, key: str, *values: str) -> int:
        """移除 Set 成员"""
        if not self._client:
            return 0
        return await self._client.srem(key, *values)

    # =========================================================================
    # 有序 Set 操作
    # =========================================================================

    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """添加有序 Set 成员"""
        if not self._client:
            return 0
        return await self._client.zadd(key, mapping)

    async def zrange(
        self,
        key: str,
        start: int = 0,
        end: int = -1,
        withscores: bool = False
    ) -> List:
        """获取有序 Set 范围"""
        if not self._client:
            return []
        return await self._client.zrange(key, start, end, withscores=withscores)

    async def zrank(self, key: str, member: str) -> Optional[int]:
        """获取成员排名"""
        if not self._client:
            return None
        return await self._client.zrank(key, member)

    # =========================================================================
    # 会话管理
    # =========================================================================

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        data: Dict[str, Any],
        ttl: int = CacheTTL.DAY
    ) -> bool:
        """创建会话"""
        key = f"{CacheKey.USER_SESSION}{session_id}"
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "data": json.dumps(data),
            "created_at": datetime.now().isoformat()
        }
        return await self.hset(key, mapping=session, ex=ttl)

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        key = f"{CacheKey.USER_SESSION}{session_id}"
        data = await self.hgetall(key)
        if data and "data" in data:
            data["data"] = json.loads(data["data"])
        return data if data else None

    async def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """更新会话"""
        key = f"{CacheKey.USER_SESSION}{session_id}"
        return await self.hset(key, "data", json.dumps(data))

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        key = f"{CacheKey.USER_SESSION}{session_id}"
        return await self.delete(key) > 0

    async def extend_session(self, session_id: str, ttl: int = CacheTTL.DAY) -> bool:
        """延长会话过期时间"""
        key = f"{CacheKey.USER_SESSION}{session_id}"
        return await self.expire(key, ttl)

    # =========================================================================
    # Agent 状态管理
    # =========================================================================

    async def set_agent_state(
        self,
        agent_id: str,
        state: Dict[str, Any],
        ttl: int = CacheTTL.LONG
    ) -> bool:
        """设置 Agent 状态"""
        key = f"{CacheKey.AGENT_STATE}{agent_id}"
        return await self.set(key, json.dumps(state), ex=ttl)

    async def get_agent_state(self, agent_id: str) -> Optional[Dict]:
        """获取 Agent 状态"""
        key = f"{CacheKey.AGENT_STATE}{agent_id}"
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    async def delete_agent_state(self, agent_id: str) -> bool:
        """删除 Agent 状态"""
        key = f"{CacheKey.AGENT_STATE}{agent_id}"
        return await self.delete(key) > 0

    # =========================================================================
    # 任务结果缓存
    # =========================================================================

    async def cache_task_result(
        self,
        task_id: str,
        result: Any,
        ttl: int = CacheTTL.WEEK
    ) -> bool:
        """缓存任务结果"""
        key = f"{CacheKey.TASK_RESULT}{task_id}"
        return await self.set(key, json.dumps(result), ex=ttl)

    async def get_task_result(self, task_id: str) -> Optional[Any]:
        """获取任务结果"""
        key = f"{CacheKey.TASK_RESULT}{task_id}"
        value = await self.get(key)
        if value:
            return json.loads(value)
        return None

    # =========================================================================
    # 分布式锁
    # =========================================================================

    async def acquire_lock(
        self,
        resource: str,
        owner: str,
        ttl: int = 30
    ) -> Optional[str]:
        """
        获取分布式锁

        Args:
            resource: 资源名称
            owner: 锁持有者标识
            ttl: 锁过期时间（秒）

        Returns:
            锁ID或None
        """
        lock_id = hashlib.sha256(f"{resource}:{owner}".encode()).hexdigest()
        key = f"{CacheKey.LOCK_PREFIX}{resource}"

        # 尝试设置锁
        acquired = await self.set(
            key,
            json.dumps({
                "owner": owner,
                "lock_id": lock_id,
                "acquired_at": datetime.now().isoformat()
            }),
            ex=ttl,
            nx=True  # 仅当不存在时设置
        )

        if acquired:
            return lock_id
        return None

    async def release_lock(self, resource: str, lock_id: str) -> bool:
        """释放分布式锁"""
        key = f"{CacheKey.LOCK_PREFIX}{resource}"

        # 检查锁是否属于当前持有者
        current = await self.get(key)
        if not current:
            return False

        lock_data = json.loads(current)
        if lock_data.get("lock_id") != lock_id:
            return False

        return await self.delete(key) > 0

    async def extend_lock(self, resource: str, lock_id: str, ttl: int = 30) -> bool:
        """延长锁的过期时间"""
        key = f"{CacheKey.LOCK_PREFIX}{resource}"

        current = await self.get(key)
        if not current:
            return False

        lock_data = json.loads(current)
        if lock_data.get("lock_id") != lock_id:
            return False

        return await self.expire(key, ttl)

    # =========================================================================
    # 限流
    # =========================================================================

    async def rate_limit(
        self,
        key: str,
        limit: int,
        window: int
    ) -> bool:
        """
        限流检查

        Args:
            key: 限流键
            limit: 最大请求数
            window: 时间窗口（秒）

        Returns:
            是否允许请求
        """
        rate_key = f"{CacheKey.RATE_LIMIT}{key}"

        # 使用 INCR 实现限流
        current = await self._client.incr(rate_key)

        if current == 1:
            # 首次设置过期时间
            await self._client.expire(rate_key, window)

        return current <= limit

    async def get_rate_limit_info(self, key: str, window: int) -> Dict[str, Any]:
        """获取限流信息"""
        rate_key = f"{CacheKey.RATE_LIMIT}{key}"
        current = await self._client.get(rate_key)
        ttl = await self.ttl(rate_key)

        return {
            "current": int(current) if current else 0,
            "remaining": max(0, 100 - (int(current) if current else 0)),
            "reset_in": ttl if ttl > 0 else window
        }

    # =========================================================================
    # 发布订阅
    # =========================================================================

    async def publish(self, channel: str, message: Union[str, Dict]) -> int:
        """发布消息"""
        if not self._client:
            return 0

        if isinstance(message, (dict, list)):
            message = json.dumps(message, ensure_ascii=False)

        return await self._client.publish(channel, message)

    async def subscribe(self, channel: str, handler):
        """订阅频道（需要配合 asyncio 使用）"""
        if not self._client:
            return

        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    data = message["data"]
                await handler(data)

    # =========================================================================
    # 管道操作（批量）
    # =========================================================================

    async def pipeline(self):
        """创建管道"""
        if not self._client:
            return None
        return self._client.pipeline()

    # =========================================================================
    # 缓存工具
    # =========================================================================

    async def cache_get_or_set(
        self,
        key: str,
        getter_func,
        ttl: int = CacheTTL.MEDIUM
    ) -> Any:
        """
        获取缓存，如果不存在则调用 getter_func 获取并缓存

        Args:
            key: 缓存键
            getter_func: 获取数据的异步函数
            ttl: 过期时间

        Returns:
            缓存的数据
        """
        # 尝试获取缓存
        cached = await self.get(key)
        if cached:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                return cached

        # 调用函数获取数据
        data = await getter_func()

        # 缓存结果
        if data is not None:
            await self.set(key, json.dumps(data), ex=ttl)

        return data

    async def invalidate_pattern(self, pattern: str):
        """清除匹配模式的所有缓存"""
        keys = await self.keys(f"{CacheKey.CACHE_PREFIX}{pattern}*")
        if keys:
            await self.delete(*keys)

    # =========================================================================
    # 监控
    # =========================================================================

    async def get_info(self) -> Dict:
        """获取 Redis 信息"""
        if not self._client:
            return {}
        return await self._client.info()

    async def get_memory_usage(self) -> Dict:
        """获取内存使用情况"""
        info = await self.get_info()
        return {
            "used_memory": info.get("used_memory_human", "0"),
            "used_memory_peak": info.get("used_memory_peak_human", "0"),
            "connected_clients": info.get("connected_clients", 0)
        }

    async def get_stats(self) -> Dict:
        """获取统计信息"""
        info = await self.get_info()
        return {
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": info.get("keyspace_hits", 0) / max(
                info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1
            )
        }


# ============================================================================
# 单例实例
# ============================================================================

_redis_manager: RedisManager = None


def get_redis_manager() -> RedisManager:
    """获取 Redis 管理器单例"""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisManager()
    return _redis_manager


def init_redis_manager(
    url: str = None,
    host: str = "localhost",
    port: int = 6379,
    password: str = None
) -> RedisManager:
    """初始化 Redis 管理器"""
    global _redis_manager
    _redis_manager = RedisManager(
        url=url,
        host=host,
        port=port,
        password=password
    )
    return _redis_manager
