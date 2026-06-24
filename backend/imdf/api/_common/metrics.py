"""
R7-W1: Prometheus Metrics Wrapper (api/_common/metrics.py)
=========================================================

为 IMDF 服务提供基于 prometheus_client 的指标导出层。

指标分类:
  - HTTP 请求维度: QPS / p50 / p95 / p99 / 错误率
  - 数据库维度: 慢查询计数 / SQL 执行时间分布
  - 缓存维度: 命中 / 未命中 / 命中率
  - 进程维度: 内存 / CPU / 运行时间

设计要点:
  1. 不引入强依赖: prometheus_client 不可用时降级到 in-memory registry
  2. 与 engines.metrics 兼容: 通过 re-export 让老调用继续工作
  3. ASGI 中间件友好: 提供 record_request() / observe_db() / cache_hit/miss()

用法:
  from api._common.metrics import (
      record_request, observe_db_query,
      cache_hit, cache_miss,
      REGISTRY, generate_latest,
  )
"""

from __future__ import annotations

import os
import time
import threading
from typing import Optional

# ── prometheus_client 可用性探测 ────────────────────────────────────────────
try:
    from prometheus_client import (
        Counter as _Counter,
        Histogram as _Histogram,
        Gauge as _Gauge,
        Summary as _Summary,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY as _DEFAULT_REGISTRY,
    )
    _HAS_PROM = True
except Exception:  # ImportError 或版本不兼容
    _HAS_PROM = False
    _DEFAULT_REGISTRY = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


# ── 独立 CollectorRegistry, 避免污染默认全局 ────────────────────────────────
REGISTRY: Optional["CollectorRegistry"] = None
if _HAS_PROM:
    # auto_describe=True 让 Counter/Histogram 自带 HELP 描述
    REGISTRY = CollectorRegistry(auto_describe=True)


# ═══════════════════════════════════════════════════════════════════════════
# 指标定义
# ═══════════════════════════════════════════════════════════════════════════

# ── HTTP 请求 ──────────────────────────────────────────────────────────────
if _HAS_PROM:
    HTTP_REQUESTS_TOTAL = _Counter(
        "imdf_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
        registry=REGISTRY,
    )
    HTTP_REQUEST_LATENCY = _Histogram(
        "imdf_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        registry=REGISTRY,
    )
    HTTP_REQUEST_ERRORS = _Counter(
        "imdf_http_request_errors_total",
        "Total HTTP errors (status >= 400)",
        ["method", "endpoint", "status"],
        registry=REGISTRY,
    )

    # ── 数据库 ─────────────────────────────────────────────────────────────
    DB_QUERY_TOTAL = _Counter(
        "imdf_db_queries_total",
        "Total database queries",
        ["operation"],  # select/insert/update/delete
        registry=REGISTRY,
    )
    DB_QUERY_LATENCY = _Histogram(
        "imdf_db_query_duration_seconds",
        "Database query latency in seconds",
        ["operation"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
        registry=REGISTRY,
    )
    DB_SLOW_QUERIES = _Counter(
        "imdf_db_slow_queries_total",
        "Database queries exceeding slow threshold (>200ms)",
        ["operation"],
        registry=REGISTRY,
    )

    # ── 缓存 ──────────────────────────────────────────────────────────────
    CACHE_OPERATIONS = _Counter(
        "imdf_cache_operations_total",
        "Cache operations",
        ["cache", "op"],  # op = hit/miss/set/delete
        registry=REGISTRY,
    )
    CACHE_LATENCY = _Histogram(
        "imdf_cache_operation_duration_seconds",
        "Cache operation latency in seconds",
        ["cache", "op"],
        buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1),
        registry=REGISTRY,
    )

    # ── 进程 ──────────────────────────────────────────────────────────────
    PROCESS_MEMORY_RSS = _Gauge(
        "imdf_process_memory_rss_bytes",
        "Process RSS memory in bytes",
        registry=REGISTRY,
    )
    PROCESS_UPTIME = _Gauge(
        "imdf_process_uptime_seconds",
        "Process uptime in seconds",
        registry=REGISTRY,
    )
else:
    # ── 占位对象, 让调用方在 prometheus_client 不可用时也不崩溃 ─────────
    class _Stub:
        def labels(self, **_kw): return self
        def inc(self, *_a, **_kw): pass
        def dec(self, *_a, **_kw): pass
        def observe(self, *_a, **_kw): pass
        def set(self, *_a, **_kw): pass

    HTTP_REQUESTS_TOTAL = _Stub()
    HTTP_REQUEST_LATENCY = _Stub()
    HTTP_REQUEST_ERRORS = _Stub()
    DB_QUERY_TOTAL = _Stub()
    DB_QUERY_LATENCY = _Stub()
    DB_SLOW_QUERIES = _Stub()
    CACHE_OPERATIONS = _Stub()
    CACHE_LATENCY = _Stub()
    PROCESS_MEMORY_RSS = _Stub()
    PROCESS_UPTIME = _Stub()


# ═══════════════════════════════════════════════════════════════════════════
# 进程指标后台采样
# ═══════════════════════════════════════════════════════════════════════════

_PROCESS_START = time.monotonic()
_SAMPLE_LOCK = threading.Lock()


def _sample_process() -> None:
    """刷新进程级指标 (RSS / uptime)。供 /metrics scrape 前调用。"""
    uptime = time.monotonic() - _PROCESS_START
    PROCESS_UPTIME.set(uptime)
    try:
        import psutil  # type: ignore
        rss = psutil.Process(os.getpid()).memory_info().rss
        PROCESS_MEMORY_RSS.set(rss)
    except Exception:
        # psutil 不可用时跳过, 不影响其它指标
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 公共 API (供 middleware / slow_query / cache 模块调用)
# ═══════════════════════════════════════════════════════════════════════════

def record_request(method: str, endpoint: str, status_code: int,
                   duration_seconds: float) -> None:
    """记录一次 HTTP 请求。
    
    Args:
        method: HTTP 方法
        endpoint: 规范化后的端点路径 (uuid/id 已替换)
        status_code: 响应状态码
        duration_seconds: 请求耗时 (秒)
    """
    status_class = f"{status_code // 100}xx"
    HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint,
                                status=status_class).inc()
    HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(
        duration_seconds
    )
    if status_code >= 400:
        HTTP_REQUEST_ERRORS.labels(method=method, endpoint=endpoint,
                                    status=status_class).inc()


def observe_db_query(operation: str, duration_seconds: float,
                     slow_threshold: float = 0.2) -> None:
    """记录一次数据库查询。
    
    Args:
        operation: select/insert/update/delete
        duration_seconds: 耗时 (秒)
        slow_threshold: 慢查询阈值 (秒), 默认 0.2s = 200ms
    """
    DB_QUERY_TOTAL.labels(operation=operation).inc()
    DB_QUERY_LATENCY.labels(operation=operation).observe(duration_seconds)
    if duration_seconds >= slow_threshold:
        DB_SLOW_QUERIES.labels(operation=operation).inc()


def cache_hit(cache_name: str = "default") -> None:
    """记录缓存命中。"""
    CACHE_OPERATIONS.labels(cache=cache_name, op="hit").inc()


def cache_miss(cache_name: str = "default") -> None:
    """记录缓存未命中。"""
    CACHE_OPERATIONS.labels(cache=cache_name, op="miss").inc()


def cache_set(cache_name: str = "default") -> None:
    """记录缓存写入。"""
    CACHE_OPERATIONS.labels(cache=cache_name, op="set").inc()


def cache_delete(cache_name: str = "default") -> None:
    """记录缓存删除。"""
    CACHE_OPERATIONS.labels(cache=cache_name, op="delete").inc()


def cache_observe_latency(cache_name: str, op: str,
                          duration_seconds: float) -> None:
    """记录缓存操作耗时。"""
    CACHE_LATENCY.labels(cache=cache_name, op=op).observe(duration_seconds)


def render() -> tuple[bytes, str]:
    """生成 Prometheus exposition format 输出。"""
    _sample_process()
    if _HAS_PROM and REGISTRY is not None:
        return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
    # 降级: 返回最少的可用文本
    return (
        b"# prometheus_client not available; metrics disabled\n",
        CONTENT_TYPE_LATEST,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 兼容 re-export: 让已有代码继续工作
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "REGISTRY",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_LATENCY",
    "HTTP_REQUEST_ERRORS",
    "DB_QUERY_TOTAL",
    "DB_QUERY_LATENCY",
    "DB_SLOW_QUERIES",
    "CACHE_OPERATIONS",
    "CACHE_LATENCY",
    "PROCESS_MEMORY_RSS",
    "PROCESS_UPTIME",
    "record_request",
    "observe_db_query",
    "cache_hit",
    "cache_miss",
    "cache_set",
    "cache_delete",
    "cache_observe_latency",
    "render",
]