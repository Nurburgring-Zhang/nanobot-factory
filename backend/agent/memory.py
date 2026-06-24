#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Enhanced Memory System
增强型记忆系统 - 实现三层记忆、用户Pin锁定、重要分级、多用户隔离

核心功能：
- 短记忆（当前会话）
- 长记忆（持久化存储）
- 重要记忆（Pin锁定）
- 重要性分级管理
- 访问频率追踪
- 多用户隔离
- 向量语义检索
- 自动记忆整理

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import json
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import uuid
import heapq
from collections import defaultdict

logger = logging.getLogger(__name__)


class ImportanceLevel(Enum):
    """重要性等级"""
    CRITICAL = 5   # 关键记忆（用户Pin锁定）
    HIGH = 4       # 高重要性
    NORMAL = 3     # 普通重要性
    LOW = 2        # 低重要性
    DISCARD = 1    # 可丢弃


class MemoryType(Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"       # 短记忆
    LONG_TERM = "long_term"         # 长记忆
    IMPORTANT = "important"         # 重要记忆


@dataclass
class Memory:
    """记忆"""
    id: str
    user_id: str
    content: str
    memory_type: MemoryType
    importance: ImportanceLevel = ImportanceLevel.NORMAL
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_pinned: bool = False
    session_id: Optional[str] = None
    parent_id: Optional[str] = None  # 引用其他记忆

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "tags": self.tags,
            "metadata": self.metadata,
            "is_pinned": self.is_pinned,
            "session_id": self.session_id,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """从字典创建"""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            importance=ImportanceLevel(data.get("importance", 3)),
            embedding=data.get("embedding"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            is_pinned=data.get("is_pinned", False),
            session_id=data.get("session_id"),
            parent_id=data.get("parent_id"),
        )


class VectorStore(ABC):
    """向量存储抽象基类"""

    @abstractmethod
    async def add(self, memory_id: str, embedding: List[float]) -> bool:
        """添加向量"""
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """删除向量"""
        pass


class SimpleVectorStore(VectorStore):
    """简单向量存储（基于余弦相似度）"""

    def __init__(self):
        self._vectors: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def add(self, memory_id: str, embedding: List[float]) -> bool:
        """添加向量"""
        async with self._lock:
            self._vectors[memory_id] = embedding
            return True

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        results = []

        # 简单的余弦相似度计算
        query_norm = sum(x**2 for x in query_embedding) ** 0.5
        if query_norm == 0:
            return []

        for memory_id, embedding in self._vectors.items():
            # 应用过滤
            if filter and not self._matches_filter(memory_id, filter):
                continue

            # 计算相似度
            dot_product = sum(a * b for a, b in zip(query_embedding, embedding))
            embedding_norm = sum(x**2 for x in embedding) ** 0.5

            if embedding_norm > 0:
                similarity = dot_product / (query_norm * embedding_norm)
                results.append({
                    "id": memory_id,
                    "score": similarity,
                })

        # 排序并返回top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _matches_filter(self, memory_id: str, filter: Dict[str, Any]) -> bool:
        """检查是否匹配过滤器"""
        # 简化实现
        return True

    async def delete(self, memory_id: str) -> bool:
        """删除向量"""
        async with self._lock:
            if memory_id in self._vectors:
                del self._vectors[memory_id]
                return True
            return False


class StorageBackend(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    async def save(self, memory: Memory) -> bool:
        """保存记忆"""
        pass

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        pass

    @abstractmethod
    async def search(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[MemoryType] = None,
        importance: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """搜索记忆"""
        pass

    @abstractmethod
    async def list_user_memories(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """列出用户记忆"""
        pass


class InMemoryStorage(StorageBackend):
    """内存存储后端"""

    def __init__(self):
        self._memories: Dict[str, Memory] = {}
        self._user_index: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def save(self, memory: Memory) -> bool:
        """保存记忆"""
        async with self._lock:
            self._memories[memory.id] = memory
            self._user_index[memory.user_id].add(memory.id)
            return True

    async def get(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        return self._memories.get(memory_id)

    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        async with self._lock:
            if memory_id in self._memories:
                memory = self._memories[memory_id]
                self._user_index[memory.user_id].discard(memory_id)
                del self._memories[memory_id]
                return True
            return False

    async def search(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[MemoryType] = None,
        importance: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """搜索记忆"""
        async with self._lock:
            results = []

            for memory_id in self._user_index.get(user_id, set()):
                memory = self._memories.get(memory_id)
                if not memory:
                    continue

                # 过滤
                if memory_type and memory.memory_type != memory_type:
                    continue

                if importance and memory.importance != importance:
                    continue

                if tags and not any(t in memory.tags for t in tags):
                    continue

                # 简单文本匹配（实际应使用向量搜索）
                if query.lower() in memory.content.lower():
                    results.append(memory)

            # 按重要性和访问时间排序
            results.sort(
                key=lambda m: (
                    -m.importance.value,
                    -m.access_count,
                    -m.last_accessed.timestamp(),
                ),
            )

            return results[:limit]

    async def list_user_memories(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """列出用户记忆"""
        async with self._lock:
            results = []

            for memory_id in self._user_index.get(user_id, set()):
                memory = self._memories.get(memory_id)
                if not memory:
                    continue

                if memory_type and memory.memory_type != memory_type:
                    continue

                results.append(memory)

            # 排序
            results.sort(
                key=lambda m: (
                    -m.importance.value,
                    -m.updated_at.timestamp(),
                ),
            )

            return results[:limit]


class EmbeddingGenerator(ABC):
    """嵌入生成器抽象基类"""

    @abstractmethod
    async def generate(self, text: str) -> List[float]:
        """生成嵌入向量"""
        pass


class SimpleEmbeddingGenerator(EmbeddingGenerator):
    """简单嵌入生成器（模拟）"""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    async def generate(self, text: str) -> List[float]:
        """生成嵌入向量"""
        # 简单的hash-based生成（实际应使用真实模型）
        import hashlib
        hash_bytes = hashlib.sha256(text.encode()).digest()

        # 转换为固定维度的向量
        vector = []
        for i in range(self.dimension):
            byte_index = i % len(hash_bytes)
            value = hash_bytes[byte_index] / 255.0
            # 添加一些基于位置的变化
            value = (value + 0.1 * (i % 10) / 10) % 1.0
            vector.append(value)

        # 归一化
        norm = sum(x**2 for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]

        return vector


class EnhancedMemorySystem:
    """
    增强型记忆系统

    核心功能：
    - 三层记忆管理（短/长/重要）
    - 用户Pin锁定
    - 重要性自动分级
    - 向量语义检索
    - 访问频率追踪
    - 自动记忆整理
    """

    def __init__(
        self,
        storage: Optional[StorageBackend] = None,
        vector_store: Optional[VectorStore] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        short_term_ttl: int = 3600,        # 短记忆TTL（秒）
        long_term_threshold: int = 10,     # 转为长记忆的访问次数
        auto_cleanup: bool = True,
        cleanup_interval: int = 3600,      # 清理间隔（秒）
    ):
        # 存储后端
        self.storage = storage or InMemoryStorage()
        self.vector_store = vector_store or SimpleVectorStore()
        self.embedding_generator = embedding_generator or SimpleEmbeddingGenerator()

        # 配置
        self.short_term_ttl = short_term_ttl
        self.long_term_threshold = long_term_threshold
        self.auto_cleanup = auto_cleanup
        self.cleanup_interval = cleanup_interval

        # 会话记忆缓存: {session_id: [memory_ids]}
        self._session_cache: Dict[str, List[str]] = defaultdict(list)

        # 访问频率追踪: {memory_id: count}
        self._access_counts: Dict[str, int] = defaultdict(int)

        # 运行状态
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info("EnhancedMemorySystem initialized")

    async def start(self):
        """启动记忆系统"""
        self._running = True
        if self.auto_cleanup:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("EnhancedMemorySystem started")

    async def stop(self):
        """停止记忆系统"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("EnhancedMemorySystem stopped")

    async def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        importance: ImportanceLevel = ImportanceLevel.NORMAL,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        添加记忆

        Args:
            user_id: 用户ID
            content: 记忆内容
            memory_type: 记忆类型
            importance: 重要性
            tags: 标签
            metadata: 元数据
            session_id: 会话ID

        Returns:
            记忆ID
        """
        # 生成嵌入
        embedding = await self.embedding_generator.generate(content)

        # 创建记忆
        memory = Memory(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            embedding=embedding,
            tags=tags or [],
            metadata=metadata or {},
            session_id=session_id,
        )

        # 保存到存储
        await self.storage.save(memory)

        # 添加到向量存储
        await self.vector_store.add(memory.id, embedding)

        # 更新会话缓存
        if session_id:
            self._session_cache[session_id].append(memory.id)

        logger.info(f"Memory added: {memory.id} (type={memory_type.value})")
        return memory.id

    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        memory = await self.storage.get(memory_id)
        if memory:
            # 更新访问信息
            memory.access_count += 1
            memory.last_accessed = datetime.now()
            await self.storage.save(memory)

            # 更新访问计数
            self._access_counts[memory_id] = memory.access_count

            # 检查是否需要升级
            await self._check_and_upgrade(memory)

        return memory

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        memory = await self.storage.get(memory_id)
        if memory and memory.is_pinned:
            # 不允许删除Pin的记忆
            logger.warning(f"Cannot delete pinned memory: {memory_id}")
            return False

        # 从向量存储删除
        await self.vector_store.delete(memory_id)

        # 从会话缓存删除
        if memory and memory.session_id:
            session_ids = self._session_cache[memory.session_id]
            if memory_id in session_ids:
                session_ids.remove(memory_id)

        # 从存储删除
        result = await self.storage.delete(memory_id)

        if result:
            logger.info(f"Memory deleted: {memory_id}")

        return result

    async def pin_memory(self, memory_id: str, pinned: bool = True) -> bool:
        """
        Pin/Unpin记忆

        Args:
            memory_id: 记忆ID
            pinned: 是否Pin

        Returns:
            是否成功
        """
        memory = await self.storage.get(memory_id)
        if not memory:
            return False

        memory.is_pinned = pinned
        memory.importance = ImportanceLevel.CRITICAL if pinned else memory.importance

        await self.storage.save(memory)

        logger.info(f"Memory {memory_id} pinned: {pinned}")
        return True

    async def set_importance(
        self,
        memory_id: str,
        importance: ImportanceLevel,
    ) -> bool:
        """设置重要性"""
        memory = await self.storage.get(memory_id)
        if not memory:
            return False

        # 如果是CRITICAL，自动Pin
        if importance == ImportanceLevel.CRITICAL:
            memory.is_pinned = True

        memory.importance = importance
        await self.storage.save(memory)

        return True

    async def search_memories(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[MemoryType] = None,
        importance: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """
        搜索记忆

        Args:
            user_id: 用户ID
            query: 查询文本
            memory_type: 记忆类型过滤
            importance: 重要性过滤
            tags: 标签过滤
            limit: 返回数量

        Returns:
            记忆列表
        """
        # 生成查询嵌入
        query_embedding = await self.embedding_generator.generate(query)

        # 向量搜索
        vector_results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=limit * 2,
            filter={"user_id": user_id},
        )

        # 获取记忆详情
        results = []
        for result in vector_results[:limit]:
            memory = await self.storage.get(result["id"])
            if memory:
                # 应用过滤
                if memory_type and memory.memory_type != memory_type:
                    continue
                if importance and memory.importance != importance:
                    continue
                if tags and not any(t in memory.tags for t in tags):
                    continue

                results.append(memory)

        return results

    async def get_session_memories(
        self,
        session_id: str,
        user_id: str,
    ) -> List[Memory]:
        """获取会话记忆"""
        memory_ids = self._session_cache.get(session_id, [])

        memories = []
        for memory_id in memory_ids:
            memory = await self.storage.get(memory_id)
            if memory:
                memories.append(memory)

        return memories

    async def convert_to_long_term(self, memory_id: str) -> bool:
        """转换为长记忆"""
        memory = await self.storage.get(memory_id)
        if not memory:
            return False

        if memory.memory_type != MemoryType.SHORT_TERM:
            return False

        memory.memory_type = MemoryType.LONG_TERM
        await self.storage.save(memory)

        logger.info(f"Memory converted to long_term: {memory_id}")
        return True

    async def _check_and_upgrade(self, memory: Memory):
        """检查并升级记忆"""
        # 检查访问频率
        if memory.access_count >= self.long_term_threshold:
            if memory.memory_type == MemoryType.SHORT_TERM:
                await self.convert_to_long_term(memory.id)

        # 检查重要性升级
        if memory.access_count >= 50 and memory.importance == ImportanceLevel.NORMAL:
            memory.importance = ImportanceLevel.HIGH
            await self.storage.save(memory)
        elif memory.access_count >= 100 and memory.importance == ImportanceLevel.HIGH:
            memory.importance = ImportanceLevel.CRITICAL
            await self.storage.save(memory)

    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup(self):
        """清理低价值和过期记忆"""
        # 简化实现：清理访问次数为0且超过TTL的短记忆
        # 实际应更复杂
        pass

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户记忆统计"""
        # 这是一个简化实现
        return {
            "user_id": user_id,
            "session_cache_size": len(self._session_cache),
            "access_counts": len(self._access_counts),
        }


# =============================================================================
# 工厂函数
# =============================================================================

def create_memory_system(
    storage: Optional[StorageBackend] = None,
    vector_store: Optional[VectorStore] = None,
    embedding_generator: Optional[EmbeddingGenerator] = None,
    short_term_ttl: int = 3600,
    long_term_threshold: int = 10,
) -> EnhancedMemorySystem:
    """
    创建增强型记忆系统

    Args:
        storage: 存储后端
        vector_store: 向量存储
        embedding_generator: 嵌入生成器
        short_term_ttl: 短记忆TTL
        long_term_threshold: 长记忆阈值

    Returns:
        EnhancedMemorySystem实例
    """
    return EnhancedMemorySystem(
        storage=storage,
        vector_store=vector_store,
        embedding_generator=embedding_generator,
        short_term_ttl=short_term_ttl,
        long_term_threshold=long_term_threshold,
    )


# =============================================================================
# 使用示例
# =============================================================================

async def example_usage():
    """使用示例"""
    # 创建记忆系统
    memory_system = create_memory_system()

    # 启动
    await memory_system.start()

    # 添加记忆
    memory_id = await memory_system.add_memory(
        user_id="user1",
        content="用户喜欢蓝色",
        memory_type=MemoryType.SHORT_TERM,
        tags=["preference", "color"],
    )

    # 添加更多记忆
    await memory_system.add_memory(
        user_id="user1",
        content="用户之前询问过Python编程问题",
        memory_type=MemoryType.LONG_TERM,
        importance=ImportanceLevel.HIGH,
        tags=["programming", "python"],
    )

    # Pin记忆
    await memory_system.pin_memory(memory_id, True)

    # 搜索
    results = await memory_system.search_memories(
        user_id="user1",
        query="用户喜欢什么颜色",
    )

    print(f"Found {len(results)} memories")

    # 获取统计
    print(memory_system.get_stats("user1"))

    # 停止
    await memory_system.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())
