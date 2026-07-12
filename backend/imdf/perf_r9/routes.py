"""VDP-2026 R9 — perf HTTP routes (cache / pool / batch / queue)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Body, Query

from .primitives import get_cache, get_pool, get_batch, get_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/perf", tags=["perf_r9"])


@router.post("/cache/set")
async def cache_set(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    c = get_cache()
    c.set(str(payload.get("key", "")), payload.get("value"), ttl_seconds=payload.get("ttl"))
    return {"ok": True, "stats": c.stats()}


@router.get("/cache/get")
async def cache_get(key: str = Query(...)) -> Dict[str, Any]:
    c = get_cache()
    v = c.get(key)
    return {"value": v, "stats": c.stats()}


@router.post("/cache/invalidate")
async def cache_invalidate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    c = get_cache()
    n = c.invalidate(prefix=payload.get("prefix"))
    return {"invalidated": n, "stats": c.stats()}


@router.get("/cache/stats")
async def cache_stats() -> Dict[str, Any]:
    return get_cache().stats()


@router.post("/pool/acquire")
async def pool_acquire(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    get_pool()
    return get_pool().stats()


@router.post("/pool/release")
async def pool_release(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return get_pool().stats()


@router.get("/pool/stats")
async def pool_stats() -> Dict[str, Any]:
    return get_pool().stats()


@router.post("/batch/run")
async def batch_run(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    b = get_batch()
    job = payload.get("jobs", [])
    # processor is implicit: increment a counter (no real fn needed)
    def _proc(n: int) -> int:
        return n * 2
    for j in job:
        b.add(_proc, args=(int(j.get("value", 0)),))
    b.flush()
    return b.stats()


@router.get("/batch/stats")
async def batch_stats() -> Dict[str, Any]:
    return get_batch().stats()


@router.post("/queue/push")
async def queue_push(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    q = get_queue()
    q.push(payload.get("payload"), priority=float(payload.get("priority", 1.0)))
    return {"ok": True, "stats": q.stats()}


@router.get("/queue/pop")
async def queue_pop(timeout: float = Query(0.1, ge=0.0, le=10.0)) -> Dict[str, Any]:
    q = get_queue()
    return {"value": q.pop(timeout=timeout), "stats": q.stats()}


@router.get("/queue/stats")
async def queue_stats() -> Dict[str, Any]:
    return get_queue().stats()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "cache": get_cache().stats(),
        "pool": get_pool().stats(),
        "batch": get_batch().stats(),
        "queue": get_queue().stats(),
    }
