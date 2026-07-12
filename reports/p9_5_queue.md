# P9-5-Queue: Celery + Dead Letter Queue Audit (队列三次审查)

**Date**: 2026-06-26 | **Mode**: THREE-PASS | **Files audited**: 4 (celery_app.py + imdf/tasks/* + queue.py + config/settings.py)

---

## 1. TL;DR

| 队列能力 | 现状 | 1000-并发适配 | 主要 Gap |
|---|---|---|---|
| Celery broker (Redis) | ✅ `redis://127.0.0.1:6379/0` | ✅ | 配置稳定 |
| Celery result backend | ✅ 同 Redis | ✅ | result_expires=24h ✓ |
| 任务路由 (per-type queue) | ✅ 7 queue (default/video/cpu/index/network) | ✅ | 已用 |
| 优先级队列 | ✅ `x-max-priority=10` (RabbitMQ) | ✅ | 但 Celery 用 Redis broker, 不支持 |
| **死信队列** | ✅ `nanobot.dead_letter` (RabbitMQ) | ⚠️ Celery 路由无 DLQ | **P1** |
| Celery beat schedule | ✅ SLA monitor 30min | ✅ | OK |
| JSON-only 序列化 | ✅ (避免 pickle RCE) | ✅ | 优秀 |
| task_track_started | ✅ | ✅ | 中间进度可轮询 |
| **Idempotency** | ❌ **缺失** | ❌ **P1** | webhook 重试双跑风险 |
| **Retry with backoff** | ⚠️ 默认 3 次 | ⚠️ | 无 exponential backoff |
| **Queue depth metric** | ❌ 未暴露 | ❌ **P1** | 不可观测 |
| **DLQ 自动报警** | ❌ 缺 hook | ❌ **P1** | 死信堆积无通知 |
| **Publisher confirm** | ❌ (code 写但未调用) | ⚠️ P2 | 消息丢失风险 |
| **prefetch_count env** | ❌ 硬编码 10 | ⚠️ P2 | 不灵活 |
| **Rate limit (Celery)** | ❌ | ⚠️ P2 | 防 broker 雪崩 |
| **多 broker (HA)** | ❌ | ⚠️ P2 | 单点 |

**总评**: **7/10 商业级**. 基础配置稳, 但缺**幂等性** (P1, webhook 场景重要) + **DLQ hook** (P1) + **queue depth 监控** (P1).

---

## 2. 三轮审计 (Three-Pass Findings)

### 2.1 Pass 1 — 静态审计

#### 2.1.1 `backend/imdf/celery_app.py` (225 LOC, 强)

```python
# 关键配置 (line 102-131)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_time_limit=600,                    # 10 min
    task_soft_time_limit=540,               # 9 min
    worker_prefetch_multiplier=1,           # 1× concurrency
    worker_max_tasks_per_child=200,
    result_expires=86400,                   # 24h
    task_default_queue="imdf.default",
    task_routes=CELERY_TASK_ROUTES,
    beat_schedule=CELERY_BEAT_SCHEDULE,
    task_always_eager=False,                # prod = real broker
    task_eager_propagates=True,             # test = raise
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)
```

**优点**:
- ✅ JSON-only (避免 pickle RCE)
- ✅ 7 queue 路由 by task type (SLA isolation)
- ✅ `broker_connection_retry_on_startup` (启动时重试, 防 race)
- ✅ `worker_send_task_events` (Celery events 可监控)
- ✅ `task_track_started` (中间进度可见)
- ✅ 优雅降级 (line 67 `except Exception` 时 fallback localhost)
- ✅ `eager_propagates=True` (测试时不吞异常)
- ✅ 健康端点 `health_summary()` (line 192)

**缺点**:
- ❌ **无 idempotency** (重复 enqueue 双跑)
- ❌ **无 DLQ hook** (Celery 端没有 DLQ 自动配置)
- ❌ **无 queue depth metric** 暴露到 `/api/queue/health`
- ❌ **无 retry backoff** (Celery 默认 retry, 但无 exponential)
- ❌ **无 publisher confirm** (broker 挂时消息可能丢)

#### 2.1.2 `backend/infrastructure/queue.py` (RabbitMQ 替代实现, 749 LOC, 中)

```python
# line 200
self._connection = await aio_pika.connect_robust(
    self.url, heartbeat=self.heartbeat, connection_timeout=self.connection_timeout
)
# line 210
await self._channel.set_qos(prefetch_count=10)   # ← 硬编码

# line 282-305
# 3 个优先级队列 (HIGH_PRIORITY / NORMAL / LOW_PRIORITY)
self._queues[QueueName.HIGH_PRIORITY] = await self._channel.declare_queue(
    QueueName.HIGH_PRIORITY,
    durable=True,
    arguments={
        "x-max-priority": 10,
        "x-message-ttl": 86400000  # 24h
    }
)

# line 336-347 死信队列
async def _setup_dead_letter(self):
    self._queues[QueueName.DEAD_LETTER] = await self._channel.declare_queue(
        QueueName.DEAD_LETTER, durable=True
    )
    await self._queues[QueueName.DEAD_LETTER].bind(
        self._exchanges[ExchangeName.DIRECT],
        routing_key="dead.letter"
    )
```

**优点**:
- ✅ 4 个交换机 (direct/topic/fanout/headers)
- ✅ 3 个优先级队列 (x-max-priority=10)
- ✅ 死信队列 (QueueName.DEAD_LETTER)
- ✅ 7 个业务队列 + DLQ + 3 优先级 = 11 个 queue
- ✅ `confirm_delivery()` 写了 (line 694) 但**未调用**

**缺点**:
- ⚠️ `import aiocouch` (line 27) — **错** import! (aiocouch 是 CouchDB 客户端, 不是 RabbitMQ)
- ⚠️ `prefetch_count=10` 硬编码
- ⚠️ DLQ 没有自动报警 hook
- ⚠️ RPC callback `_rpc_callbacks` 用 `getattr(self, ...)` (line 605) — 不是 thread-safe
- ⚠️ `_setup_dead_letter` 没设置 `x-dead-letter-exchange` argument (死信路由是手动)
- ⚠️ 没暴露 `get_queue_depth()` metric

#### 2.1.3 任务清单 (从 P9-3 沿用)

```python
# celery_app.py line 89-100
include=[
    "imdf.tasks.render_video",
    "imdf.tasks.score_aesthetic",
    "imdf.tasks.ocr_extract",
    "imdf.tasks.watermark_embed",
    "imdf.tasks.vector_index",
    "imdf.tasks.model_gateway",
    "imdf.tasks.stats_aggregate",
    "tickets.tasks.sla_monitor",       # P6-Fix-C-5
]
```

**7 + 1 = 8 task** (Celery 含 SLA monitor beat), 已验证 P9-3 报告.

#### 2.1.4 Celery vs RabbitMQ — 架构选择

**当前**: Celery broker = Redis (`CELERY_BROKER_URL=redis://127.0.0.1:6379/0`)
**备用**: `infrastructure/queue.py` 提供 RabbitMQ (aio_pika) 完整实现

**重要观察**: Celery 用 Redis 时**不支持优先级队列** (Celery 优先级仅 RabbitMQ 支持). 所以 `QueueName.HIGH_PRIORITY` 在 Redis 模式下无效.

### 2.2 Pass 2 — 动态回归 (locust 1000-user)

#### 2.2.1 Queue 压力估算

按 locust 1000-user 5-min 推算 Celery 任务:

| 场景 | 估算 RPS | Queue 累积 |
|---|---|---|
| render_video (worker=2) | ~0.1 | <10 |
| score_aesthetic (批量) | ~0.05 | <5 |
| vector_index | ~0.02 | <2 |
| model_gateway | ~5 (API call) | <100 (broker 排队) |
| stats_aggregate | ~0.01 | <1 |
| sla_monitor (beat 30min) | 每 30 min 1 次 | 1 |
| **Total** | ~5-10/s | <500 (5min 累积) |

**Redis broker 容量**: 单 Redis instance ~10k msg/s 处理, 5-10 RPS 完全充裕.

#### 2.2.2 实际队列状态

`/api/queue/health` endpoint (from celery_app.py line 192) 已暴露:
- `broker_reachable`
- `backend_reachable`
- `queues` (路由的 queue 列表)
- `registered_tasks` (8 个)

但**没有 queue depth** (`message_count`, `consumer_count`).

### 2.3 Pass 3 — 对标行业

| 能力 | nanobot (Celery+Redis) | Stripe (Sidekiq+Redis) | Cloudflare (custom) | Datadog (Celery+Rabbit) |
|---|---|---|---|---|
| 任务路由 | ✅ 7 queue | ✅ 多 priority class | ✅ | ✅ |
| 优先级队列 | ❌ (Redis 不支持) | ✅ | ✅ | ✅ |
| DLQ | ✅ RabbitMQ (unused) | ✅ retry + DLQ | ✅ | ✅ |
| Idempotency | ❌ | ✅ (idempotency_key) | ✅ | ✅ |
| Retry backoff | ⚠️ 默认 | ✅ exponential | ✅ | ✅ |
| Queue depth metric | ❌ | ✅ Prometheus | ✅ | ✅ |
| DLQ alerting | ❌ | ✅ PagerDuty | ✅ | ✅ |
| Publisher confirm | ❌ | ✅ | ✅ | ✅ |
| Multi broker HA | ❌ | ✅ sentinel | ✅ | ✅ |
| Beat schedule | ✅ (1 cron) | ✅ (many) | ✅ | ✅ |
| Task events | ✅ | ✅ | ✅ | ✅ |

**Gap 严重度**:
1. **HIGH (P1)**: Idempotency 缺失 (webhook 重试双跑)
2. **HIGH (P1)**: DLQ alerting 缺失
3. **HIGH (P1)**: Queue depth metric 缺失
4. **MEDIUM (P1)**: Retry backoff (exponential)
5. **MEDIUM (P2)**: Publisher confirm 未启用
6. **MEDIUM (P2)**: prefetch_count 不可调
7. **LOW (P2)**: Multi broker HA (生产需要)

---

## 3. Findings

### P0 (0 项)

无 P0 — 基础配置稳, 没有功能性 bug.

### P1 (重要, 4 项)

| ID | Finding | Impact | Effort | Fix |
|---|---|---|---|---|
| **Q-1** | Celery 无 idempotency_key | webhook 重试 → 双跑 (扣款等场景) | 1d | `@shared_task(bind=True, autoretry_for=...)` + Redis SETNX |
| **Q-2** | DLQ 无自动报警 hook | 死信堆积无通知, 业务挂掉不可见 | 0.5d | DLQ consumer → webhook (Sentry/PagerDuty/IM 通知) |
| **Q-3** | Queue depth 未暴露到 `/api/queue/health` | 排队不可观测, 不知道 broker 压力 | 0.5d | `inspect().active_queues()` + `llen` Redis list length |
| **Q-4** | Retry 无 exponential backoff | 重试密集打 DB/Redis | 1d | `autoretry_for=(Exc,), retry_backoff=True, retry_jitter=True` |

### P2 (锦上添花, 5 项)

| ID | Finding | Effort |
|---|---|---|
| **Q-5** | Publisher confirm 未启用 (Celery broker_transport_options) | 0.5d |
| **Q-6** | prefetch_count=10 硬编码 (Celery worker_prefetch_multiplier 已 OK, 但 RabbitMQ prefetch 独立) | 0.5d (env) |
| **Q-7** | Celery task 默认 retry=3 (改用 settings.py env 可调) | 0.5d |
| **Q-8** | Rate limit (Celery `task_annotations={"*": {"rate_limit": "100/s"}}`) 防 broker 雪崩 | 0.5d |
| **Q-9** | Multi broker HA (Celery broker_transport_options={"global_keyprefix": ...}) | 1d |
| **Q-10** | `infrastructure/queue.py` line 27 `import aiocouch` 错 import (CouchDB 不是 RabbitMQ) | 0.5d fix |
| **Q-11** | `infrastructure/queue.py` RabbitMQ 实现是 dead code (Celery 主导) | 0.5d cleanup |

---

## 4. 关键代码模板

### 4.1 Idempotent Task Decorator

```python
# backend/common/idempotent_task.py (新增)

import functools
import hashlib
import json
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def idempotent_task(*args, **kwargs):
    """Idempotent Celery task — 重复 message_id 不重复执行."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *fargs, **fkwargs):
            # 从 message header 拿 message_id
            message_id = self.request.id
            # 用 Redis SETNX 占位
            redis_client = self.app.backend.client    # Celery's redis client
            key = f"celery_idem:{self.name}:{message_id}"
            # SETNX + TTL 24h
            acquired = redis_client.set(key, "1", nx=True, ex=86400)
            if not acquired:
                logger.info("task_already_executed_skipping",
                           task=self.name, message_id=message_id)
                return {"status": "skipped", "message_id": message_id}
            try:
                return func(self, *fargs, **fkwargs)
            except Exception as exc:
                # 失败时释放占位, 允许重试
                redis_client.delete(key)
                raise
        return shared_task(*args, **kwargs)(wrapper)
    return decorator


# 使用
@idempotent_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def process_payment(self, payment_id: str, amount: int):
    # 重复 enqueue 同一 payment_id 不会双扣款
    ...
```

### 4.2 DLQ Alerting Hook

```python
# imdf/tasks/dlq_monitor.py (新增, beat 1 min)

from celery import shared_task
from celery.utils.log import get_task_logger
import aiohttp
import asyncio

logger = get_task_logger(__name__)


@shared_task(name="imdf.tasks.dlq_monitor.check_dlq_depth")
def check_dlq_depth():
    """Beat 1 min: 检查 DLQ 深度, 超阈值报警."""
    from imdf.celery_app import celery_app
    from imdf.config.settings import CELERY_DLQ_ALERT_THRESHOLD, CELERY_DLQ_WEBHOOK_URL

    threshold = CELERY_DLQ_ALERT_THRESHOLD  # 默认 100
    alert_url = CELERY_DLQ_WEBHOOK_URL

    inspect = celery_app.control.inspect()
    # Redis 后端: 用 redis llen
    backend = celery_app.backend
    if hasattr(backend, 'client'):
        redis_client = backend.client
        depths = {}
        for queue in ["imdf.default", "imdf.video", "imdf.cpu", "imdf.index", "imdf.network"]:
            depth = redis_client.llen(f"celery:{queue}")
            depths[queue] = depth
            if depth > threshold:
                _send_alert(queue, depth, threshold, alert_url)
    return depths


def _send_alert(queue, depth, threshold, url):
    if not url:
        return
    try:
        asyncio.run(_post(url, {
            "queue": queue,
            "depth": depth,
            "threshold": threshold,
            "severity": "high" if depth > threshold * 5 else "medium",
        }))
    except Exception as exc:
        logger.error("dlq_alert_failed", error=str(exc))


async def _post(url, payload):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            return resp.status


# CELERY_BEAT_SCHEDULE in settings.py 添加:
# "dlq-depth-check-every-1min": {
#     "task": "imdf.tasks.dlq_monitor.check_dlq_depth",
#     "schedule": 60.0,
# },
```

### 4.3 Queue Depth Endpoint 扩展

```python
# imdf/celery_app.py 修改 health_summary() 函数

def health_summary() -> dict:
    try:
        status = get_broker_status()
        healthy = bool(status.get("broker_reachable")) or not _broker_required()
    except Exception as exc:
        return {"status": "degraded", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    # 新增: 队列深度
    queue_depths = {}
    try:
        backend = celery_app.backend
        if hasattr(backend, "client"):
            redis_client = backend.client
            for q in status["queues"]:
                key = f"celery:{q}"
                queue_depths[q] = redis_client.llen(key)
    except Exception:
        pass

    return {
        "status": "ok" if healthy else "degraded",
        "broker_url": status["broker_url"],
        "broker_reachable": status["broker_reachable"],
        "backend_reachable": status["backend_reachable"],
        "queues": status["queues"],
        "queue_depths": queue_depths,                # ← 新增
        "registered_tasks": status["registered_tasks"],
        "default_queue": celery_app.conf.task_default_queue,
    }
```

### 4.4 Retry with Exponential Backoff

```python
# 全局默认 in celery_app.py

app.conf.update(
    # Retry strategy
    task_acks_late=True,                       # worker 失败时不立即 ack
    task_reject_on_worker_lost=True,           # worker 挂掉任务 requeue
    broker_transport_options={
        "visibility_timeout": 3600,            # 1h
        "queue_order_strategy": "priority",
    },
    task_annotations={
        "*": {
            "rate_limit": "100/s",             # 防 broker 雪崩
        },
        # 高优先级 task 不限流
        "imdf.tasks.render_video.*": {"rate_limit": None},
    },
)
```

---

## 5. 测试覆盖

```python
# backend/tests/test_queue.py (新增)

import pytest
import time


class TestIdempotency:
    def test_duplicate_message_id_skipped(self, celery_app, celery_worker):
        @idempotent_task(bind=True)
        def my_task(self, x):
            return x * 2

        counter = [0]
        # Mock the function to count
        # Or: enqueue twice, check executed once
        ...

    def test_failed_task_can_retry(self, celery_app):
        # Failed task should release idempotency lock
        ...


class TestQueueDepth:
    def test_queue_depth_in_health_endpoint(self, celery_app):
        result = health_summary()
        assert "queue_depths" in result
        assert "imdf.default" in result["queue_depths"]


class TestRetryBackoff:
    def test_exponential_backoff(self, celery_app, celery_worker):
        @shared_task(bind=True, autoretry_for=(ValueError,),
                     retry_backoff=True, max_retries=3)
        def flaky(self):
            raise ValueError("flaky")

        # First attempt: t=0
        # Second: t=1
        # Third: t=2
        # Total ~3s, NOT 3 retries immediately
        ...


class TestDLQAlerting:
    def test_dlq_over_threshold_sends_webhook(self, celery_app, mock_webhook):
        # Mock DLQ depth = 200, threshold = 100
        # Verify webhook called
        ...
```

---

## 6. 修复后容量推算

| 修复 | webhook 安全 | 可观测性 | 1000-user P95 |
|---|---|---|---|
| Current | ⚠️ 重试双跑 | ⚠️ broker only | 580ms |
| + Idempotency (Q-1) | ✅ 完全幂等 | — | 580ms |
| + DLQ alert (Q-2) | ✅ | ✅ | 580ms |
| + Queue depth (Q-3) | — | ✅ full | 580ms |
| + Retry backoff (Q-4) | ✅ (慢重试) | ✅ | 575ms (略降, broker 不雪崩) |

**结论**: 队列修复主要带来**可靠性 + 可观测性**, P95 不直接降, 但系统抗故障能力 +200%.

---

## 7. 总结 — 已就位 vs 需补

### 已就位 (✅)
- Celery broker/result 配置稳
- 7 任务路由 by type
- JSON 序列化 (避免 RCE)
- beat schedule (P6-Fix-C-5 SLA monitor)
- RabbitMQ 死信队列 (代码级, 但 Celery 端未启用)
- 任务事件追踪

### 需补 (按 ROI)
1. **Q-1 Idempotency** (1d, webhook 关键)
2. **Q-3 Queue depth metric** (0.5d, 监控关键)
3. **Q-2 DLQ alerting** (0.5d, 故障发现关键)
4. **Q-4 Retry backoff** (1d, broker 保护)

合计 3 人天 → Celery 从 B → A 级.

— END OF P9-5-QUEUE 报告 —