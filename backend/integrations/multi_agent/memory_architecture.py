#!/usr/bin/env python3
"""
NanoBot Factory - 4-Layer Memory Architecture
四层记忆架构 - 实现真正的Agent记忆系统
Layer 1: Working Memory (工作记忆) - 当前任务上下文
Layer 2: Short-Term Memory (短期记忆) - 最近交互
Layer 3: Long-Term Memory (长期记忆) - 持久知识
Layer 4: Semantic Memory (语义记忆) - 结构化知识图谱
@author MiniMax Agent
@date 2026-04-15
"""
import asyncio
import logging
import json
import hashlib
import time
import uuid
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading
import re

logger = logging.getLogger(__name__)


class MemoryLayer(Enum):
    WORKING = "working"       # L1: 当前任务
    SHORT_TERM = "short_term" # L2: 最近交互
    LONG_TERM = "long_term"   # L3: 持久知识
    SEMANTIC = "semantic"     # L4: 知识图谱


class MemoryType(Enum):
    FACT = "fact"              # 事实
    PROCEDURE = "procedure"   # 流程
    EXPERIENCE = "experience"  # 经验
    PREFERENCE = "preference"  # 偏好
    RELATIONSHIP = "relationship"  # 关系
    CONTEXT = "context"       # 上下文


@dataclass
class MemoryEntry:
    """记忆条目"""
    entry_id: str
    content: str
    memory_type: MemoryType
    layer: MemoryLayer
    agent_id: Optional[str] = None
    entity_id: Optional[str] = None
    importance: float = 0.5  # 0.0 - 1.0
    relevance_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    embeddings: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "content": self.content[:200],
            "memory_type": self.memory_type.value,
            "layer": self.layer.value,
            "agent_id": self.agent_id,
            "importance": self.importance,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "tags": list(self.tags),
        }

    def access(self):
        """记录访问"""
        self.accessed_at = datetime.now()
        self.access_count += 1


@dataclass
class MemoryQuery:
    """记忆查询"""
    query_text: str
    agent_id: Optional[str] = None
    layers: List[MemoryLayer] = None
    memory_types: List[MemoryType] = None
    tags: Set[str] = None
    limit: int = 10
    min_importance: float = 0.0
    min_relevance: float = 0.0


@dataclass
class MemoryRetrievalResult:
    """记忆检索结果"""
    entries: List[MemoryEntry]
    total_found: int
    query: str
    retrieval_time_ms: float


class Layer1WorkingMemory:
    """
    Layer 1: Working Memory (工作记忆)
    存储当前任务的上下文信息，高频读写，容量有限
    """

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._entries: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()
        self._current_task_context: Dict[str, Any] = {}
        self._access_order: List[str] = []
        logger.info(f"Layer1 WorkingMemory 初始化, max_entries={max_entries}")

    def store(self, key: str, value: Any, memory_type: MemoryType = MemoryType.CONTEXT) -> MemoryEntry:
        """存储到工作记忆"""
        with self._lock:
            entry = MemoryEntry(
                entry_id=f"wm_{hashlib.md5(f'{key}_{time.time()}'.encode()).hexdigest()[:12]}",
                content=str(value),
                memory_type=memory_type,
                layer=MemoryLayer.WORKING,
                importance=0.8,
            )
            self._entries[key] = entry
            self._current_task_context[key] = value

            # LRU淘汰
            if len(self._entries) > self.max_entries:
                oldest = self._access_order.pop(0) if self._access_order else None
                if oldest and oldest in self._entries:
                    del self._entries[oldest]

            self._access_order.append(key)
            return entry

    def retrieve(self, key: str) -> Optional[Any]:
        """从工作记忆检索"""
        with self._lock:
            if key in self._entries:
                self._entries[key].access()
                return self._current_task_context.get(key)
            return None

    def get_all(self) -> Dict[str, Any]:
        """获取所有工作记忆"""
        return self._current_task_context.copy()

    def clear(self):
        """清空工作记忆"""
        with self._lock:
            self._entries.clear()
            self._current_task_context.clear()
            self._access_order.clear()
            logger.info("Layer1 工作记忆已清空")

    def set_task_context(self, task_id: str, context: Dict[str, Any]):
        """设置任务上下文"""
        with self._lock:
            self._current_task_context[f"task_{task_id}"] = context

    def get_task_context(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务上下文"""
        return self._current_task_context.get(f"task_{task_id}")


class Layer2ShortTermMemory:
    """
    Layer 2: Short-Term Memory (短期记忆)
    存储最近交互，容量适中，会随时间衰减
    """

    def __init__(self, max_entries: int = 1000, ttl_hours: int = 24):
        self.max_entries = max_entries
        self.ttl_hours = ttl_hours
        self._entries: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()
        self._agent_entries: Dict[str, Set[str]] = defaultdict(set)
        logger.info(f"Layer2 ShortTermMemory 初始化, max_entries={max_entries}, ttl={ttl_hours}h")

    def store(self, agent_id: str, content: str, memory_type: MemoryType,
              metadata: Dict[str, Any] = None) -> MemoryEntry:
        """存储到短期记忆"""
        with self._lock:
            entry = MemoryEntry(
                entry_id=f"stm_{uuid.uuid4().hex[:16]}",
                content=content,
                memory_type=memory_type,
                layer=MemoryLayer.SHORT_TERM,
                agent_id=agent_id,
                importance=0.6,
                metadata=metadata or {},
            )
            self._entries[entry.entry_id] = entry
            self._agent_entries[agent_id].add(entry.entry_id)

            # 容量管理
            if len(self._entries) > self.max_entries:
                self._evict_oldest()

            return entry

    def _evict_oldest(self):
        """淘汰最旧的条目"""
        if not self._entries:
            return
        oldest_entry = min(self._entries.values(), key=lambda e: e.created_at)
        self._remove_entry(oldest_entry.entry_id)

    def _remove_entry(self, entry_id: str):
        """移除条目"""
        entry = self._entries.pop(entry_id, None)
        if entry and entry.agent_id:
            self._agent_entries[entry.agent_id].discard(entry_id)

    def retrieve_for_agent(self, agent_id: str, limit: int = 20) -> List[MemoryEntry]:
        """获取Agent的最近记忆"""
        with self._lock:
            entry_ids = self._agent_entries.get(agent_id, set())
            entries = [self._entries[eid] for eid in entry_ids if eid in self._entries]
            entries.sort(key=lambda e: e.created_at, reverse=True)
            return entries[:limit]

    def retrieve_recent(self, hours: int = 24, limit: int = 50) -> List[MemoryEntry]:
        """获取最近N小时的记忆"""
        with self._lock:
            cutoff = datetime.now() - timedelta(hours=hours)
            recent = [e for e in self._entries.values() if e.created_at > cutoff]
            recent.sort(key=lambda e: e.created_at, reverse=True)
            return recent[:limit]

    def decay_old_entries(self):
        """衰减旧条目"""
        with self._lock:
            cutoff = datetime.now() - timedelta(hours=self.ttl_hours)
            to_remove = [
                entry_id for entry_id, entry in self._entries.items()
                if entry.created_at < cutoff
            ]
            for entry_id in to_remove:
                self._remove_entry(entry_id)
            if to_remove:
                logger.info(f"Layer2 衰减了 {len(to_remove)} 条过期记忆")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "max_entries": self.max_entries,
            "agent_count": len(self._agent_entries),
            "ttl_hours": self.ttl_hours,
        }


class Layer3LongTermMemory:
    """
    Layer 3: Long-Term Memory (长期记忆)
    存储持久知识，高重要性，带索引
    """

    def __init__(self, max_entries: int = 50000):
        self.max_entries = max_entries
        self._entries: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()
        self._index_by_type: Dict[MemoryType, Set[str]] = defaultdict(set)
        self._index_by_agent: Dict[str, Set[str]] = defaultdict(set)
        self._index_by_tag: Dict[str, Set[str]] = defaultdict(set)
        self._importance_index: List[str] = []  # 按重要性排序
        logger.info(f"Layer3 LongTermMemory 初始化, max_entries={max_entries}")

    def store(self, content: str, memory_type: MemoryType, agent_id: str = None,
              importance: float = 0.5, tags: Set[str] = None,
              metadata: Dict[str, Any] = None) -> MemoryEntry:
        """存储到长期记忆"""
        with self._lock:
            entry = MemoryEntry(
                entry_id=f"ltm_{uuid.uuid4().hex[:16]}",
                content=content,
                memory_type=memory_type,
                layer=MemoryLayer.LONG_TERM,
                agent_id=agent_id,
                importance=importance,
                tags=tags or set(),
                metadata=metadata or {},
            )
            self._entries[entry.entry_id] = entry

            # 更新索引
            self._index_by_type[memory_type].add(entry.entry_id)
            if agent_id:
                self._index_by_agent[agent_id].add(entry.entry_id)
            for tag in entry.tags:
                self._index_by_tag[tag].add(entry.entry_id)

            # 容量管理
            if len(self._entries) > self.max_entries:
                self._evict_low_importance()

            logger.debug(f"Layer3 存储长期记忆: {entry.entry_id}, importance={importance}")
            return entry

    def _evict_low_importance(self):
        """淘汰低重要性条目"""
        if not self._entries:
            return
        lowest = min(self._entries.values(), key=lambda e: e.importance)
        self._remove_entry(lowest.entry_id)

    def _remove_entry(self, entry_id: str):
        """移除条目及索引"""
        entry = self._entries.pop(entry_id, None)
        if not entry:
            return
        self._index_by_type[entry.memory_type].discard(entry_id)
        if entry.agent_id:
            self._index_by_agent[entry.agent_id].discard(entry_id)
        for tag in entry.tags:
            self._index_by_tag[tag].discard(entry_id)

    def retrieve_by_type(self, memory_type: MemoryType, limit: int = 50) -> List[MemoryEntry]:
        """按类型检索"""
        with self._lock:
            entry_ids = self._index_by_type.get(memory_type, set())
            entries = [self._entries[eid] for eid in entry_ids if eid in self._entries]
            entries.sort(key=lambda e: e.importance, reverse=True)
            return entries[:limit]

    def retrieve_by_agent(self, agent_id: str, limit: int = 50) -> List[MemoryEntry]:
        """按Agent检索"""
        with self._lock:
            entry_ids = self._index_by_agent.get(agent_id, set())
            entries = [self._entries[eid] for eid in entry_ids if eid in self._entries]
            entries.sort(key=lambda e: e.created_at, reverse=True)
            return entries[:limit]

    def retrieve_by_tags(self, tags: Set[str], limit: int = 50) -> List[MemoryEntry]:
        """按标签检索"""
        with self._lock:
            matching_ids = None
            for tag in tags:
                tag_ids = self._index_by_tag.get(tag, set())
                if matching_ids is None:
                    matching_ids = tag_ids.copy()
                else:
                    matching_ids &= tag_ids

            if not matching_ids:
                return []

            entries = [self._entries[eid] for eid in matching_ids if eid in self._entries]
            entries.sort(key=lambda e: e.importance, reverse=True)
            return entries[:limit]

    def search(self, query: str, limit: int = 20) -> List[MemoryEntry]:
        """文本搜索"""
        with self._lock:
            query_lower = query.lower()
            results = []
            for entry in self._entries.values():
                if query_lower in entry.content.lower():
                    results.append(entry)

            results.sort(key=lambda e: (e.importance, e.access_count), reverse=True)
            return results[:limit]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "max_entries": self.max_entries,
            "by_type": {t.value: len(ids) for t, ids in self._index_by_type.items()},
            "unique_tags": len(self._index_by_tag),
            "unique_agents": len(self._index_by_agent),
        }


class Layer4SemanticMemory:
    """
    Layer 4: Semantic Memory(语义记忆)
    知识图谱，存储实体和关系
    """

    def __init__(self):
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._relations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._entity_index: Dict[str, Set[str]] = defaultdict(set)  # tag -> entities
        self._lock = threading.RLock()
        logger.info("Layer4 SemanticMemory 初始化")

    def add_entity(self, entity_id: str, entity_type: str, properties: Dict[str, Any],
                   tags: Set[str] = None) -> Dict[str, Any]:
        """添加实体"""
        with self._lock:
            entity = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "properties": properties,
                "tags": tags or set(),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self._entities[entity_id] = entity

            for tag in entity["tags"]:
                self._entity_index[tag].add(entity_id)

            logger.debug(f"Layer4 添加实体: {entity_id} ({entity_type})")
            return entity

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                    properties: Dict[str, Any] = None) -> bool:
        """添加关系"""
        with self._lock:
            if source_id not in self._entities or target_id not in self._entities:
                return False

            relation = {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "properties": properties or {},
                "created_at": datetime.now().isoformat(),
            }
            self._relations[source_id].append(relation)
            logger.debug(f"Layer4 添加关系: {source_id} --[{relation_type}]--> {target_id}")
            return True

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取实体"""
        return self._entities.get(entity_id)

    def get_neighbors(self, entity_id: str, relation_type: str = None) -> List[Dict[str, Any]]:
        """获取关联实体"""
        with self._lock:
            neighbors = []
            for rel in self._relations.get(entity_id, []):
                if relation_type is None or rel["relation_type"] == relation_type:
                    target = self._entities.get(rel["target_id"])
                    if target:
                        neighbors.append({
                            "entity": target,
                            "relation": rel,
                        })
            return neighbors

    def find_path(self, source_id: str, target_id: str, max_depth: int = 3) -> List[List[str]]:
        """查找实体间的路径"""
        with self._lock:
            if source_id not in self._entities or target_id not in self._entities:
                return []

            paths = []
            visited = set()

            def dfs(current: str, path: List[str], depth: int):
                if depth > max_depth:
                    return
                if current == target_id:
                    paths.append(path.copy())
                    return

                for rel in self._relations.get(current, []):
                    next_id = rel["target_id"]
                    if next_id not in visited:
                        visited.add(next_id)
                        path.append(next_id)
                        dfs(next_id, path, depth + 1)
                        path.pop()
                        visited.remove(next_id)

            visited.add(source_id)
            dfs(source_id, [source_id], 0)
            return paths

    def search_entities(self, query: str, entity_type: str = None) -> List[Dict[str, Any]]:
        """搜索实体"""
        with self._lock:
            results = []
            query_lower = query.lower()

            for entity in self._entities.values():
                if entity_type and entity["entity_type"] != entity_type:
                    continue

                # 搜索名称和属性
                name = str(entity.get("properties", {}).get("name", "")).lower()
                if query_lower in name:
                    results.append(entity)
                    continue

                props_str = json.dumps(entity.get("properties", {}), ensure_ascii=False).lower()
                if query_lower in props_str:
                    results.append(entity)

            return results

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entities": len(self._entities),
            "total_relations": sum(len(r) for r in self._relations.values()),
            "entity_types": len(set(e["entity_type"] for e in self._entities.values())),
            "unique_tags": len(self._entity_index),
        }


class FourLayerMemorySystem:
    """
    四层记忆系统总控制器
    协调各层记忆，提供统一的记忆接口
    """

    def __init__(self, agent_id: str = "system"):
        self.agent_id = agent_id

        # 初始化四层记忆
        self.working_memory = Layer1WorkingMemory(max_entries=100)
        self.short_term_memory = Layer2ShortTermMemory(max_entries=1000, ttl_hours=24)
        self.long_term_memory = Layer3LongTermMemory(max_entries=50000)
        self.semantic_memory = Layer4SemanticMemory()

        # 统计
        self._stats = {
            "total_reads": 0,
            "total_writes": 0,
            "cache_hits": 0,
        }
        self._lock = threading.RLock()

        logger.info(f"FourLayerMemorySystem 初始化完成 (agent_id={agent_id})")

    def remember(self, content: str, memory_type: MemoryType = MemoryType.CONTEXT,
                 importance: float = 0.5, layer: MemoryLayer = None,
                 tags: Set[str] = None, metadata: Dict[str, Any] = None) -> MemoryEntry:
        """
        存储记忆 - 自动选择合适的层级
        """
        with self._lock:
            self._stats["total_writes"] += 1

            # 根据重要性自动选择层级
            if layer is None:
                if importance >= 0.7:
                    layer = MemoryLayer.LONG_TERM
                elif importance >= 0.4:
                    layer = MemoryLayer.SHORT_TERM
                else:
                    layer = MemoryLayer.WORKING

            if layer == MemoryLayer.WORKING:
                key = f"wm_{hashlib.md5(content.encode()).hexdigest()[:8]}"
                return self.working_memory.store(key, content, memory_type)

            elif layer == MemoryLayer.SHORT_TERM:
                return self.short_term_memory.store(
                    self.agent_id, content, memory_type, metadata
                )

            elif layer == MemoryLayer.LONG_TERM:
                return self.long_term_memory.store(
                    content, memory_type, self.agent_id, importance, tags, metadata
                )

            elif layer == MemoryLayer.SEMANTIC:
                # 语义记忆需要结构化数据
                entity_id = f"entity_{uuid.uuid4().hex[:8]}"
                self.semantic_memory.add_entity(
                    entity_id, memory_type.value,
                    {"content": content, **(metadata or {})},
                    tags
                )
                return MemoryEntry(
                    entry_id=entity_id,
                    content=content,
                    memory_type=memory_type,
                    layer=MemoryLayer.SEMANTIC,
                    tags=tags or set(),
                )

    def recall(self, query: str, layers: List[MemoryLayer] = None,
               limit: int = 10) -> MemoryRetrievalResult:
        """
        检索记忆 - 跨层搜索
        """
        start_time = time.time()
        with self._lock:
            self._stats["total_reads"] += 1

        layers = layers or [MemoryLayer.WORKING, MemoryLayer.SHORT_TERM, MemoryLayer.LONG_TERM]
        all_entries: List[Tuple[MemoryEntry, float]] = []

        # 各层检索
        if MemoryLayer.WORKING in layers:
            wm_entries = self.working_memory._entries.values()
            for entry in wm_entries:
                if query.lower() in entry.content.lower():
                    all_entries.append((entry, 0.9))  # 工作记忆高相关性

        if MemoryLayer.SHORT_TERM in layers:
            stm_entries = self.short_term_memory.retrieve_recent(hours=24, limit=100)
            for entry in stm_entries:
                if query.lower() in entry.content.lower():
                    all_entries.append((entry, 0.7))

        if MemoryLayer.LONG_TERM in layers:
            ltm_entries = self.long_term_memory.search(query, limit=50)
            for entry in ltm_entries:
                all_entries.append((entry, entry.importance))

        # 去重并排序
        seen_ids = set()
        unique_entries = []
        for entry, score in sorted(all_entries, key=lambda x: x[1], reverse=True):
            if entry.entry_id not in seen_ids:
                seen_ids.add(entry.entry_id)
                entry.relevance_score = score
                unique_entries.append(entry)

        retrieval_time = (time.time() - start_time) * 1000

        return MemoryRetrievalResult(
            entries=unique_entries[:limit],
            total_found=len(unique_entries),
            query=query,
            retrieval_time_ms=retrieval_time,
        )

    def get_context_for_task(self, task_id: str) -> Dict[str, Any]:
        """获取任务完整上下文"""
        return {
            "task_context": self.working_memory.get_task_context(task_id) or {},
            "recent_memories": [
                e.to_dict() for e in self.short_term_memory.retrieve_recent(hours=2, limit=10)
            ],
            "relevant_knowledge": [
                e.to_dict() for e in self.long_term_memory.search(task_id, limit=5)
            ],
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计"""
        return {
            "agent_id": self.agent_id,
            "working_memory": {
                "entries": len(self.working_memory._entries),
                "max": self.working_memory.max_entries,
            },
            "short_term_memory": self.short_term_memory.get_stats(),
            "long_term_memory": self.long_term_memory.get_stats(),
            "semantic_memory": self.semantic_memory.get_stats(),
            "system": self._stats.copy(),
        }

    async def maintenance(self):
        """维护任务 - 衰减、清理"""
        self.short_term_memory.decay_old_entries()
        logger.info("记忆系统维护完成")


# 全局记忆管理器
_global_memory_managers: Dict[str, FourLayerMemorySystem] = {}
_memory_lock = threading.RLock()


def get_agent_memory(agent_id: str) -> FourLayerMemorySystem:
    """获取Agent的记忆系统"""
    with _memory_lock:
        if agent_id not in _global_memory_managers:
            _global_memory_managers[agent_id] = FourLayerMemorySystem(agent_id)
        return _global_memory_managers[agent_id]


def get_system_memory() -> FourLayerMemorySystem:
    """获取系统级记忆"""
    return get_agent_memory("system")


__all__ = [
    "FourLayerMemorySystem",
    "Layer1WorkingMemory",
    "Layer2ShortTermMemory",
    "Layer3LongTermMemory",
    "Layer4SemanticMemory",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryRetrievalResult",
    "MemoryLayer",
    "MemoryType",
    "get_agent_memory",
    "get_system_memory",
]
