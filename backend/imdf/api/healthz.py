"""
api.healthz
===========

R7-Worker-2: Liveness probe — top-level ``/healthz`` endpoint.

Semantics (Kubernetes-friendly):
  * Returns 200 as long as the Python process is alive and the event loop
    can respond. No DB, no disk, no external dependencies.
  * Intended for ``livenessProbe`` in k8s — restart only when this fails.
  * Detailed component checks (DB / disk / ffmpeg / memory / vector_store)
    live on ``/readyz`` and ``/api/v1/health/ready`` instead.

Response shape::

    {
      "status": "ok",
      "service": "imdf",
      "version": "...",
      "uptime_seconds": 12.3,
      "timestamp": "2026-06-18T08:05:00.123456+00:00",
      "pid": 12345
    }
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

# Ensure project root in path (so this file works whether imported as
# ``api.healthz`` or ``run directly``).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api._common.logging_setup import get_logger  # noqa: E402

logger = get_logger("imdf.healthz")

router = APIRouter(tags=["healthz"])

STARTUP_TIME = time.time()


def _uptime() -> float:
    return round(time.time() - STARTUP_TIME, 1)


@router.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    """Liveness probe — returns 200 if the process is alive.

    This endpoint is *cheap* (no DB / FS checks) so it can be polled every
    second by k8s without hurting throughput.
    """
    payload = {
        "status": "ok",
        "service": "imdf",
        "version": _read_version(),
        "uptime_seconds": _uptime(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    logger.debug("healthz probe", **payload)
    return JSONResponse(content=payload, status_code=200)


def _read_version() -> str:
    """Best-effort version string from VERSION file (fallback '2.0.0')."""
    try:
        v = _PROJECT_ROOT / "VERSION"
        if v.exists():
            return v.read_text(encoding="utf-8").strip() or "2.0.0"
    except Exception:
        pass
    return "2.0.0"