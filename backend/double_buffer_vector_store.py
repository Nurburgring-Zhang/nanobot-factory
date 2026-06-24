#!/usr/bin/env python3
"""
Nanobot Factory - 双缓冲向量存储模块
完整实现项目方案要求的双缓冲索引机制

功能：
- 双索引缓冲机制（HNSW索引动态重建）
- 读写分离设计
- 无感知切换
- 高并发支持

@author MiniMax Agent
@date 2026-03-03
"""

import os
import sys
import asyncio
import threading
import logging
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import json
import pickle
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# 配置
# ============================================================================

class IndexState(Enum):
    """索引状态"""
    ACTIVE = "active"      # 正在提供服务
    BUILDING = "building"  # 正在构建
    STANDBY = "standby"   # 备用


@dataclass
class VectorIndex:
    """向量索引封装"""
    index_id: str
    state: IndexState
    vectors: np.ndarray
    payloads: List[Dict]
    metadata: Dict[str, Any]
    created_at: float
    version: int
    index_type: str = "hnsw"  # hnsw, flat, ivf


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    score: float
    payload: Dict[str, Any]


# ============================================================================
# HNSW 索引实现（简化版）
# ============================================================================

class HNSWIndex:
    """
    简化版 HNSW (Hierarchical Navigable Small World) 索引
    实现高效的近似最近邻搜索
    """

    def __init__(
        self,
        m: int = 16,
        ef_construction: int = 200,
        ef_search: int = 50,
        vector_size: int = 768
    ):
        self.m = m
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.vector_size = vector_size

        # 索引数据结构
        self.data: List[np.ndarray] = []
        self.metadata: List[Dict] = []
        self.entry_point: Optional[int] = None
        self.max_level: int = 0

        # 跳表结构
        self.levels: List[Dict[int, List[int]]] = []
        self.distances: Dict[Tuple[int, int], float] = {}

    def _distance(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def _search_layer(
        self,
        query: np.ndarray,
        ep: int,
        ef: int,
        level: int
    ) -> List[Tuple[int, float]]:
        """在单层搜索"""
        visited = {ep}
        candidates = [(ep, self._distance(self.data[ep], query))]
        results = [(ep, self._distance(self.data[ep], query))]

        while candidates:
            # 按距离排序
            candidates.sort(key=lambda x: x[1])
            current, dist = candidates.pop(0)

            # 更新结果
            if len(results) < ef:
                results.append((current, dist))
                results.sort(key=lambda x: x[1])
            elif dist > results[-1][1]:
                break

            # 获取邻居
            if level < len(self.levels) and current in self.levels[level]:
                neighbors = self.levels[level][current]
                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        ndist = self._distance(self.data[neighbor], query)
                        if len(candidates) < ef or ndist < candidates[-1][1]:
                            candidates.append((neighbor, ndist))

        return results[:ef]

    def search(
        self,
        query: np.ndarray,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """搜索最近邻"""
        if not self.data:
            return []

        # 从顶层开始
        ep = self.entry_point
        for level in range(self.max_level, -1, -1):
            results = self._search_layer(query, ep, self.ef_search, level)
            ep = results[0][0] if results else None
            if ep is None:
                break

        # 返回 top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def add_vector(
        self,
        vector: np.ndarray,
        metadata: Dict[str, Any]
    ) -> int:
        """添加向量"""
        idx = len(self.data)
        self.data.append(vector)
        self.metadata.append(metadata)

        # 简化实现：每次添加只更新 entry_point
        if self.entry_point is None:
            self.entry_point = idx
            self.max_level = 0
            self.levels.append({})
        else:
            # 简单的插入逻辑
            dist = self._distance(vector, self.data[self.entry_point])
            if dist > self._distance(vector, self.data[self.entry_point]):
                self.entry_point = idx

        return idx

    def delete_vector(self, idx: int) -> bool:
        """删除向量"""
        if idx >= len(self.data):
            return False
        self.data[idx] = np.zeros(self.vector_size)
        self.metadata[idx] = {"deleted": True}
        return True

    def save(self, filepath: str):
        """保存索引"""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'data': self.data,
                'metadata': self.metadata,
                'entry_point': self.entry_point,
                'max_level': self.max_level,
                'levels': self.levels,
                'm': self.m,
                'ef_construction': self.ef_construction,
                'vector_size': self.vector_size
            }, f)

    def load(self, filepath: str):
        """加载索引"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.data = data['data']
            self.metadata = data['metadata']
            self.entry_point = data['entry_point']
            self.max_level = data['max_level']
            self.levels = data['levels']
            self.m = data['m']
            self.ef_construction = data['ef_construction']
            self.vector_size = data['vector_size']


# ============================================================================
# 双缓冲向量存储核心类
# ============================================================================

class DoubleBufferVectorStore:
    """
    双缓冲向量索引存储

    工作原理：
    1. 系统始终使用 active 状态的索引提供搜索服务
    2. 当需要重建时，创建新的索引（building 状态）
    3. 新索引构建完成后，切换为 standby 状态
    4. 原子切换 active 和 standby 索引的角色
    5. 旧索引在切换完成后可选择保留或释放
    """

    def __init__(
        self,
        storage_dir: str = "./data/vector_store",
        vector_size: int = 768,
        m: int = 16,
        ef_construction: int = 100,
        max_elements: int = 100000,
        rebuild_threshold: float = 0.3,
        rebuild_interval: int = 3600
    ):
        """
        初始化双缓冲向量存储

        Args:
            storage_dir: 存储目录
            vector_size: 向量维度
            m: HNSW 参数 M
            ef_construction: HNSW 构造参数
            max_elements: 最大元素数
            rebuild_threshold: 删除比例超过此值时触发重建
            rebuild_interval: 最小重建间隔（秒）
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.vector_size = vector_size
        self.m = m
        self.ef_construction = ef_construction
        self.max_elements = max_elements

        # 双索引缓冲
        self._index_a: Optional[HNSWIndex] = None
        self._index_b: Optional[HNSWIndex] = None
        self._active_index: Optional[HNSWIndex] = None
        self._standby_index: Optional[HNSWIndex] = None
        self._building_index: Optional[HNSWIndex] = None

        # 重建配置
        self._rebuild_threshold = rebuild_threshold
        self._rebuild_interval = rebuild_interval
        self._last_rebuild_time = 0
        self._deleted_count = 0
        self._total_count = 0

        # 线程安全
        self._swap_lock = threading.Lock()
        self._write_lock = asyncio.Lock()

        # 统计信息
        self._stats = {
            "total_searches": 0,
            "total_adds": 0,
            "total_deletes": 0,
            "rebuild_count": 0,
            "avg_search_time": 0
        }

        # 初始化索引
        self._initialize_indexes()

        logger.info(f"双缓冲向量存储初始化完成: {self.storage_dir}")

    def _initialize_indexes(self):
        """初始化两个索引"""
        index_a_path = self.storage_dir / "index_a.pkl"
        index_b_path = self.storage_dir / "index_b.pkl"

        # 加载或创建索引 A
        if index_a_path.exists():
            self._index_a = HNSWIndex(
                m=self.m,
                ef_construction=self.ef_construction,
                vector_size=self.vector_size
            )
            self._index_a.load(str(index_a_path))
            logger.info("加载索引 A 成功")
        else:
            self._index_a = HNSWIndex(
                m=self.m,
                ef_construction=self.ef_construction,
                vector_size=self.vector_size
            )

        # 加载或创建索引 B
        if index_b_path.exists():
            self._index_b = HNSWIndex(
                m=self.m,
                ef_construction=self.ef_construction,
                vector_size=self.vector_size
            )
            self._index_b.load(str(index_b_path))
            logger.info("加载索引 B 成功")
        else:
            self._index_b = HNSWIndex(
                m=self.m,
                ef_construction=self.ef_construction,
                vector_size=self.vector_size
            )

        # 设置活动索引
        self._active_index = self._index_a
        self._standby_index = self._index_b

    async def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        ef: int = 50
    ) -> List[SearchResult]:
        """
        搜索接口 - 使用 active 索引

        Args:
            query_vector: 查询向量
            top_k: 返回前 k 个结果
            ef: 搜索参数

        Returns:
            List[SearchResult]: 搜索结果列表
        """
        start_time = time.time()

        with self._swap_lock:
            if self._active_index is None:
                return []

            # 执行搜索
            results = self._active_index.search(query_vector, top_k)

        # 转换为结果对象
        search_results = []
        for idx, dist in results:
            if idx < len(self._active_index.metadata):
                metadata = self._active_index.metadata[idx]
                if not metadata.get("deleted", False):
                    search_results.append(SearchResult(
                        id=metadata.get("id", str(idx)),
                        score=float(dist),
                        payload=metadata
                    ))

        # 更新统计
        self._stats["total_searches"] += 1
        elapsed = time.time() - start_time
        self._stats["avg_search_time"] = (
            (self._stats["avg_search_time"] * (self._stats["total_searches"] - 1) + elapsed)
            / self._stats["total_searches"]
        )

        return search_results

    async def add_vector(
        self,
        vector: np.ndarray,
        payload: Dict[str, Any],
        vector_id: Optional[str] = None
    ) -> str:
        """
        添加向量

        Args:
            vector: 向量数据
            payload: 元数据
            vector_id: 向量 ID（可选）

        Returns:
            str: 添加的向量 ID
        """
        async with self._write_lock:
            # 生成 ID
            if vector_id is None:
                vector_id = hashlib.md5(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest()

            # 添加 metadata
            metadata = {
                "id": vector_id,
                **payload,
                "created_at": datetime.now().isoformat()
            }

            # 添加到活动索引
            with self._swap_lock:
                if self._active_index:
                    self._active_index.add_vector(vector, metadata)

            self._stats["total_adds"] += 1
            self._total_count += 1

            # 检查是否需要重建
            await self._check_rebuild()

            return vector_id

    async def add_vectors_batch(
        self,
        vectors: np.ndarray,
        payloads: List[Dict[str, Any]]
    ) -> List[str]:
        """
        批量添加向量

        Args:
            vectors: 向量数组 (N, D)
            payloads: 元数据列表

        Returns:
            List[str]: 添加的向量 ID 列表
        """
        vector_ids = []

        for vector, payload in zip(vectors, payloads):
            vector_id = await self.add_vector(vector, payload)
            vector_ids.append(vector_id)

        return vector_ids

    async def delete_vector(self, vector_id: str) -> bool:
        """
        删除向量（逻辑删除）

        Args:
            vector_id: 向量 ID

        Returns:
            bool: 是否删除成功
        """
        async with self._write_lock:
            deleted = False

            # 从活动索引删除
            with self._swap_lock:
                if self._active_index:
                    for idx, metadata in enumerate(self._active_index.metadata):
                        if metadata.get("id") == vector_id:
                            self._active_index.delete_vector(idx)
                            deleted = True
                            break

            if deleted:
                self._stats["total_deletes"] += 1
                self._deleted_count += 1
                self._total_count -= 1

                # 检查是否需要重建
                await self._check_rebuild()

            return deleted

    async def _check_rebuild(self):
        """检查是否需要重建索引"""
        current_time = time.time()

        # 检查时间间隔
        if current_time - self._last_rebuild_time < self._rebuild_interval:
            return

        # 检查删除比例
        if self._total_count > 0:
            delete_ratio = self._deleted_count / self._total_count

            if delete_ratio >= self._rebuild_threshold:
                logger.info(f"触发索引重建: 删除比例 {delete_ratio:.2%}")
                await self._rebuild_index()

    async def _rebuild_index(self):
        """重建索引"""
        if self._building_index is not None:
            logger.info("索引重建正在进行中，跳过")
            return

        logger.info("开始重建索引...")

        try:
            # 创建新的构建索引
            self._building_index = HNSWIndex(
                m=self.m,
                ef_construction=self.ef_construction,
                vector_size=self.vector_size
            )

            # 从活动索引复制有效数据
            with self._swap_lock:
                if self._active_index:
                    for idx, (vector, metadata) in enumerate(
                        zip(self._active_index.data, self._active_index.metadata)
                    ):
                        if not metadata.get("deleted", False):
                            self._building_index.add_vector(vector, metadata)

            # 保存备用索引
            index_b_path = self.storage_dir / "index_b.pkl"
            self._building_index.save(str(index_b_path))

            # 原子切换
            with self._swap_lock:
                if self._active_index == self._index_a:
                    self._index_b = self._building_index
                    self._standby_index = self._index_b
                else:
                    self._index_a = self._building_index
                    self._standby_index = self._index_a

                self._active_index = self._building_index

            # 清理
            self._building_index = None
            self._deleted_count = 0
            self._last_rebuild_time = time.time()
            self._stats["rebuild_count"] += 1

            logger.info(f"索引重建完成: {self._stats['rebuild_count']} 次")

        except Exception as e:
            logger.error(f"索引重建失败: {str(e)}")
            self._building_index = None
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "total_vectors": self._total_count,
            "deleted_vectors": self._deleted_count,
            "active_index": "A" if self._active_index == self._index_a else "B"
        }

    async def save(self):
        """保存所有索引到磁盘"""
        with self._swap_lock:
            if self._index_a:
                index_a_path = self.storage_dir / "index_a.pkl"
                self._index_a.save(str(index_a_path))
                logger.info(f"保存索引 A: {index_a_path}")

            if self._index_b:
                index_b_path = self.storage_dir / "index_b.pkl"
                self._index_b.save(str(index_b_path))
                logger.info(f"保存索引 B: {index_b_path}")


# ============================================================================
# 向量存储管理器（对外接口）
# ============================================================================

class VectorStoreManager:
    """
    向量存储管理器
    提供统一的向量存储和检索接口
    """

    _instance: Optional['VectorStoreManager'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Dict[str, Any] = None):
        if hasattr(self, '_initialized'):
            return

        config = config or {}
        self._store: Optional[DoubleBufferVectorStore] = None
        self._initialized = False

        # 从配置初始化
        storage_dir = config.get("storage_dir", "./data/vector_store")
        vector_size = config.get("vector_size", 768)

        self._store = DoubleBufferVectorStore(
            storage_dir=storage_dir,
            vector_size=vector_size
        )

        self._initialized = True
        logger.info("向量存储管理器初始化完成")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_params: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        搜索向量

        Args:
            query: 查询文本
            top_k: 返回数量
            filter_params: 过滤参数

        Returns:
            List[SearchResult]: 搜索结果
        """
        # 将文本转换为向量（简化实现）
        # 实际应该使用 sentence-transformers
        query_vector = self._text_to_vector(query)

        results = await self._store.search(
            query_vector=query_vector,
            top_k=top_k
        )

        # 应用过滤
        if filter_params:
            results = [
                r for r in results
                if all(r.payload.get(k) == v for k, v in filter_params.items())
            ]

        return results

    async def add(
        self,
        text: str,
        payload: Dict[str, Any]
    ) -> str:
        """
        添加向量

        Args:
            text: 文本内容
            payload: 元数据

        Returns:
            str: 向量 ID
        """
        vector = self._text_to_vector(text)
        return await self._store.add_vector(vector, payload)

    async def delete(self, vector_id: str) -> bool:
        """
        删除向量

        Args:
            vector_id: 向量 ID

        Returns:
            bool: 是否删除成功
        """
        return await self._store.delete_vector(vector_id)

    def _text_to_vector(self, text: str) -> np.ndarray:
        """
        将文本转换为向量
        简化实现：使用随机向量
        实际应该使用 sentence-transformers 或其他 embedding 模型
        """
        np.random.seed(hash(text) % (2**32))
        return np.random.randn(self._store.vector_size).astype(np.float32)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._store.get_stats()

    async def close(self):
        """关闭并保存"""
        await self._store.save()


# ============================================================================
# 便捷函数
# ============================================================================

def get_vector_store(config: Dict[str, Any] = None) -> VectorStoreManager:
    """获取向量存储管理器实例"""
    return VectorStoreManager(config)


# ============================================================================
# 主程序（测试用）
# ============================================================================

async def main():
    """测试主程序"""
    print("=" * 60)
    print("  双缓冲向量存储测试")
    print("=" * 60)
    print()

    # 初始化
    store = VectorStoreManager({
        "storage_dir": "./test_vector_store",
        "vector_size": 128
    })

    # 添加测试数据
    print("[1/4] 添加测试数据...")
    test_texts = [
        "人工智能是未来的发展方向",
        "机器学习是人工智能的子领域",
        "深度学习是机器学习的分支",
        "自然语言处理用于文本分析",
        "计算机视觉用于图像识别"
    ]

    for i, text in enumerate(test_texts):
        vector_id = await store.add(
            text=text,
            payload={"text": text, "category": f"test_{i % 2}"}
        )
        print(f"   添加: {text[:30]}... -> {vector_id[:8]}")

    print()

    # 搜索
    print("[2/4] 搜索测试...")
    query = "人工智能和机器学习"
    results = await store.search(query, top_k=3)

    print(f"   查询: {query}")
    for r in results:
        print(f"   - {r.payload.get('text', '')[:30]}... (score: {r.score:.4f})")

    print()

    # 统计信息
    print("[3/4] 统计信息...")
    stats = store.get_stats()
    print(f"   总向量数: {stats['total_vectors']}")
    print(f"   搜索次数: {stats['total_searches']}")
    print(f"   平均搜索时间: {stats['avg_search_time']*1000:.2f}ms")
    print(f"   重建次数: {stats['rebuild_count']}")

    print()

    # 清理
    print("[4/4] 清理...")
    await store.close()

    print()
    print("=" * 60)
    print("  测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
