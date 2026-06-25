"""
IMDF Celery Application — P2-1-W2 async queue
================================================

Provides:
  - Celery app bound to Redis broker + result backend
  - Task autodiscovery under `imdf.tasks.*`
  - Per-queue routing (video / cpu / index / network / default)
  - Graceful degradation: if Redis is unreachable the module still imports
    (so uvicorn workers start) but health endpoint will report `broker_unreachable`.

Start the worker:

    cd backend
    ../../.ext/python.exe -m celery -A imdf.celery_app:celery_app worker \\
        --loglevel=info --concurrency=2 -Q imdf.default,imdf.video,imdf.cpu,imdf.index,imdf.network

Submit a task (from any Python process with broker reachable):

    from imdf.celery_app import celery_app
    from imdf.tasks.render_video import render_project
    async_result = render_project.delay(project_dict={"title": "demo", "segments": []})
    print(async_result.id, async_result.status)
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional

# Make sure `imdf` is importable when invoked as `celery -A imdf.celery_app`
_THIS_FILE = Path(__file__).resolve()
_BACKEND_DIR = _THIS_FILE.parent  # backend/imdf
_BACKEND_PARENT = _BACKEND_DIR.parent  # backend
_PROJECT_ROOT = _BACKEND_PARENT.parent  # nanobot-factory

# When celery is invoked via `celery -A backend.imdf.celery_app`, sys.path
# must contain `backend/` so that `imdf.*` is importable.
if str(_BACKEND_PARENT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_PARENT))

from celery import Celery  # noqa: E402  (after sys.path fix-up)

logger = logging.getLogger(__name__)


def _build_celery() -> Celery:
    """Construct the Celery application using config.settings."""
    try:
        from imdf.config.settings import (  # type: ignore
            CELERY_BROKER_URL,
            CELERY_RESULT_BACKEND,
            CELERY_RESULT_EXPIRES,
            CELERY_TASK_TIME_LIMIT,
            CELERY_TASK_SOFT_TIME_LIMIT,
            CELERY_WORKER_PREFETCH_MULTIPLIER,
            CELERY_WORKER_MAX_TASKS_PER_CHILD,
            CELERY_TASK_DEFAULT_QUEUE,
            CELERY_TASK_ROUTES,
            CELERY_TASK_ALWAYS_EAGER,
            CELERY_TASK_EAGER_PROPAGATES,
            CELERY_BEAT_SCHEDULE,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to import imdf.config.settings for Celery: %s", exc)
        # Fall back to localhost redis defaults
        broker = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        backend = os.environ.get("CELERY_RESULT_BACKEND", broker)
        cfg = {
            "broker_url": broker,
            "result_backend": backend,
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "timezone": "Asia/Shanghai",
            "enable_utc": False,
        }
        app = Celery("imdf", broker=broker, backend=backend)
        app.conf.update(cfg)
        return app

    app = Celery(
        "imdf",
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=[
            "imdf.tasks.render_video",
            "imdf.tasks.score_aesthetic",
            "imdf.tasks.ocr_extract",
            "imdf.tasks.watermark_embed",
            "imdf.tasks.vector_index",
            "imdf.tasks.model_gateway",
            "imdf.tasks.stats_aggregate",
            # P6-Fix-C-5: tickets SLA monitor
            "tickets.tasks.sla_monitor",
        ],
    )

    app.conf.update(
        # Serialization — JSON only (avoid pickle RCE surface)
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Time / scheduling
        timezone="Asia/Shanghai",
        enable_utc=False,
        task_time_limit=CELERY_TASK_TIME_LIMIT,
        task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
        # Worker behaviour
        worker_prefetch_multiplier=CELERY_WORKER_PREFETCH_MULTIPLIER,
        worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
        # Result hygiene
        result_expires=CELERY_RESULT_EXPIRES,
        # Routing
        task_default_queue=CELERY_TASK_DEFAULT_QUEUE,
        task_routes=CELERY_TASK_ROUTES,
        # Periodic schedule (Celery beat) — P6-Fix-C-5 SLA breach scan runs every 30 min
        beat_schedule=CELERY_BEAT_SCHEDULE,
        # Eager mode (tests)
        task_always_eager=CELERY_TASK_ALWAYS_EAGER,
        task_eager_propagates=CELERY_TASK_EAGER_PROPAGATES,
        # Track started state (so the API can poll intermediate progress)
        task_track_started=True,
        # Reasonable defaults for visibility / heartbeat
        broker_connection_retry_on_startup=True,
        worker_send_task_events=True,
        task_send_sent_event=True,
    )
    logger.info(
        "Celery app 'imdf' configured: broker=%s backend=%s default_queue=%s",
        CELERY_BROKER_URL,
        CELERY_RESULT_BACKEND,
        CELERY_TASK_DEFAULT_QUEUE,
    )
    return app


# Singleton — `celery -A imdf.celery_app:celery_app` expects this name
celery_app: Celery = _build_celery()


# Eagerly import every task module so the API process (uvicorn worker) sees
# the same set of registered tasks as the celery worker would. Without this,
# ``celery_app.tasks`` only contains the celery.* built-ins until the worker
# process imports the include= modules. The /api/queue/health endpoint then
# reports a misleadingly small ``registered_tasks`` count.
for _mod in (
    "imdf.tasks.render_video",
    "imdf.tasks.score_aesthetic",
    "imdf.tasks.ocr_extract",
    "imdf.tasks.watermark_embed",
    "imdf.tasks.vector_index",
    "imdf.tasks.model_gateway",
    "imdf.tasks.stats_aggregate",
    # P6-Fix-C-5: tickets SLA monitor
    "tickets.tasks.sla_monitor",
):
    try:
        __import__(_mod)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to import %s into Celery registry: %s", _mod, exc)


def get_broker_status() -> dict:
    """Inspect broker / backend reachability for /api/queue/health."""
    out = {
        "broker_url": celery_app.conf.broker_url,
        "result_backend": str(celery_app.conf.result_backend),
        "broker_reachable": False,
        "backend_reachable": False,
        "queues": list({r.get("queue", celery_app.conf.task_default_queue) for r in (celery_app.conf.task_routes or {}).values()}),
        "registered_tasks": sorted(celery_app.tasks.keys()),
    }
    try:
        with celery_app.connection_or_acquire() as conn:
            out["broker_reachable"] = True
            out["ping_latency_ms"] = round(conn.default_connection.timeout * 1000, 2)
    except Exception as exc:
        out["broker_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        from celery.result import ResultBackend
        rb: ResultBackend = celery_app.backend
        out["backend_reachable"] = bool(rb.ping(timeout=0.5) if hasattr(rb, "ping") else True)
    except Exception as exc:
        out["backend_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def health_summary() -> dict:
    """Compact health dict for /api/queue/health endpoint."""
    try:
        status = get_broker_status()
        healthy = bool(status.get("broker_reachable")) or not _broker_required()
    except Exception as exc:
        return {"status": "degraded", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "status": "ok" if healthy else "degraded",
        "broker_url": status["broker_url"],
        "broker_reachable": status["broker_reachable"],
        "backend_reachable": status["backend_reachable"],
        "queues": status["queues"],
        "registered_tasks": status["registered_tasks"],
        "default_queue": celery_app.conf.task_default_queue,
    }


def _broker_required() -> bool:
    try:
        from imdf.config.settings import CELERY_HEALTH_REQUIRED  # type: ignore
        return bool(CELERY_HEALTH_REQUIRED)
    except Exception:
        return True


# Expose at module level so `celery -A imdf.celery_app worker ...` discovers them
app = celery_app  # alias — common convention

if __name__ == "__main__":  # pragma: no cover - manual smoke check
    print("Celery app name:", celery_app.main)
    print("Broker:", celery_app.conf.broker_url)
    print("Backend:", celery_app.conf.result_backend)
    print("Routes:", celery_app.conf.task_routes)