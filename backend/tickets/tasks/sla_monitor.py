"""
P6-Fix-C-5: SLA breach monitor — Celery task
==============================================

Periodic task that wraps ``tickets.sla_monitor.check_sla_breach()`` and
dispatches escalation entries to ``oncall.log`` (and a real webhook if
``ONCALL_WEBHOOK_URL`` is set).

Schedule (defined in ``imdf.config.settings.CELERY_BEAT_SCHEDULE``):
    tickets.tasks.sla_monitor.run_sla_breach_check  — every 30 minutes.

Design notes:
- The task body is a thin wrapper; pure-detection logic lives in
  ``tickets.sla_monitor`` so unit tests can verify classification without
  spinning up a broker.
- ``acks_late=True`` so an unexpected worker crash doesn't drop the
  scheduled run — Celery will redeliver it to the next worker.
- Always returns a JSON-serializable dict (so Celery result backend works
  even when the body executes in eager mode).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from celery import shared_task

# Make `tickets` importable when this module is loaded by Celery beat /
# worker via `celery -A imdf.celery_app ...`.
_THIS_FILE = Path(__file__).resolve()
_TICKETS_DIR = _THIS_FILE.parent.parent            # backend/tickets
_BACKEND_DIR = _TICKETS_DIR.parent                  # backend
for _p in (str(_BACKEND_DIR),):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from tickets.sla_monitor import check_sla_breach, dispatch_alerts  # noqa: E402

logger = logging.getLogger(__name__)


@shared_task(
    name="tickets.tasks.sla_monitor.run_sla_breach_check",
    bind=True,
    acks_late=True,
)
def run_sla_breach_check(self) -> Dict[str, Any]:
    """Periodic SLA breach scan — runs every 30 min via Celery beat.

    Returns a dict with ``scanned`` / ``at_risk_count`` / ``breached_count``
    plus counters for the dispatched alert categories.  The oncall log
    entries themselves are written as a side effect (best-effort).
    """
    started = datetime.utcnow().isoformat()
    try:
        report = check_sla_breach()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("sla_monitor check failed")
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "started_at": started,
            "task_id": self.request.id,
        }

    try:
        counters = dispatch_alerts(report)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("sla_monitor dispatch failed")
        counters = {
            "p0_breach_alerts": 0,
            "p1_breach_alerts": 0,
            "p2_breach_alerts": 0,
            "p3_breach_alerts": 0,
            "at_risk_warnings": 0,
            "dispatch_error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }

    summary = {
        "ok": True,
        "started_at": started,
        "scanned": report.scanned,
        "at_risk_count": len(report.at_risk),
        "breached_count": len(report.breached),
        "alerts": counters,
        "task_id": self.request.id,
    }

    # High-severity log so oncall sees it in the worker stderr stream too.
    if report.breached:
        logger.warning(
            "sla_breach_detected: breached=%d at_risk=%d (P0=%d P1=%d P2=%d P3=%d)",
            len(report.breached),
            len(report.at_risk),
            counters.get("p0_breach_alerts", 0),
            counters.get("p1_breach_alerts", 0),
            counters.get("p2_breach_alerts", 0),
            counters.get("p3_breach_alerts", 0),
        )
    return summary


__all__ = ["run_sla_breach_check"]
