"""
Phase2: Enhanced Health Check Routes
====================================
Provides three levels of health check endpoints:

  GET /api/v1/health       — Basic health + DB connectivity check
  GET /api/v1/health/ready — Readiness check (all components: DB, disk, ffmpeg, etc.)
  GET /api/v1/health/live  — Liveness check (lightweight, just returns 200)

All endpoints return standard JSON with status/message/checks format.
"""

import os
import sys
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

# Ensure project root in path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

router = APIRouter(tags=["health"])

# Track startup time for uptime calculation
STARTUP_TIME = time.time()


def _get_uptime_seconds() -> float:
    return time.time() - STARTUP_TIME


# ============================================================================
# Component Check Helpers
# ============================================================================

def check_database() -> Dict[str, Any]:
    """Check database connectivity using aiosqlite."""
    try:
        import sqlite3
        # Try the main database file
        db_path = _PROJECT_ROOT / "data" / "imdf.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT 1")
            row = cursor.fetchone()
            conn.close()
            db_ok = row is not None and row[0] == 1
        else:
            # Fallback: try in-memory
            conn = sqlite3.connect(":memory:")
            cursor = conn.execute("SELECT 1")
            row = cursor.fetchone()
            conn.close()
            db_ok = row is not None and row[0] == 1
        return {"ok": db_ok, "message": "DB connected" if db_ok else "DB connection failed"}
    except Exception as e:
        return {"ok": False, "message": f"DB error: {str(e)[:100]}"}


def check_disk() -> Dict[str, Any]:
    """Check disk space. Warnings below 500MB free."""
    try:
        usage = shutil.disk_usage(str(_PROJECT_ROOT))
        mb_free = usage.free / (1024 * 1024)
        mb_total = usage.total / (1024 * 1024)
        pct_used = round(usage.used / usage.total * 100, 1)
        ok = mb_free > 500
        return {
            "ok": ok,
            "free_mb": round(mb_free, 1),
            "total_mb": round(mb_total, 1),
            "used_pct": pct_used,
            "message": f"{mb_free:.0f}MB free" if ok else f"Low disk: {mb_free:.0f}MB free",
        }
    except Exception as e:
        return {"ok": False, "message": f"Disk check failed: {str(e)[:100]}"}


def check_ffmpeg() -> Dict[str, Any]:
    """Check if ffmpeg is available on PATH."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return {"ok": True, "path": ffmpeg_path, "message": "ffmpeg available"}
    return {"ok": False, "message": "ffmpeg not found"}


def check_memory() -> Dict[str, Any]:
    """Check process memory usage."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem = process.memory_info()
        mem_pct = process.memory_percent()
        return {
            "ok": True,
            "rss_mb": round(mem.rss / (1024 * 1024), 1),
            "percent": round(mem_pct, 1),
            "message": f"{mem.rss // (1024*1024)}MB RSS",
        }
    except ImportError:
        return {"ok": True, "message": "psutil not available, memory check skipped"}
    except Exception as e:
        return {"ok": False, "message": f"Memory check failed: {str(e)[:100]}"}


def check_vector_store() -> Dict[str, Any]:
    """Check if vector store DB exists and is readable."""
    try:
        import sqlite3
        vs_path = _PROJECT_ROOT / "data" / "vector_store.db"
        if vs_path.exists():
            conn = sqlite3.connect(str(vs_path))
            conn.execute("SELECT 1")
            conn.close()
            return {"ok": True, "message": "Vector store accessible"}
        return {"ok": True, "message": "Vector store not yet created"}
    except Exception as e:
        return {"ok": False, "message": f"Vector store error: {str(e)[:100]}"}


def check_api_keys_db() -> Dict[str, Any]:
    """Check if API keys database exists and is readable."""
    try:
        import sqlite3
        ak_path = _PROJECT_ROOT / "data" / "api_keys.db"
        if ak_path.exists():
            conn = sqlite3.connect(str(ak_path))
            conn.execute("SELECT 1")
            conn.close()
            return {"ok": True, "message": "API keys DB accessible"}
        return {"ok": True, "message": "API keys DB not yet created"}
    except Exception as e:
        return {"ok": False, "message": f"API keys DB error: {str(e)[:100]}"}


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/api/v1/health")
@router.get("/api/health")
async def health_basic():
    """
    Basic health check.
    Returns: service status + database connectivity.
    """
    db = check_database()
    overall = db["ok"]

    return JSONResponse(
        content={
            "success": overall,
            "data": {
                "status": "ok" if overall else "degraded",
                "service": "imdf",
                "version": "2.0.0",
                "uptime_seconds": round(_get_uptime_seconds(), 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": {
                    "database": db,
                },
            },
            "error": None if overall else "Database check failed",
            "message": "health check ok" if overall else "health check degraded",
        },
        status_code=200 if overall else 503,
    )


@router.get("/api/v1/health/ready")
@router.get("/api/health/ready")
async def health_ready():
    """
    Readiness check: verifies ALL core components are ready.
    Checks: database, disk space, ffmpeg, memory, vector store, API keys DB.
    Returns 200 if all pass, 503 if any component is not ready.
    """
    checks = {
        "database": check_database(),
        "disk": check_disk(),
        "ffmpeg": check_ffmpeg(),
        "memory": check_memory(),
        "vector_store": check_vector_store(),
        "api_keys_db": check_api_keys_db(),
    }

    all_ok = all(v.get("ok", False) for v in checks.values())
    degraded = [k for k, v in checks.items() if not v.get("ok", False)]

    return JSONResponse(
        content={
            "success": all_ok,
            "data": {
                "status": "ok" if all_ok else "degraded",
                "service": "imdf",
                "version": "2.0.0",
                "uptime_seconds": round(_get_uptime_seconds(), 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": checks,
                "degraded_components": degraded if degraded else None,
            },
            "error": None if all_ok else f"Degraded components: {', '.join(degraded)}",
            "message": "all components ready" if all_ok else "some components degraded",
        },
        status_code=200 if all_ok else 503,
    )


@router.get("/api/v1/health/live")
@router.get("/api/health/live")
async def health_live():
    """
    Liveness check: lightweight probe that just confirms the service is alive.
    Returns 200 always if the server is responding.
    """
    return JSONResponse(
        content={
            "success": True,
            "data": {
                "status": "ok",
                "service": "imdf",
                "uptime_seconds": round(_get_uptime_seconds(), 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "error": None,
            "message": "service is alive",
        },
        status_code=200,
    )


@router.get("/api/v1/health/metrics-summary")
async def health_metrics_summary():
    """
    Health + metrics summary: combines health check with key metrics.
    Useful for dashboard or alerting systems.
    """
    from engines.metrics import get_metrics
    metrics = get_metrics()
    snap = metrics.snapshot()

    db = check_database()
    disk = check_disk()

    db_ok = db["ok"]
    return {
        "success": db_ok,
        "data": {
            "status": "ok" if db_ok else "degraded",
            "service": "imdf",
            "version": "2.0.0",
            "uptime_seconds": snap["uptime_seconds"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health": {
                "database": db,
                "disk": disk,
            },
            "metrics": {
                "requests_total": snap["request_count_total"],
                "errors_total": snap["error_count_total"],
                "active_connections": snap["active_connections"],
                "active_ws": snap["active_ws_connections"],
                "queue_depth": snap["queue_depth"],
                "running_tasks": snap["running_tasks"],
                "memory_mb": round(snap["memory_rss_bytes"] / (1024 * 1024), 1),
                "memory_pct": snap["memory_percent"],
                "latency_p50_ms": round(snap["latency"]["p50"] * 1000, 1),
                "latency_p95_ms": round(snap["latency"]["p95"] * 1000, 1),
                "latency_p99_ms": round(snap["latency"]["p99"] * 1000, 1),
            },
        },
        "error": None if db_ok else "Database check failed",
        "message": "metrics summary ok" if db_ok else "metrics summary degraded",
    }
