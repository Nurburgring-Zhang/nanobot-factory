"""
R7-W1: Cache Layer (api/_common/cache.py)
=========================================

内存优先 LRU 缓存 + 可选 Redis 后端 + post-mutate 失效钩子。

设计目标:
  1. 默认走本地 LRU (有序 dict 实现, O(1) get/set), 进程内可见
  2. 如果环境变量 IMDF_CACHE_REDIS_URL 配置了 Redis, 则优先用 Redis
  3. 列表类端点 5 分钟 TTL, 详情类 1 分钟 TTL, 写操作触发失效
  4. 与 metrics 模块打通: hit/miss/set/delete 全部上报

用法:
    from api._common.cache import (
        cached, list_cache, detail_cache,
        invalidate_prefix, invalidate_key,
        get_cache_stats,
    )

    # 装饰器用法 (推荐)
    @router.get("/api/v1/projects")
    @list_cache(ttl=300, key_prefix="projects:list")
    async def list_projects(...):
        ...

    # 直接调用
    data = list_cache.get_or_set("projects:list:page=1", lambda: query_db(), ttl=300)

    # 写后失效
    @router.post("/api/v1/projects")
    async def create_project(...):
        ...
        invalidate_prefix("projects:")
"""

from __future__ import annotations

import os
import time
import json
import hashlib
import threading
import logging
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("imdf.cache")


# ═══════════════════════════════════════════════════════════════════════════
# 默认 TTL 配置
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_LIST_TTL = int(os.environ.get("IMDF_CACHE_LIST_TTL", "300"))     # 5 min
DEFAULT_DETAIL_TTL = int(os.environ.get("IMDF_CACHE_DETAIL_TTL", "60"))  # 1 min
DEFAULT_MAX_ENTRIES = int(os.environ.get("IMDF_CACHE_MAX_ENTRIES", "5000"))


T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════════════
# 内存 LRU 缓存 (OrderedDict 实现)
# ═══════════════════════════════════════════════════════════════════════════

class LRUCache:
    """线程安全的内存 LRU 缓存。

    实现细节:
      - 用 OrderedDict 维护访问顺序
      - get() 时把 key 移到末尾 (most-recently-used)
      - set() 时若超出容量, 从头部弹出最久未使用项
    """

    def __init__(self, name: str = "default", max_entries: int = DEFAULT_MAX_ENTRIES):
        self.name = name
        self.max_entries = max(1, max_entries)
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        # 统计
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.evictions = 0

    # ── 核心操作 ──────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._miss()
                return None
            expire_at, value = entry
            if expire_at > 0 and expire_at < time.time():
                # 过期 → 删除
                del self._data[key]
                self._miss()
                return None
            # LRU: 移到末尾
            self._data.move_to_end(key)
            self._hit()
            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        if ttl_seconds < 0:
            ttl_seconds = 0
        expire_at = (time.time() + ttl_seconds) if ttl_seconds > 0 else 0
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (expire_at, value)
            self.sets += 1
            # 容量控制
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
                self.evictions += 1

    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._data
            if existed:
                del self._data[key]
                self.deletes += 1
            return existed

    def clear(self) -> int:
        with self._lock:
            n = len(self._data)
            self._data.clear()
            return n

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys_to_del = [k for k in self._data if k.startswith(prefix)]
            for k in keys_to_del:
                del self._data[k]
                self.deletes += 1
            return len(keys_to_del)

    # ── 复合 API ──────────────────────────────────────────────────────────

    def get_or_set(self, key: str, factory: Callable[[], T],
                   ttl_seconds: int = 0) -> T:
        """先读; 失效或缺失时调用 factory 回填。"""
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value
        value = factory()
        if value is not None:
            self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    # ── 统计 ──────────────────────────────────────────────────────────────

    def _hit(self) -> None:
        self.hits += 1
        try:
            from api._common.metrics import cache_hit
            cache_hit(self.name)
        except Exception:
            pass

    def _miss(self) -> None:
        self.misses += 1
        try:
            from api._common.metrics import cache_miss
            cache_miss(self.name)
        except Exception:
            pass

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "name": self.name,
                "size": len(self._data),
                "max_entries": self.max_entries,
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "deletes": self.deletes,
                "evictions": self.evictions,
                "hit_ratio": round(self.hits / total, 4) if total else 0.0,
            }


# ═══════════════════════════════════════════════════════════════════════════
# Redis 后端 (可选)
# ═══════════════════════════════════════════════════════════════════════════

class _RedisBackend:
    """Redis 后端封装, 仅在 REDIS_URL 配置时启用。"""

    def __init__(self, url: str):
        self.url = url
        self._client = None
        self._init_failed = False
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0

    def _ensure_client(self):
        if self._client is not None or self._init_failed:
            return
        try:
            import redis  # type: ignore
            self._client = redis.Redis.from_url(
                self.url, decode_responses=False,
                socket_connect_timeout=1.0, socket_timeout=1.0,
            )
            self._client.ping()
            logger.info("redis_cache_connected", url=self.url)
        except Exception as exc:
            self._init_failed = True
            logger.warning("redis_cache_init_failed", url=self.url, error=str(exc))
            self._client = None

    def get(self, key: str) -> Optional[Any]:
        self._ensure_client()
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        self._ensure_client()
        if self._client is None:
            return
        try:
            payload = json.dumps(value, default=str).encode("utf-8")
            if ttl_seconds > 0:
                self._client.setex(key, ttl_seconds, payload)
            else:
                self._client.set(key, payload)
            self.sets += 1
        except Exception:
            pass

    def delete(self, key: str) -> bool:
        self._ensure_client()
        if self._client is None:
            return False
        try:
            n = self._client.delete(key)
            self.deletes += 1
            return bool(n)
        except Exception:
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        self._ensure_client()
        if self._client is None:
            return 0
        try:
            keys = list(self._client.scan_iter(match=f"{prefix}*"))
            if keys:
                self._client.delete(*keys)
                self.deletes += len(keys)
            return len(keys)
        except Exception:
            return 0

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "name": "redis",
            "connected": self._client is not None,
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "hit_ratio": round(self.hits / total, 4) if total else 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 统一前端: list_cache / detail_cache
# ═══════════════════════════════════════════════════════════════════════════

_memory_cache = LRUCache(name="memory", max_entries=DEFAULT_MAX_ENTRIES)
_redis_cache: Optional[_RedisBackend] = None

# 懒初始化 Redis 后端
_redis_url = os.environ.get("IMDF_CACHE_REDIS_URL", "").strip()
if _redis_url:
    _redis_cache = _RedisBackend(_redis_url)


def _backend():
    """优先 Redis, 失败回退到内存 LRU。"""
    if _redis_cache is not None:
        try:
            return _redis_cache
        except Exception:
            pass
    return _memory_cache


# ── 公开 API ──────────────────────────────────────────────────────────────

def get(key: str) -> Optional[Any]:
    return _backend().get(key)


def set(key: str, value: Any, ttl_seconds: int = 0) -> None:
    _backend().set(key, value, ttl_seconds=ttl_seconds)


def delete(key: str) -> bool:
    return _backend().delete(key)


def invalidate_prefix(prefix: str) -> int:
    """失效所有以 prefix 开头的 key (用于写后批量失效)。"""
    n = _backend().invalidate_prefix(prefix)
    # 同时清内存缓存 (避免 Redis 与本地不一致)
    n += _memory_cache.invalidate_prefix(prefix)
    return n


def invalidate_key(key: str) -> bool:
    """失效单个 key。"""
    deleted = _backend().delete(key)
    deleted = _memory_cache.delete(key) or deleted
    return deleted


def get_or_set(key: str, factory: Callable[[], T],
               ttl_seconds: int = DEFAULT_LIST_TTL) -> T:
    """高层 API: 读穿透模式。"""
    return _backend().get_or_set(key, factory, ttl_seconds=ttl_seconds)


# ── 装饰器 ────────────────────────────────────────────────────────────────

def list_cache(key_prefix: str, ttl: int = DEFAULT_LIST_TTL,
               key_builder: Optional[Callable[..., str]] = None):
    """列表类端点缓存装饰器 (默认 5min TTL)。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            builder = key_builder or _default_key_builder
            cache_key = builder(key_prefix, args, kwargs)
            # 读缓存
            hit = get(cache_key)
            if hit is not None:
                return hit
            # 未命中 → 执行原函数
            result = await func(*args, **kwargs)
            if result is not None:
                set(cache_key, result, ttl_seconds=ttl)
            return result
        return wrapper
    return decorator


def detail_cache(key_prefix: str, ttl: int = DEFAULT_DETAIL_TTL,
                 key_builder: Optional[Callable[..., str]] = None):
    """详情类端点缓存装饰器 (默认 1min TTL)。"""
    return list_cache(key_prefix=key_prefix, ttl=ttl, key_builder=key_builder)


def _default_key_builder(prefix: str, args: tuple, kwargs: dict) -> str:
    """默认 cache key 生成器: 用参数生成稳定 hash。"""
    parts = [prefix]
    for arg in args:
        parts.append(str(arg))
    for k in sorted(kwargs.keys()):
        if k in ("self", "cls"):
            continue
        parts.append(f"{k}={kwargs[k]}")
    raw = "|".join(parts)
    if len(raw) > 256:
        h = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return f"{prefix}:hash:{h}"
    return raw


# ── post-mutate hook ──────────────────────────────────────────────────────

def post_mutate_invalidate(*prefixes: str) -> Callable:
    """写后失效装饰器工厂。

    用法:
        @router.post("/api/v1/projects")
        @post_mutate_invalidate("projects:list", "projects:detail")
        async def create_project(...):
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            for prefix in prefixes:
                try:
                    invalidate_prefix(prefix)
                except Exception:
                    logger.debug("post_mutate_invalidate_failed", prefix=prefix,
                                 exc_info=True)
            return result
        return wrapper
    return decorator


# ── 统计聚合 ──────────────────────────────────────────────────────────────

def get_cache_stats() -> dict:
    """返回所有缓存后端的统计快照。"""
    mem = _memory_cache.stats()
    out: dict = {"memory": mem}
    if _redis_cache is not None:
        out["redis"] = _redis_cache.stats()
    out["backend"] = "redis" if (_redis_cache and _redis_cache._client) else "memory"
    return out


__all__ = [
    "LRUCache",
    "list_cache",
    "detail_cache",
    "post_mutate_invalidate",
    "get_or_set",
    "get",
    "set",
    "delete",
    "invalidate_prefix",
    "invalidate_key",
    "get_cache_stats",
    "DEFAULT_LIST_TTL",
    "DEFAULT_DETAIL_TTL",
]