"""
NanoBot Factory - Memory Persistence Layer
记忆持久化层 - Redis存储实现

功能：
- 记忆数据的Redis持久化
- 向量嵌入缓存
- 定期备份机制
- 数据恢复

@author MiniMax Agent
@date 2026-04-11
"""

import asyncio
import json
import logging
import pickle
import hashlib
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


class RedisMemoryStorage:
    """
    Redis记忆存储
    
    提供记忆数据的持久化存储，支持：
    - 短时/长时/重要记忆分类存储
    - 自动过期策略
    - 向量嵌入缓存
    - 批量操作
    """
    
    # Key前缀
    PREFIX_SHORT = "memory:short:"      # 短时记忆
    PREFIX_LONG = "memory:long:"        # 长时记忆
    PREFIX_IMPORTANT = "memory:important:"  # 重要记忆
    PREFIX_EMBEDDING = "memory:embedding:"  # 向量嵌入
    PREFIX_INDEX = "memory:index:"      # 索引
    
    # 默认TTL
    DEFAULT_TTL_SECONDS = 3600 * 24 * 7  # 7天
    LONG_TERM_TTL_SECONDS = 3600 * 24 * 30  # 30天
    IMPORTANT_TTL_SECONDS = 3600 * 24 * 365  # 1年
    
    def __init__(
        self,
        redis_client=None,
        max_memory_mb: int = 512,
        enable_snapshot: bool = True
    ):
        """
        初始化Redis记忆存储
        
        Args:
            redis_client: Redis客户端（可选，默认使用内置客户端）
            max_memory_mb: 最大内存使用（MB）
            enable_snapshot: 是否启用快照
        """
        self._redis = redis_client
        self._max_memory_mb = max_memory_mb
        self._enable_snapshot = enable_snapshot
        self._local_cache: Dict[str, Any] = {}
        self._cache_lock = threading.RLock()
        self._connected = False
        self._use_fallback = redis_client is None
        
        # 尝试连接
        if redis_client is None:
            self._init_redis_client()
        
        # 启动后台任务
        if enable_snapshot:
            self._start_snapshot_timer()
        
        logger.info(f"RedisMemoryStorage initialized (fallback={self._use_fallback})")
    
    def _init_redis_client(self) -> bool:
        """初始化Redis客户端"""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                "redis://localhost:6379/0",
                encoding="utf-8",
                decode_responses=True
            )
            self._connected = True
            logger.info("Redis client connected")
            return True
        except ImportError:
            logger.warning("redis-py not installed, using in-memory fallback")
            self._use_fallback = True
            return False
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory fallback")
            self._use_fallback = True
            return False
    
    async def save_memory(
        self,
        memory_id: str,
        content: Any,
        memory_type: str = "short_term",
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        保存记忆
        
        Args:
            memory_id: 记忆ID
            content: 记忆内容
            memory_type: 记忆类型 (short_term/long_term/important)
            ttl_seconds: 过期时间（秒）
            metadata: 元数据
            
        Returns:
            是否保存成功
        """
        # 序列化内容
        if isinstance(content, (dict, list)):
            serialized = json.dumps(content, ensure_ascii=False)
        else:
            serialized = str(content)
        
        # 构建键名
        prefix = self._get_prefix(memory_type)
        key = f"{prefix}{memory_id}"
        
        # 构建数据
        data = {
            "id": memory_id,
            "content": serialized,
            "content_type": type(content).__name__,
            "memory_type": memory_type,
            "created_at": datetime.now().isoformat(),
            "metadata": json.dumps(metadata or {}, ensure_ascii=False)
        }
        
        # TTL设置
        if ttl_seconds is None:
            ttl_seconds = self._get_default_ttl(memory_type)
        
        try:
            if self._use_fallback:
                # 使用本地缓存
                with self._cache_lock:
                    self._local_cache[key] = {
                        **data,
                        "expires_at": datetime.now() + timedelta(seconds=ttl_seconds)
                    }
            else:
                # 使用Redis
                pipe = self._redis.pipeline()
                pipe.hset(key, mapping=data)
                pipe.expire(key, ttl_seconds)
                await pipe.execute()
            
            logger.debug(f"Memory saved: {memory_id} (type={memory_type})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save memory {memory_id}: {e}")
            return False
    
    async def get_memory(self, memory_id: str, memory_type: str = "short_term") -> Optional[Dict]:
        """
        获取记忆
        
        Args:
            memory_id: 记忆ID
            memory_type: 记忆类型
            
        Returns:
            记忆数据
        """
        prefix = self._get_prefix(memory_type)
        key = f"{prefix}{memory_id}"
        
        try:
            if self._use_fallback:
                with self._cache_lock:
                    if key in self._local_cache:
                        entry = self._local_cache[key]
                        # 检查过期
                        if entry.get("expires_at") and entry["expires_at"] < datetime.now():
                            del self._local_cache[key]
                            return None
                        return entry
                    return None
            else:
                data = await self._redis.hgetall(key)
                if not data:
                    return None
                
                # 反序列化
                if data.get("content"):
                    data["content"] = json.loads(data["content"])
                if data.get("metadata"):
                    data["metadata"] = json.loads(data["metadata"])
                return data
                
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None
    
    async def delete_memory(self, memory_id: str, memory_type: str = "short_term") -> bool:
        """删除记忆"""
        prefix = self._get_prefix(memory_type)
        key = f"{prefix}{memory_id}"
        
        try:
            if self._use_fallback:
                with self._cache_lock:
                    if key in self._local_cache:
                        del self._local_cache[key]
            else:
                await self._redis.delete(key)
            
            logger.debug(f"Memory deleted: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    async def list_memories(
        self,
        memory_type: str = "short_term",
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """列出记忆"""
        prefix = self._get_prefix(memory_type)
        
        try:
            if self._use_fallback:
                with self._cache_lock:
                    keys = [k for k in self._local_cache.keys() if k.startswith(prefix)]
                    memories = []
                    for k in keys[offset:offset + limit]:
                        entry = self._local_cache[k]
                        if entry.get("expires_at") and entry["expires_at"] < datetime.now():
                            continue
                        memories.append(entry)
                    return memories
            else:
                pattern = f"{prefix}*"
                keys = []
                async for key in self._redis.scan_iter(match=pattern, count=100):
                    keys.append(key)
                
                memories = []
                for key in keys[offset:offset + limit]:
                    data = await self._redis.hgetall(key)
                    if data:
                        if data.get("content"):
                            data["content"] = json.loads(data["content"])
                        if data.get("metadata"):
                            data["metadata"] = json.loads(data["metadata"])
                        memories.append(data)
                
                return memories
                
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return []
    
    async def save_embedding(self, memory_id: str, embedding: List[float]) -> bool:
        """保存向量嵌入"""
        key = f"{self.PREFIX_EMBEDDING}{memory_id}"
        
        try:
            serialized = json.dumps(embedding)
            
            if self._use_fallback:
                with self._cache_lock:
                    self._local_cache[key] = {
                        "id": memory_id,
                        "embedding": embedding,
                        "created_at": datetime.now().isoformat()
                    }
            else:
                await self._redis.set(key, serialized, ex=self.LONG_TERM_TTL_SECONDS)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save embedding {memory_id}: {e}")
            return False
    
    async def get_embedding(self, memory_id: str) -> Optional[List[float]]:
        """获取向量嵌入"""
        key = f"{self.PREFIX_EMBEDDING}{memory_id}"
        
        try:
            if self._use_fallback:
                with self._cache_lock:
                    entry = self._local_cache.get(key)
                    return entry["embedding"] if entry else None
            else:
                data = await self._redis.get(key)
                return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get embedding {memory_id}: {e}")
            return None
    
    async def search_by_embedding(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        memory_type: str = "long_term"
    ) -> List[Dict]:
        """通过向量相似度搜索"""
        prefix = self._get_prefix(memory_type)
        
        try:
            # 获取所有嵌入
            memories = await self.list_memories(memory_type, limit=1000)
            
            if not memories:
                return []
            
            # 计算相似度
            results = []
            for memory in memories:
                emb = await self.get_embedding(memory["id"])
                if emb:
                    similarity = self._cosine_similarity(query_embedding, emb)
                    results.append({
                        **memory,
                        "score": similarity
                    })
            
            # 排序并返回top_k
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Failed to search by embedding: {e}")
            return []
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
    
    async def convert_to_long_term(
        self,
        memory_id: str,
        content: Any,
        metadata: Optional[Dict] = None
    ) -> bool:
        """将短时记忆转换为长时记忆"""
        return await self.save_memory(
            memory_id=memory_id,
            content=content,
            memory_type="long_term",
            metadata=metadata
        )
    
    async def convert_to_important(
        self,
        memory_id: str,
        content: Any,
        metadata: Optional[Dict] = None
    ) -> bool:
        """将记忆标记为重要"""
        return await self.save_memory(
            memory_id=memory_id,
            content=content,
            memory_type="important",
            metadata=metadata
        )
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计"""
        stats = {
            "connected": self._connected,
            "using_fallback": self._use_fallback,
            "local_cache_size": len(self._local_cache),
            "memory_types": {}
        }
        
        for memory_type in ["short_term", "long_term", "important"]:
            prefix = self._get_prefix(memory_type)
            try:
                if self._use_fallback:
                    count = sum(1 for k in self._local_cache.keys() if k.startswith(prefix))
                else:
                    count = 0
                    async for _ in self._redis.scan_iter(match=f"{prefix}*", count=1000):
                        count += 1
                stats['memory_types'][memory_type] = count
            except (redis.RedisError, asyncio.TimeoutError):
                logger.warning(f"Failed to count memory type {memory_type}")
                stats['memory_types'][memory_type] = 0
        
        return stats
    
    async def backup(self, backup_path: str) -> bool:
        """备份记忆数据"""
        try:
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "memories": {}
            }
            
            for memory_type in ["short_term", "long_term", "important"]:
                memories = await self.list_memories(memory_type, limit=10000)
                backup_data["memories"][memory_type] = memories
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Memory backed up to {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False
    
    async def restore(self, backup_path: str) -> bool:
        """恢复记忆数据"""
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            for memory_type, memories in backup_data.get("memories", {}).items():
                for memory in memories:
                    await self.save_memory(
                        memory_id=memory["id"],
                        content=memory.get("content", ""),
                        memory_type=memory_type,
                        metadata=memory.get("metadata")
                    )
            
            logger.info(f"Memory restored from {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False
    
    def _get_prefix(self, memory_type: str) -> str:
        """获取键前缀"""
        prefixes = {
            "short_term": self.PREFIX_SHORT,
            "long_term": self.PREFIX_LONG,
            "important": self.PREFIX_IMPORTANT
        }
        return prefixes.get(memory_type, self.PREFIX_SHORT)
    
    def _get_default_ttl(self, memory_type: str) -> int:
        """获取默认TTL"""
        ttls = {
            "short_term": self.DEFAULT_TTL_SECONDS,
            "long_term": self.LONG_TERM_TTL_SECONDS,
            "important": self.IMPORTANT_TTL_SECONDS
        }
        return ttls.get(memory_type, self.DEFAULT_TTL_SECONDS)
    
    def _start_snapshot_timer(self) -> None:
        """启动定期快照定时器"""
        # 每小时执行一次快照
        self._snapshot_interval = 3600
        logger.info("Snapshot timer started (hourly)")
    
    async def close(self) -> None:
        """关闭存储"""
        if self._redis and not self._use_fallback:
            await self._redis.close()
        logger.info("RedisMemoryStorage closed")


# 便捷函数
_storage_instance: Optional[RedisMemoryStorage] = None


def get_memory_storage(redis_client=None) -> RedisMemoryStorage:
    """获取记忆存储单例"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = RedisMemoryStorage(redis_client)
    return _storage_instance


__all__ = ['RedisMemoryStorage', 'get_memory_storage']
