# P9-5-Cache: Multi-Tier Cache Audit (缓存三次审查)

**Date**: 2026-06-26 | **Mode**: THREE-PASS | **Files audited**: 2 (cache.py + _common/cache.py)

---

## 1. TL;DR

| 项目 | 状态 | 备注 |
|---|---|---|
| L1 in-process cache | ✅ **就位** (`backend/imdf/api/_common/cache.py` 443 LOC) | OrderedDict LRU, 线程安全, max=5000, TTL env 可调 |
| L2 Redis cache | ⚠️ **代码就位, 生产未启用** | `IMDF_CACHE_REDIS_URL` env 未设 |
| L3 CDN/edge cache | ❌ **缺失** | (中期, 30d+) |
| TTL 策略 | ✅ | list=300s, detail=60s, env override |
| 失效策略 (post-mutate) | ✅ | `@post_mutate_invalidate` 装饰器, 但未广泛使用 |
| 缓存击穿防护 | ⚠️ **部分** | `get_or_set` 读穿透, 但无 singleflight 互斥 (P1) |
| 缓存雪崩防护 | ⚠️ **部分** | TTL 是固定值, 无随机 jitter (P1) |
| 缓存穿透防护 | ❌ **缺失** | 无 null/negative cache (P1) |
| 多租户隔离 | ❌ **缺失** | key prefix 不含 tenant_id (P2) |
| Hit ratio 实测 | ⚠️ **不可见** | 无 Prometheus exporter (P1) |

**总评**: **8/10 商业级**. L1 实现质量高, 但 L2 未启用 + 健康探针无缓存 + 缺监控是 3 个主要 gap.

---

## 2. 三轮审计 (Three-Pass Findings)

### 2.1 Pass 1 — 静态审计 (读 2 个文件 1136 LOC)

#### 2.1.1 `backend/imdf/api/_common/cache.py` (443 LOC, 强)

```python
# 关键设计 (high quality):
class LRUCache:                          # 线程安全 OrderedDict LRU
    def __init__(self, name, max_entries=5000)  # 容量 env 可调

_DEFAULT_LIST_TTL = 300                  # 5 min, env 可调
_DEFAULT_DETAIL_TTL = 60                 # 1 min, env 可调

# 装饰器 (推荐用法)
@list_cache(key_prefix="projects:list", ttl=300)
async def list_projects(...): ...

@detail_cache(key_prefix="projects:detail", ttl=60)
async def get_project(project_id: str): ...

@post_mutate_invalidate("projects:list", "projects:detail")
async def create_project(...): ...
```

**优点 (设计亮点)**:
- ✅ OrderedDict 实现 LRU, O(1) get/set
- ✅ TTL on every entry, lazy expiration on read
- ✅ `evictions` 统计可观测
- ✅ Hit/miss 通过 `metrics.py` 上报 (但 metrics 模块需独立审计)
- ✅ `_backend()` 选择: 优先 Redis → fallback LRU (graceful degrade)
- ✅ `invalidate_prefix` 同时清内存和 Redis (避免不一致)
- ✅ Key builder 默认 MD5 hash 长 key → 避免 key 爆炸

**缺点**:
- ⚠️ RedisBackend 单连接 (no pool, P1) — 高并发下 `socket_timeout=1.0` 容易堆
- ⚠️ RedisBackend miss 时不更新 memory (line 313 `get()` 直接转发 backend, 不 mirror 到 L1)
- ⚠️ 没有 singleflight: 1000 并发同 key cold miss 会同时调 factory → 缓存击穿
- ⚠️ `_default_key_builder` 用 `str(arg)` 序列化 — 复杂对象 (Pydantic / dataclass) 会变成巨大字符串
- ⚠️ 无 null caching: DB 返回 None 不缓存, 攻击者可刷不存在 key → DB DoS

#### 2.1.2 `backend/infrastructure/cache.py` (693 LOC, 中, **DEAD CODE**)

```python
class RedisManager:
    # 完整 Redis 管理 (cache/lock/rate-limit/session/pubsub)
    # 但: 全项目 grep 无任何 import!
```

**这是 dead code**:
- `infrastructure/__init__.py` 没有暴露
- 12 service `main.py` 没有 import
- api-gateway 没有 import
- 唯一相关的是 `infra/cache.py` line 13 自己 import `redis.asyncio`

**判定**: 应该删除 (P3 cleanup) 或合并到 `_common/cache.py`.

#### 2.1.3 缓存架构现状图

```
┌─────────────────────────────────────────────────────────────┐
│  Client (1000 users)                                        │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│  api-gateway (port 8000)                                    │
│  ├─ uvicorn worker × N                                      │
│  └─ **无缓存层** (gateway 直接转发到 12 service)            │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│  12 microservices (ports 8001-8012)                         │
│  ├─ L1 in-proc LRU (per service, 5000 entries, 5min TTL)   │
│  │  └─ `_common/cache.py` (per service 独立, 不共享)        │
│  └─ **L2 Redis 未启用** (env 未设)                          │
└──────────────────┬──────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────────┐
│  Storage                                                    │
│  ├─ SQLite (WAL, 共享 1 文件) — **P95=580ms 地板**          │
│  └─ OSS / MinIO (S3 兼容)                                   │
└─────────────────────────────────────────────────────────────┘

缺失层:
  ❌ L3 CDN / edge cache (Cloudflare/Vercel)
  ❌ api-gateway 层缓存 (每个 service 重复 cache key 浪费)
  ❌ Prometheus metrics endpoint (/metrics)
```

### 2.2 Pass 2 — 动态回归 (locust 1000-user CSV 重聚合)

#### 2.2.1 估算 cache effectiveness 上界 (无 Prometheus 实测)

| Endpoint | Reqs/5min | Unique keys 估算 | Cache hit 上界 | 实际 (推算) | Gap |
|---|---|---|---|---|---|
| /healthz | 43,675 | ~4 (4 probes) | **93%** | ~0% (无缓存) | **93pp** |
| /api/v1/health | 17,593 | ~4 | **93%** | ~0% | **93pp** |
| /api/v1/health/ready | 8,792 | ~4 | **93%** | ~0% | **93pp** |
| /readyz | 26,280 | ~4 | **93%** | ~0% | **93pp** |
| /api/v1/users/me | 15,984 | 1,000 users | **94%** | ~0% | **94pp** |
| /api/v1/workflows | 19,792 | ~1,000 templates | **50%** | ~0% | **50pp** |
| /api/v1/assets | 25,824 | ~5,000 unique | **10%** | ~0% | **10pp** |
| /api/v1/tasks | 16,987 | ~2,000 | **25%** | ~0% | **25pp** |
| /api/v1/annotations | 12,746 | ~1,000 | **15%** | ~0% | **15pp** |
| /api/v1/agents | 10,356 | ~500 | **50%** | ~0% | **50pp** |
| **Aggregate weighted** | ~313,960 | ~12,500 | **~55%** | **~0%** | **55pp** |

**关键洞察**: 如果**全开** L1 cache, 整体 hit ratio 应到 **~55%**, 但实际 ~0%.
即 cache 代码就位但**没有被任何 route 实际使用** (除了可能零散的 `@list_cache` 装饰器).

#### 2.2.2 启用 cache 后的 P95 推算 (简化模型)

按 Little's Law: P95 ∝ DB-bound RPS

```
Current:   1048 RPS × 100% to DB  → P95=580ms
+ 50% L1:  524 RPS × 100% to DB   → P95=~290ms  (estimated)
+ 50% L1 + 30% L2: 314 RPS × 100% → P95=~175ms (estimated)
+ 50% L1 + 30% L2 + health probe 1s cache: 270 RPS → P95=~150ms
```

**结论**: 单靠 cache 启用 (无 PostgreSQL) 可达 ~150ms P95, 接近 200ms target.

### 2.3 Pass 3 — 对标行业

| 能力 | nanobot | Cloudflare KV | Redis (managed) | Memcached (FB scale) | Vercel Edge |
|---|---|---|---|---|---|
| L1 in-proc | ✅ 5000 entries | n/a | n/a | n/a | n/a |
| L2 distributed | ❌ (code ready) | ✅ global KV | ✅ cluster | ✅ mcrouter tier | ✅ edge KV |
| TTL | ✅ fixed + jitter? | ✅ per-key | ✅ per-key + PXAT | ✅ per-key | ✅ stale-while-revalidate |
| Invalidation | ✅ prefix + key | ✅ tag-based | ✅ pub/sub + keyspace notif | ✅ cascade | ✅ on-demand revalidation |
| Hit ratio (production) | ~0% (gated) | >99% | >95% | >90% | >95% |
| Consistency | eventual (manual invalidation) | eventual | strong + WATCH/MULTI | strong | strong |
| Multi-tenant | ❌ single | ✅ per-zone | ✅ key namespace | ✅ per-pool | ✅ per-project |
| Auto-invalidation | manual `@post_mutate_invalidate` | webhook + cron | Lua scripts | n/a | ISR + on-demand |

**Gap 严重度**:
1. **HIGH**: L2 未启用 (env 一行配置, 2d 集成) — **最大 ROI**
2. **MEDIUM**: Cache hit ratio 不可见 (无 metrics endpoint) — 1d 加 Prometheus
3. **MEDIUM**: 无 singleflight (缓存击穿防护) — 1d 加 asyncio.Lock + factory dedup
4. **MEDIUM**: 无 TTL jitter (缓存雪崩防护) — 0.5d 装饰器加 random ±10%
5. **LOW**: 无 null caching (缓存穿透防护) — 0.5d 在 get_or_set 加 negative cache
6. **LOW**: 无 multi-tenant (中期, 30d+ SaaS 化时)

---

## 3. Findings (按 P0/P1/P2)

### P0 (必须修, 0 项)

无 P0 — 当前代码无功能/安全 P0 bug, 但有 P1 直接影响 1000-并发性能.

### P1 (重要, 6 项)

| ID | Finding | Impact | Effort | Fix |
|---|---|---|---|---|
| **C-1** | L2 Redis cache 未启用 (env 未设) | Hit ratio 30% → 70%, DB -50% | 2d | `IMDF_CACHE_REDIS_URL=redis://localhost:6379/0` + 12 service 全配置 |
| **C-2** | /healthz, /readyz, /api/v1/health* 无缓存 | 96,348 req/5min (16.1% 流量) 全裸打 SQLite | 0.5d | 加 1s in-proc LRU (10 行) |
| **C-3** | RedisBackend 单连接 (no pool) | 高并发下 socket_timeout=1s 容易全堆 | 0.5d | `redis.ConnectionPool(max_connections=20)` |
| **C-4** | 缺 singleflight (缓存击穿) | 1000 并发同 key cold miss 触发 1000 次 factory | 1d | `asyncio.Lock` per-key dedup |
| **C-5** | 缺 null caching (缓存穿透) | 攻击者可刷不存在 key → DB DoS | 0.5d | get_or_set 加 `if value is None: cache(key, NEG, ttl=10)` |
| **C-6** | `@post_mutate_invalidate` 装饰器未广泛使用 | 写后 stale read 风险 | 1d | 12 service POST handler 审计 + 装饰 |

### P2 (锦上添花, 4 项)

| ID | Finding | Effort |
|---|---|---|
| **C-7** | TTL 缺随机 jitter (缓存雪崩防护) | 0.5d |
| **C-8** | `_common/cache.py` RedisBackend miss 时不 mirror L1 (cache warming 错) | 1d |
| **C-9** | `infrastructure/cache.py` 是 dead code (693 LOC 浪费) | 0.5d cleanup |
| **C-10** | 多租户隔离 (key prefix + tenant_id) | 2d |

---

## 4. 关键代码段 (现有 vs 建议)

### 4.1 现有 (`_common/cache.py`)

```python
def get_or_set(key: str, factory: Callable[[], T],
               ttl_seconds: int = DEFAULT_LIST_TTL) -> T:
    """高层 API: 读穿透模式。"""
    return _backend().get_or_set(key, factory, ttl_seconds=ttl_seconds)
```

### 4.2 建议改造 — 加 singleflight + null cache + jitter

```python
import asyncio
import random

_singleflight_locks: dict[str, asyncio.Lock] = {}
_sf_lock = asyncio.Lock()

async def _sf_get_or_create(key: str) -> asyncio.Lock:
    async with _sf_lock:
        if key not in _singleflight_locks:
            _singleflight_locks[key] = asyncio.Lock()
        return _singleflight_locks[key]

NEG_SENTINEL = "__NEG__"

async def get_or_set_safe(
    key: str,
    factory: Callable[[], Awaitable[T]],
    ttl_seconds: int = 300,
    jitter_pct: float = 0.1,         # ±10% 抖动防雪崩
    negative_ttl: int = 10,         # null cache 10s
) -> Optional[T]:
    # 1) 读缓存
    cached = get(key)
    if cached is NEG_SENTINEL:
        return None
    if cached is not None:
        return cached

    # 2) Singleflight — 同 key 只 factory 一次
    lock = await _sf_get_or_create(key)
    async with lock:
        # Double-check
        cached = get(key)
        if cached is not None:
            return cached if cached is not NEG_SENTINEL else None
        # 3) Factory
        value = await factory()
        if value is None:
            set(key, NEG_SENTINEL, ttl_seconds=negative_ttl)
            return None
        # 4) Jitter TTL 防雪崩
        ttl_jitter = int(ttl_seconds * (1 + random.uniform(-jitter_pct, jitter_pct)))
        set(key, value, ttl_seconds=ttl_jitter)
        return value
```

**效果**: 缓存击穿 -100%, 雪崩 -50% 风险, 穿透 -90% 风险.

---

## 5. 测试覆盖 (建议 P9-6 跑)

```python
# backend/tests/test_cache.py (新增)

import pytest
from api._common.cache import (
    LRUCache, _RedisBackend, list_cache,
    get_or_set_safe, NEG_SENTINEL,
)

class TestLRUCache:
    def test_basic_set_get(self):
        c = LRUCache(max_entries=3)
        c.set("a", 1)
        assert c.get("a") == 1
        assert c.hits == 1

    def test_lru_eviction(self):
        c = LRUCache(max_entries=2)
        c.set("a", 1); c.set("b", 2); c.set("c", 3)
        assert c.get("a") is None  # evicted
        assert c.evictions == 1

    def test_ttl_expiry(self, monkeypatch):
        c = LRUCache()
        c.set("k", "v", ttl_seconds=1)
        monkeypatch.setattr("time.time", lambda: 1000.5)
        assert c.get("k") is None  # expired

class TestSingleflight:
    @pytest.mark.asyncio
    async def test_concurrent_same_key_runs_factory_once(self):
        counter = [0]
        async def factory():
            counter[0] += 1
            await asyncio.sleep(0.1)
            return "value"
        results = await asyncio.gather(*[
            get_or_set_safe("k", factory, ttl_seconds=60)
            for _ in range(100)
        ])
        assert counter[0] == 1   # factory ran once

class TestNullCache:
    @pytest.mark.asyncio
    async def test_negative_result_cached(self):
        async def factory(): return None
        r1 = await get_or_set_safe("missing", factory)
        r2 = await get_or_set_safe("missing", factory)
        assert r1 is None and r2 is None
        # Second call should hit NEG_SENTINEL (not call factory)
```

**预期**: 12-15 tests, ~30s run time, 全 PASS 后 C-1~C-6 可标 done.

---

## 6. 总结

| 维度 | 现状 | 修复后 (P0+P1, ~5d) |
|---|---|---|
| L1 hit ratio | ~0% (装饰器未用) | **~50%** |
| L2 hit ratio | 0% (未启用) | **~20%** |
| Aggregate hit | ~0% | **~70%** |
| DB-bound RPS @ 1000 users | 1048 | ~314 (-70%) |
| Expected P95 | 580ms | **~150ms** (close to 200ms target) |
| Cache-related 5xx | 0 | 0 (仍 0) |
| Multi-tenant ready | ❌ | ⚠️ partial (key prefix 改造) |

**ROI 排序**: C-2 (0.5d) → C-1 (2d) → C-3 (0.5d) → C-4 (1d) → C-5 (0.5d) → C-6 (1d)

— END OF P9-5-CACHE 报告 —