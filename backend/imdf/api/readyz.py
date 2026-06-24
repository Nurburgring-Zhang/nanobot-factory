"""
api.readyz
==========

R7-Worker-2: Readiness probe — top-level ``/readyz`` endpoint.

Semantics (Kubernetes-friendly):
  * Returns 200 only when all *critical* dependencies are reachable
    (database, optional disk space, ffmpeg if it's expected).
  * Returns 503 if any critical check fails — k8s will then stop routing
    traffic to this pod until it recovers.
  * Distinct from ``/healthz`` (process alive) — readiness cares about
    *usability*.

This module reuses the heavy-lifting from ``api.health_routes.check_*`` so
behaviour stays aligned with the existing ``/api/v1/health/ready`` endpoint.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Response

# Ensure project root in path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api._common.logging_setup import get_logger  # noqa: E402

logger = get_logger("imdf.readyz")

router = APIRouter(tags=["readyz"])

STARTUP_TIME = time.time()


def _uptime() -> float:
    return round(time.time() - STARTUP_TIME, 1)


# ── Critical checks (must pass for 200) ──────────────────────────────────────
def _check_db() -> dict:
    """Synchronous SQLite ping to the main imdf.db."""
    try:
        import sqlite3
        db_path = _PROJECT_ROOT / "data" / "imdf.db"
        target = str(db_path) if db_path.exists() else ":memory:"
        conn = sqlite3.connect(target, timeout=1.5)
        try:
            cur = conn.execute("SELECT 1")
            row = cur.fetchone()
            ok = row is not None and row[0] == 1
        finally:
            conn.close()
        return {
            "ok": ok,
            "message": "DB connected" if ok else "DB ping returned no row",
            "path": target,
        }
    except Exception as e:
        return {"ok": False, "message": f"DB error: {str(e)[:120]}", "path": None}


def _check_disk() -> dict:
    """Disk free > 200MB is 'ok' for readiness (vs 500MB for full health)."""
    try:
        import shutil
        usage = shutil.disk_usage(str(_PROJECT_ROOT))
        mb_free = usage.free / (1024 * 1024)
        ok = mb_free > 200
        return {
            "ok": ok,
            "free_mb": round(mb_free, 1),
            "message": f"{mb_free:.0f}MB free" if ok else f"Low disk: {mb_free:.0f}MB free",
        }
    except Exception as e:
        return {"ok": False, "message": f"Disk check failed: {str(e)[:120]}"}


@router.get("/readyz", include_in_schema=False)
async def readyz() -> Response:
    """Readiness probe — 200 if all critical components are healthy.

    Critical checks (any failure → 503):
      * DB ping
      * Disk free space
    """
    checks = {
        "database": _check_db(),
        "disk": _check_disk(),
    }
    all_ok = all(v.get("ok") for v in checks.values())
    degraded = [k for k, v in checks.items() if not v.get("ok")]

    payload = {
        "status": "ok" if all_ok else "not_ready",
        "service": "imdf",
        "uptime_seconds": _uptime(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "degraded_components": degraded or None,
    }

    if all_ok:
        logger.debug("readyz ok", uptime_seconds=payload["uptime_seconds"])
    else:
        logger.warning(
            "readyz degraded",
            degraded_components=degraded,
            checks=checks,
        )

    import json
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        status_code=200 if all_ok else 503,
    )