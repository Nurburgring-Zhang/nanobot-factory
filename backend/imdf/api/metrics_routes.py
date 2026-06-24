"""
F0.5: Prometheus Metrics Endpoint (Phase2 Enhanced + R7-W1)
============================================================
GET /metrics -> Prometheus format metrics
Backed by engines.metrics (StreamingHistogram for P50/P95/P99).
R7-W1: Aggregates api/_common/metrics (slow query / cache / process gauges)
so the /metrics endpoint exposes the full R7-W1 surface area.

Includes: request count, latency, error rate, active connections, queue depth, memory,
          slow_queries_total, cache_operations_total, process gauges.
"""
import os
import time
import threading
from typing import Dict, Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])

# Forward compatibility: these functions wrap the new engines.metrics module
# to keep the old call signature working for any code that already imports them
from engines.metrics import (
    get_metrics,
    record_request,
    generate_prometheus,
    HAS_PROMETHEUS_CLIENT,
)

# For backwards compatibility, expose these aliases wrapped from the engine
def record_active_user(user_id: str):
    """Record an active user. (backwards compat wrapper)"""
    pass  # Already tracked via active_connections in metrics.py

def set_queue_depth(depth: int):
    """Set current queue depth. (backwards compat wrapper)"""
    m = get_metrics()
    m.set_queue_metrics(depth, m.snapshot()["running_tasks"])


def _r7_render() -> bytes:
    """R7-W1: 拼接 engines.metrics (历史) + api/_common/metrics (R7 新增) 两份指标。"""
    chunks: list[bytes] = []

    # 1) engines.metrics 输出的 Prometheus 文本
    try:
        legacy = generate_prometheus()
        if isinstance(legacy, str):
            legacy = legacy.encode("utf-8")
        chunks.append(legacy)
    except Exception:
        pass

    # 2) R7-W1 新增: 慢查询 / 缓存 / 进程指标
    try:
        from api._common.metrics import render as r7_render
        r7_body, _ct = r7_render()
        chunks.append(b"\n# R7-W1 metrics (slow_query / cache / process)\n")
        chunks.append(r7_body)
    except Exception:
        pass

    # 3) cache stats 摘要 (便于运维快速看命中率)
    try:
        from api._common.cache import get_cache_stats
        stats = get_cache_stats()
        chunks.append(b"\n# R7-W1 cache stats snapshot (non-prometheus)\n")
        chunks.append(("# HELP imdf_r7_cache_stats_json JSON snapshot\n").encode())
        chunks.append(("# TYPE imdf_r7_cache_stats_json gauge\n").encode())
        import json as _json
        chunks.append(
            ("imdf_r7_cache_stats_json " + _json.dumps(stats) + "\n").encode("utf-8")
        )
    except Exception:
        pass

    return b"".join(chunks)


@router.get("/metrics")
async def get_metrics_endpoint():
    """Prometheus-compatible metrics endpoint.
    Uses engines.metrics with StreamingHistogram for accurate P50/P95/P99
    + R7-W1 metrics (slow query / cache / process gauges).
    """
    return Response(
        content=_r7_render(),
        media_type="text/plain; charset=utf-8",
    )


# ── R7-W1: 缓存统计便捷端点 ──────────────────────────────────────────────
@router.get("/metrics/cache")
async def cache_stats_endpoint():
    """R7-W1: 暴露缓存命中/未命中/驱逐等统计 (非 prometheus 格式)。"""
    try:
        from api._common.cache import get_cache_stats
        return get_cache_stats()
    except Exception as exc:
        return {"error": str(exc)}


# ── R7-W1: 慢查询统计便捷端点 ─────────────────────────────────────────────
@router.get("/metrics/slow_queries")
async def slow_queries_endpoint():
    """R7-W1: 返回 SQLAlchemy 慢查询监听器的累计统计。"""
    try:
        from api.db_models import engine as _engine
        from api._common.slow_query import get_listener_for
        listener = get_listener_for(_engine)
        if listener is None:
            return {"installed": False}
        return {"installed": True, "stats": listener.stats()}
    except Exception as exc:
        return {"installed": False, "error": str(exc)}
