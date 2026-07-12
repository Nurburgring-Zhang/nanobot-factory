"""智影 V5 — Memory 3 层文件分层 (raw / sources / 长期记忆)"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MemoryLayer(str, Enum):
    """记忆分层 — 信任等级从高到低"""
    RAW = "raw"            # 原始证据 (永不删除, 结构上拒绝写入)
    SOURCE = "source"      # Agent 为原件生成的影子 MD (可重做)
    INBOX = "inbox"        # 待审核的沉淀 (自由写)
    FEEDBACK = "feedback"  # 👍/👎 反馈 (自由写)
    LONG_TERM = "long_term"  # 长期记忆 (写入需确认)
    PROFILE = "profile"    # 我是谁 (写入需确认)


class TrustLevel(str, Enum):
    """信任等级 — 跟 MemoryLayer 一一对应"""
    ABSOLUTE = "absolute"   # 原始证据
    DERIVED = "derived"     # 抽取结果
    PENDING = "pending"     # 待确认
    CONFIRMED = "confirmed"  # 已确认


LAYER_TRUST: Dict[MemoryLayer, TrustLevel] = {
    MemoryLayer.RAW: TrustLevel.ABSOLUTE,
    MemoryLayer.SOURCE: TrustLevel.DERIVED,
    MemoryLayer.INBOX: TrustLevel.PENDING,
    MemoryLayer.FEEDBACK: TrustLevel.PENDING,
    MemoryLayer.LONG_TERM: TrustLevel.CONFIRMED,
    MemoryLayer.PROFILE: TrustLevel.CONFIRMED,
}


@dataclass
class MemoryItem:
    """记忆项 — 跨层统一"""
    item_id: str = field(default_factory=lambda: f"mi-{uuid.uuid4().hex[:12]}")
    layer: MemoryLayer = MemoryLayer.INBOX
    title: str = ""
    content: str = ""
    content_hash: str = ""

    # 元数据
    source: str = ""  # 来源 (URL/文件/线程/...)
    source_type: str = "text"  # text/image/pdf/...
    created_at: float = 0.0
    updated_at: float = 0.0

    # 关联
    raw_id: str = ""           # 关联的 raw item
    source_ids: List[str] = field(default_factory=list)  # 关联的 sources
    thread_id: str = ""
    matter_id: str = ""
    project_id: str = ""
    people_ids: List[str] = field(default_factory=list)

    # 标签
    tags: List[str] = field(default_factory=list)
    category: str = ""
    domain: str = ""

    # 状态
    status: str = "active"  # active/archived/deleted
    confirmed: bool = False
    confirmed_by: str = ""
    confirmed_at: float = 0.0

    # Embedding (cross-modal retrieval)
    embedding: Optional[List[float]] = None
    embedding_model: str = ""

    # 统计
    view_count: int = 0
    use_count: int = 0
    last_used: float = 0.0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def trust(self) -> TrustLevel:
        return LAYER_TRUST.get(self.layer, TrustLevel.PENDING)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "layer": self.layer.value,
            "trust": self.trust.value,
            "title": self.title,
            "content": self.content[:500] + "..." if len(self.content) > 500 else self.content,
            "content_hash": self.content_hash,
            "source": self.source,
            "source_type": self.source_type,
            "tags": self.tags,
            "category": self.category,
            "domain": self.domain,
            "status": self.status,
            "confirmed": self.confirmed,
            "confirmed_by": self.confirmed_by,
            "raw_id": self.raw_id,
            "source_ids": self.source_ids,
            "thread_id": self.thread_id,
            "matter_id": self.matter_id,
            "project_id": self.project_id,
            "people_ids": self.people_ids,
            "view_count": self.view_count,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used": self.last_used,
        }


@dataclass
class MemoryQuery:
    """记忆查询"""
    query: str
    layers: Optional[List[MemoryLayer]] = None  # None = all
    tags: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    project_id: str = ""
    confirmed_only: bool = False
    min_trust: TrustLevel = TrustLevel.PENDING
    top_k: int = 10
    since_ts: float = 0.0
    until_ts: float = 0.0


class _BaseStore:
    """层基类 — 提供基础的增删改查"""

    def __init__(self, layer: MemoryLayer, base_path: str = ""):
        self.layer = layer
        self.base_path = base_path or f"D:/Hermes/生产平台/nanobot-factory/backend/data/memory_v5/{layer.value}"
        self._items: Dict[str, MemoryItem] = {}
        self._lock = False
        # 加载
        self._load_from_disk()

    def _load_from_disk(self):
        os.makedirs(self.base_path, exist_ok=True)
        # 简化:不强制加载旧文件,运行时写入

    def add(self, item: MemoryItem) -> str:
        if item.layer != self.layer:
            raise ValueError(f"layer mismatch: {item.layer} != {self.layer}")
        if not item.created_at:
            item.created_at = time.time()
        item.updated_at = time.time()
        self._items[item.item_id] = item
        return item.item_id

    def get(self, item_id: str) -> Optional[MemoryItem]:
        item = self._items.get(item_id)
        if item:
            item.view_count += 1
        return item

    def list(
        self,
        limit: int = 100,
        tags: Optional[List[str]] = None,
        domain: Optional[str] = None,
        project_id: Optional[str] = None,
        confirmed_only: bool = False,
    ) -> List[MemoryItem]:
        items = list(self._items.values())
        if tags:
            items = [i for i in items if any(t in i.tags for t in tags)]
        if domain:
            items = [i for i in items if i.domain == domain]
        if project_id:
            items = [i for i in items if i.project_id == project_id]
        if confirmed_only:
            items = [i for i in items if i.confirmed]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:limit]

    def delete(self, item_id: str) -> bool:
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def count(self) -> int:
        return len(self._items)

    def all_items(self) -> List[MemoryItem]:
        return list(self._items.values())


class RawStore(_BaseStore):
    """原始证据层 — 永不删除, 结构上拒绝覆盖"""

    def add(self, item: MemoryItem) -> str:
        if item.layer != MemoryLayer.RAW:
            item.layer = MemoryLayer.RAW
        # raw 永不覆盖 — 同 content_hash 直接返回旧 id
        existing = next(
            (i for i in self._items.values() if i.content_hash == item.content_hash),
            None,
        )
        if existing:
            return existing.item_id
        return super().add(item)

    def update(self, item_id: str, **kwargs) -> bool:
        """raw 不允许更新 — 抛出"""
        raise PermissionError("raw 原始证据层禁止更新 (信任等级 ABSOLUTE)")


class SourceStore(_BaseStore):
    """影子 MD 层 — 可重做 (raw 还在)"""

    def regenerate(self, raw_id: str, new_content: str) -> Optional[MemoryItem]:
        """基于 raw 重新生成"""
        for item in self._items.values():
            if item.raw_id == raw_id:
                old_id = item.item_id
                self._items.pop(old_id)
                new_item = MemoryItem(
                    item_id=old_id,
                    layer=MemoryLayer.SOURCE,
                    title=item.title,
                    content=new_content,
                    raw_id=raw_id,
                    source_ids=item.source_ids,
                    thread_id=item.thread_id,
                    project_id=item.project_id,
                    people_ids=item.people_ids,
                    tags=item.tags,
                    domain=item.domain,
                )
                self._items[old_id] = new_item
                return new_item
        return None


class InboxStore(_BaseStore):
    """收件箱 — 待审核"""

    def confirm(self, item_id: str, by: str = "") -> bool:
        item = self._items.get(item_id)
        if not item:
            return False
        item.confirmed = True
        item.confirmed_by = by
        item.confirmed_at = time.time()
        item.updated_at = time.time()
        return True


class FeedbackStore(_BaseStore):
    """反馈层 — 👍/👎"""

    def add_feedback(
        self,
        target_id: str,
        feedback_type: str,  # "approve" | "reject" | "edit" | "select" | "prefer"
        source_id: str = "",
        comment: str = "",
        delta: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        item = MemoryItem(
            layer=MemoryLayer.FEEDBACK,
            title=f"{feedback_type} {target_id}",
            content=comment,
            source=source_id,
            tags=[feedback_type, f"target:{target_id}"],
            metadata={
                "target_id": target_id,
                "feedback_type": feedback_type,
                "delta": delta or {},
            },
        )
        self.add(item)
        return item


class LongTermStore(_BaseStore):
    """长期记忆 — 写入需确认"""

    def add(self, item: MemoryItem) -> str:
        if item.layer != MemoryLayer.LONG_TERM:
            item.layer = MemoryLayer.LONG_TERM
        # 长期记忆必须确认
        if not item.confirmed:
            item.confirmed = True
            item.confirmed_at = time.time()
        return super().add(item)


class MemoryManager:
    """记忆管理 — 跨层统一查询 + 文件持久化"""

    def __init__(self, base_path: str = ""):
        self.raw = RawStore(MemoryLayer.RAW, base_path)
        self.source = SourceStore(MemoryLayer.SOURCE, base_path)
        self.inbox = InboxStore(MemoryLayer.INBOX, base_path)
        self.feedback = FeedbackStore(MemoryLayer.FEEDBACK, base_path)
        self.long_term = LongTermStore(MemoryLayer.LONG_TERM, base_path)
        self.stores: Dict[MemoryLayer, _BaseStore] = {
            MemoryLayer.RAW: self.raw,
            MemoryLayer.SOURCE: self.source,
            MemoryLayer.INBOX: self.inbox,
            MemoryLayer.FEEDBACK: self.feedback,
            MemoryLayer.LONG_TERM: self.long_term,
        }
        # profile 特殊:用 long_term 存
        self.profile = self.long_term

    def add_raw(
        self,
        title: str,
        content: str,
        source: str = "",
        source_type: str = "text",
        file_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """添加原始证据 (永不丢失)"""
        item = MemoryItem(
            layer=MemoryLayer.RAW,
            title=title,
            content=content,
            source=source,
            source_type=source_type,
            metadata=metadata or {},
        )
        if file_path:
            item.metadata["file_path"] = file_path
        self.raw.add(item)
        return item

    def add_source(
        self,
        raw_id: str,
        title: str,
        content: str,
        **kwargs,
    ) -> MemoryItem:
        """基于 raw 添加影子"""
        item = MemoryItem(
            layer=MemoryLayer.SOURCE,
            title=title,
            content=content,
            raw_id=raw_id,
            **kwargs,
        )
        self.source.add(item)
        return item

    def add_inbox(
        self,
        title: str,
        content: str,
        thread_id: str = "",
        project_id: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> MemoryItem:
        item = MemoryItem(
            layer=MemoryLayer.INBOX,
            title=title,
            content=content,
            thread_id=thread_id,
            project_id=project_id,
            tags=tags or [],
            **kwargs,
        )
        self.inbox.add(item)
        return item

    def promote_to_long_term(
        self,
        inbox_id: str,
        by: str = "",
    ) -> Optional[MemoryItem]:
        """确认 inbox → 长期记忆"""
        item = self.inbox.get(inbox_id)
        if not item:
            return None
        item.confirmed = True
        item.confirmed_by = by
        item.confirmed_at = time.time()
        # 复制到 long_term
        long_item = MemoryItem(
            item_id=item.item_id,  # 保持相同 id 便于追踪
            layer=MemoryLayer.LONG_TERM,
            title=item.title,
            content=item.content,
            source=item.source,
            source_type=item.source_type,
            raw_id=item.raw_id,
            source_ids=item.source_ids,
            thread_id=item.thread_id,
            matter_id=item.matter_id,
            project_id=item.project_id,
            people_ids=item.people_ids,
            tags=item.tags,
            domain=item.domain,
            confirmed=True,
            confirmed_by=by,
            confirmed_at=item.confirmed_at,
            metadata=item.metadata,
        )
        self.long_term.add(long_item)
        return long_item

    def query(self, q: MemoryQuery) -> List[MemoryItem]:
        """跨层查询 — 按 trust 排序"""
        layers = q.layers or [MemoryLayer.RAW, MemoryLayer.SOURCE, MemoryLayer.INBOX, MemoryLayer.FEEDBACK, MemoryLayer.LONG_TERM]
        results: List[MemoryItem] = []
        for layer in layers:
            store = self.stores.get(layer)
            if not store:
                continue
            items = store.list(
                limit=q.top_k * 2,
                tags=q.tags,
                domain=q.domains[0] if q.domains else None,
                project_id=q.project_id,
                confirmed_only=q.confirmed_only,
            )
            for item in items:
                # 过滤时间
                if q.since_ts and item.created_at < q.since_ts:
                    continue
                if q.until_ts and item.created_at > q.until_ts:
                    continue
                # 关键词匹配 (简单)
                if q.query:
                    q_lower = q.query.lower()
                    if q_lower not in (item.title + " " + item.content).lower():
                        # 尝试 token
                        tokens = re.findall(r"\w+", q_lower)
                        if not any(t in (item.title + " " + item.content).lower() for t in tokens if len(t) > 2):
                            continue
                # 信任过滤
                if LAYER_TRUST[item.layer].value < q.min_trust.value:
                    continue
                results.append(item)
        # 按 trust + 时间排序
        results.sort(key=lambda x: (LAYER_TRUST[x.layer].value, x.created_at), reverse=True)
        return results[: q.top_k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "raw": self.raw.count(),
            "source": self.source.count(),
            "inbox": self.inbox.count(),
            "inbox_pending": sum(1 for i in self.inbox.all_items() if not i.confirmed),
            "feedback": self.feedback.count(),
            "long_term": self.long_term.count(),
            "total": self.raw.count() + self.source.count() + self.inbox.count() + self.feedback.count() + self.long_term.count(),
        }

    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "raw": [i.to_dict() for i in self.raw.all_items()],
            "source": [i.to_dict() for i in self.source.all_items()],
            "inbox": [i.to_dict() for i in self.inbox.all_items()],
            "feedback": [i.to_dict() for i in self.feedback.all_items()],
            "long_term": [i.to_dict() for i in self.long_term.all_items()],
        }


memory_manager = MemoryManager()


# 默认 Store 实例 (供 feedback / palce 等模块直接使用)
raw_store_default = memory_manager.raw
source_store_default = memory_manager.source
inbox_store_default = memory_manager.inbox
feedback_store_default = memory_manager.feedback
long_term_store_default = memory_manager.long_term
