"""智影 V5 — Performance Tuning: 上下文压缩 + 提示缓存 (Hermes 10s → 1s 案例)"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CompressionStrategy(str, Enum):
    """压缩策略 — Hermes context_compressor"""
    PROTECT_BOUNDS = "protect_bounds"      # 保护头部+尾部, 压缩中间
    SUMMARIZE_OLD = "summarize_old"        # 摘要老消息
    SLIDING_WINDOW = "sliding_window"      # 滑动窗口
    IMPORTANCE = "importance"              # 按重要性保留


@dataclass
class CompressionResult:
    """压缩结果"""

    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    kept_messages: int
    summarized_messages: int
    dropped_messages: int
    strategy: CompressionStrategy
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheEntry:
    """缓存项"""

    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0
    size_bytes: int = 0
    ttl_seconds: float = 0.0

    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def access(self):
        self.last_accessed = time.time()
        self.access_count += 1


class PromptCache:
    """Prompt 缓存 — 缓存 system prompt + 工具描述"""

    def __init__(self, max_size: int = 1000, default_ttl: float = 3600.0):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            self.misses += 1
            return None
        entry = self._cache[key]
        if entry.is_expired():
            del self._cache[key]
            self.misses += 1
            return None
        entry.access()
        # LRU: 移到末尾
        self._cache.move_to_end(key)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: Any, ttl: Optional[float] = None):
        # 大小限制
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # LRU 淘汰
            self.evictions += 1
        size = len(json.dumps(value, default=str)) if not isinstance(value, (bytes, str)) else len(value)
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            last_accessed=time.time(),
            size_bytes=size,
            ttl_seconds=ttl or self.default_ttl,
        )
        self._cache[key] = entry

    def get_or_compute(self, key: str, compute_fn, ttl: Optional[float] = None) -> Any:
        v = self.get(key)
        if v is not None:
            return v
        v = compute_fn()
        self.put(key, v, ttl)
        return v

    def invalidate(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self):
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "size": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / max(total, 1), 3),
            "evictions": self.evictions,
            "total_access": total,
        }


class ContextCompressor:
    """上下文压缩器 — Hermes agent/context_compressor.py

    保护头部和尾部, 压缩中间。保留前 N 轮 + 后 M 轮,
    中间内容超阈值时自动摘要, 显著降低 token 处理量。
    """

    def __init__(
        self,
        protect_head: int = 3,
        protect_tail: int = 4,
        threshold_ratio: float = 0.85,  # 85% 触发压缩
        max_context_tokens: int = 1_000_000,
    ):
        self.protect_head = protect_head
        self.protect_tail = protect_tail
        self.threshold_ratio = threshold_ratio
        self.max_context_tokens = max_context_tokens

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算 token 数 — 简化: 1 token ≈ 4 chars (英文), ≈ 1.5 chars (中文)"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            total += len(content) // 3  # 保守估计
        return total

    def compress(
        self,
        messages: List[Dict[str, Any]],
        summarizer: Optional[Any] = None,
    ) -> Tuple[List[Dict[str, Any]], CompressionResult]:
        """压缩消息列表"""
        start = time.time()
        original_tokens = self.estimate_tokens(messages)
        # 触发判断
        if original_tokens < self.max_context_tokens * self.threshold_ratio:
            return messages, CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                kept_messages=len(messages),
                summarized_messages=0,
                dropped_messages=0,
                strategy=CompressionStrategy.PROTECT_BOUNDS,
                duration_ms=(time.time() - start) * 1000,
                metadata={"skipped": "below threshold"},
            )
        # 保护头尾
        head = messages[: self.protect_head]
        tail = messages[-self.protect_tail:] if self.protect_tail > 0 else []
        middle = messages[self.protect_head : len(messages) - self.protect_tail] if self.protect_tail > 0 else messages[self.protect_head:]
        # 摘要中间
        if summarizer:
            middle_summarized = summarizer(middle)
        else:
            middle_summarized = self._default_summarize(middle)
        # 构造结果
        result = head + [{"role": "system", "content": f"[Summary of {len(middle)} earlier messages]: {middle_summarized}"}] + tail
        compressed_tokens = self.estimate_tokens(result)
        return result, CompressionResult(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=round(compressed_tokens / max(original_tokens, 1), 3),
            kept_messages=len(head) + len(tail),
            summarized_messages=len(middle),
            dropped_messages=0,
            strategy=CompressionStrategy.PROTECT_BOUNDS,
            duration_ms=(time.time() - start) * 1000,
        )

    def _default_summarize(self, messages: List[Dict[str, Any]]) -> str:
        """默认摘要 — 提取关键信息"""
        roles: Dict[str, int] = {}
        topics: List[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
            content = str(msg.get("content", ""))[:200]
            topics.append(content[:100])
        return f"包含 {len(messages)} 条消息, 角色分布: {roles}, 关键内容摘要: {' | '.join(topics[:5])}"


# 全局实例
prompt_cache = PromptCache()
context_compressor = ContextCompressor()
