"""
Async stats aggregation tasks (P2-1-W2)
========================================

Tasks:
- ``daily_report``   — compute a single-day stats report.
- ``compare_periods`` — compare two date ranges.
- ``team_summary``   — per-team rollup.

These wrap ``engines.stats_dashboard.StatsDashboard``. The dashboard reads
from a JSON-backed datastore, so the work is CPU-bound (no I/O blocking),
but still useful to keep out of the request hot-path.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


@shared_task(name="imdf.tasks.stats_aggregate.daily_report", bind=True, acks_late=True)
def daily_report(self, date_str: Optional[str] = None) -> Dict[str, Any]:
    """Compute the daily report for a given YYYY-MM-DD string (or today)."""
    try:
        from engines.stats_dashboard import StatsDashboard
        dashboard = StatsDashboard()
        report = dashboard.get_daily_report(date_str=date_str)
        return {"ok": True, "date": date_str or "today", "report": report, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        logger.exception("daily_report failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.stats_aggregate.compare_periods", bind=True, acks_late=True)
def compare_periods(
    self,
    start_a: str,
    end_a: str,
    start_b: str,
    end_b: str,
) -> Dict[str, Any]:
    """Compare two date ranges."""
    try:
        from engines.stats_dashboard import StatsDashboard
        dashboard = StatsDashboard()
        if not hasattr(dashboard, "compare_periods"):
            return {
                "ok": False, "error": "compare_periods_not_implemented",
                "task_id": self.request.id,
            }
        result = dashboard.compare_periods(start_a, end_a, start_b, end_b)
        return {
            "ok": True,
            "a": {"start": start_a, "end": end_a},
            "b": {"start": start_b, "end": end_b},
            "diff": result,
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("compare_periods failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.stats_aggregate.team_summary", bind=True)
def team_summary(self, team_id: Optional[str] = None) -> Dict[str, Any]:
    """Per-team rollup; if ``team_id`` is None, summarise all teams."""
    try:
        from engines.stats_dashboard import StatsDashboard
        dashboard = StatsDashboard()
        if hasattr(dashboard, "team_summary"):
            data = dashboard.team_summary(team_id=team_id)
        else:
            # Fallback: derive from daily report if present
            data = {"teams": [], "note": "team_summary_not_implemented"}
        return {"ok": True, "team_id": team_id, "data": data, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}
