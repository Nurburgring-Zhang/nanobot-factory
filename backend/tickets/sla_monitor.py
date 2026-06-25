"""
P6-Fix-C-5: SLA breach monitor
================================

Scans the in-memory `_TICKETS` registry for tickets whose SLA deadline is
either about to be breached (early warning) or has already been breached
(needs upgrade / escalation).

Key requirements (from nanobot-factory P6-6 P0 fix):
- P0 ticket must trigger an alert within 1h of deadline → ``check_sla_breach``
  classifies a ticket as ``at_risk`` when the remaining time-to-deadline is
  less than the configured warning window (default 30 min for P0).
- P1 ticket must be escalated within 4h → similar early-warning logic with
  a 4h warning window for P1.
- Already-breached tickets (past ``sla_deadline``) are returned in the
  ``breached`` list regardless of priority; the caller (Celery beat task or
  oncall dispatcher) decides whether to fire a PagerDuty-style escalation.

This module is **decoupled** from the Celery beat task — it returns plain
dicts, so unit tests can verify the detection logic without spinning up a
broker. The Celery task in ``tickets.tasks.sla_monitor`` wraps this and
emits ``oncall.log`` entries plus metrics counters.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import _TICKETS, Ticket, PRIORITIES, SLA_HOURS  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Warning windows — how early we want to be alerted BEFORE the deadline
# ---------------------------------------------------------------------------
# P0 = 1h SLA → 30min early warning → ops has time to act within the 1h window.
# P1 = 4h SLA → 1h early warning.
# P2 = 24h SLA → 4h early warning.
# P3 = 72h SLA → 12h early warning.
DEFAULT_WARNING_WINDOWS_MIN: Dict[str, int] = {
    "P0": 30,
    "P1": 60,
    "P2": 240,
    "P3": 720,
}

# Terminal states — no SLA monitoring needed
TERMINAL_STATES = {"resolved", "closed"}


@dataclass
class BreachAlert:
    """A single breach / at-risk alert entry."""

    ticket_id: str
    priority: str
    status: str
    created_at: str
    sla_deadline: str
    minutes_to_deadline: float  # negative => already breached
    is_breached: bool
    is_at_risk: bool
    assignee: Optional[str]
    subject: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BreachReport:
    """Aggregate result from one ``check_sla_breach()`` invocation."""

    at_risk: List[BreachAlert] = field(default_factory=list)
    breached: List[BreachAlert] = field(default_factory=list)
    scanned: int = 0
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanned": self.scanned,
            "at_risk_count": len(self.at_risk),
            "breached_count": len(self.breached),
            "at_risk": [a.to_dict() for a in self.at_risk],
            "breached": [a.to_dict() for a in self.breached],
            "generated_at": self.generated_at,
        }


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _minutes_between(now: datetime, target: datetime) -> float:
    return (target - now).total_seconds() / 60.0


def _classify_ticket(
    ticket: Ticket,
    *,
    now: datetime,
    warning_windows_min: Dict[str, int],
) -> Optional[BreachAlert]:
    """Return a BreachAlert for ``ticket`` if it needs attention, else None."""
    # Skip terminal-state tickets (resolved/closed) — SLA is no longer live
    if ticket.status in TERMINAL_STATES:
        return None
    if ticket.priority not in PRIORITIES:
        return None
    deadline = _parse_dt(ticket.sla_deadline)
    if deadline is None:
        return None

    minutes_to_deadline = _minutes_between(now, deadline)
    is_breached = minutes_to_deadline <= 0
    warning_min = warning_windows_min.get(ticket.priority, 60)
    is_at_risk = (not is_breached) and minutes_to_deadline <= warning_min

    if not (is_breached or is_at_risk):
        return None

    return BreachAlert(
        ticket_id=ticket.ticket_id,
        priority=ticket.priority,
        status=ticket.status,
        created_at=ticket.created_at,
        sla_deadline=ticket.sla_deadline,
        minutes_to_deadline=round(minutes_to_deadline, 2),
        is_breached=is_breached,
        is_at_risk=is_at_risk,
        assignee=ticket.assignee,
        subject=ticket.subject,
        type=ticket.type,
    )


def check_sla_breach(
    *,
    now: Optional[datetime] = None,
    warning_windows_min: Optional[Dict[str, int]] = None,
    tickets: Optional[Dict[str, Ticket]] = None,
) -> BreachReport:
    """Scan all open tickets for SLA breach / near-breach.

    Args:
        now: Override the current time (used by tests).
        warning_windows_min: Override default warning windows (per priority).
        tickets: Override the ticket store (used by tests). Defaults to the
            module-level ``_TICKETS`` dict from ``tickets.__init__``.

    Returns:
        BreachReport with ``at_risk`` (warning fired but not yet breached)
        and ``breached`` (deadline passed) buckets.
    """
    if now is None:
        now = datetime.utcnow()
    if warning_windows_min is None:
        warning_windows_min = DEFAULT_WARNING_WINDOWS_MIN
    if tickets is None:
        tickets = _TICKETS

    report = BreachReport()
    for t in tickets.values():
        alert = _classify_ticket(
            t,
            now=now,
            warning_windows_min=warning_windows_min,
        )
        if alert is None:
            continue
        if alert.is_breached:
            report.breached.append(alert)
            # Mark the ticket itself so the next ``sla_stats`` reflects it
            try:
                t.sla_breached = True
            except Exception:
                pass
        else:
            report.at_risk.append(alert)
        report.scanned += 1

    # Sort: most-overdue first, then soonest-to-deadline
    report.breached.sort(key=lambda a: a.minutes_to_deadline)
    report.at_risk.sort(key=lambda a: a.minutes_to_deadline)
    return report


# ---------------------------------------------------------------------------
# Notification helpers — write to oncall.log (same fallback as create_ticket)
# ---------------------------------------------------------------------------
# NOTE: read env var PER CALL (tests set ONCALL_LOG_DIR via monkeypatch).
_ONCALL_LOG_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "logs",
)


def _append_oncall_log(entry: Dict[str, Any]) -> None:
    """Append one JSON line to the oncall.log (best-effort, never raises)."""
    import json
    try:
        log_dir = os.getenv("ONCALL_LOG_DIR") or _ONCALL_LOG_DEFAULT_DIR
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "oncall.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to write oncall.log: %s", exc)


def dispatch_alerts(report: BreachReport) -> Dict[str, int]:
    """Persist breach alerts to oncall.log; return counter for tests/metrics.

    This is the side-effecting companion of ``check_sla_breach``:
    - Each P0/P1 breach → high-severity log entry (escalation hook).
    - Each P2/P3 at-risk → low-severity log entry (warning).
    - All other at-risk → info-level entry.
    """
    counters = {
        "p0_breach_alerts": 0,
        "p1_breach_alerts": 0,
        "p2_breach_alerts": 0,
        "p3_breach_alerts": 0,
        "at_risk_warnings": 0,
    }
    for alert in report.breached:
        severity = "critical" if alert.priority in ("P0", "P1") else "warning"
        entry = {
            "event": "ticket_sla_breach",
            "severity": severity,
            "ticket_id": alert.ticket_id,
            "priority": alert.priority,
            "overdue_minutes": -alert.minutes_to_deadline,
            "sla_deadline": alert.sla_deadline,
            "assignee": alert.assignee,
            "subject": alert.subject,
            "at": datetime.utcnow().isoformat(),
        }
        _append_oncall_log(entry)
        counters[f"{alert.priority.lower()}_breach_alerts"] += 1

    for alert in report.at_risk:
        entry = {
            "event": "ticket_sla_at_risk",
            "severity": "warning",
            "ticket_id": alert.ticket_id,
            "priority": alert.priority,
            "minutes_to_deadline": alert.minutes_to_deadline,
            "sla_deadline": alert.sla_deadline,
            "assignee": alert.assignee,
            "subject": alert.subject,
            "at": datetime.utcnow().isoformat(),
        }
        _append_oncall_log(entry)
        counters["at_risk_warnings"] += 1

    return counters


__all__ = [
    "BreachAlert",
    "BreachReport",
    "DEFAULT_WARNING_WINDOWS_MIN",
    "TERMINAL_STATES",
    "check_sla_breach",
    "dispatch_alerts",
]
