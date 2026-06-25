"""
P6-Fix-C-5: SLA breach monitor tests
======================================

Covers the two P0 contract clauses:
1. **At-risk detection** — tickets whose deadline is approaching within the
   configured warning window are flagged *before* the deadline (P0 30min,
   P1 1h, P2 4h, P3 12h).
2. **Breached escalation** — tickets whose deadline has passed are flagged
   for upgrade; their ``sla_breached`` flag flips True and a
   ``ticket_sla_breach`` entry is appended to ``oncall.log``.

Also covers the Celery task wrapper to confirm the periodic entry-point
returns a structured summary and dispatches the expected number of alerts.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tickets import _TICKETS, create_ticket, add_ticket_comment  # noqa: E402
from tickets.sla_monitor import (  # noqa: E402
    BreachAlert,
    BreachReport,
    DEFAULT_WARNING_WINDOWS_MIN,
    TERMINAL_STATES,
    check_sla_breach,
    dispatch_alerts,
)
from tickets.tasks.sla_monitor import run_sla_breach_check  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Reset ticket store + isolate oncall log between tests."""
    # Clear the in-memory ticket store
    _TICKETS.clear()
    # Sandbox the oncall log
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("ONCALL_LOG_DIR", str(log_dir))
    monkeypatch.setenv("ONCALL_WEBHOOK_URL", "")
    yield
    _TICKETS.clear()


@pytest.fixture
def now() -> datetime:
    """Fixed reference time — 2026-06-25 12:00:00 UTC."""
    return datetime(2026, 6, 25, 12, 0, 0)


# ---------------------------------------------------------------------------
# 1. At-risk detection (early warning BEFORE deadline)
# ---------------------------------------------------------------------------

def test_p0_at_risk_detected_within_30min_before_deadline(now):
    """P0 SLA = 1h. Deadline 15 min from now → in warning window (30 min)."""
    t = create_ticket(
        ticket_type="incident",
        priority="P0",
        subject="服务降级",
        description="...",
    )
    # Rewind created_at so the deadline is 15 min from `now`
    t.created_at = (now - timedelta(minutes=45)).isoformat()
    t.sla_deadline = (now + timedelta(minutes=15)).isoformat()

    report = check_sla_breach(now=now)
    assert report.scanned == 1
    assert len(report.at_risk) == 1
    assert len(report.breached) == 0
    a = report.at_risk[0]
    assert a.ticket_id == t.ticket_id
    assert a.priority == "P0"
    assert a.is_at_risk is True
    assert a.is_breached is False
    assert 14.0 < a.minutes_to_deadline < 16.0


def test_p1_at_risk_detected_within_1h_before_deadline(now):
    """P1 SLA = 4h. Deadline 30 min from now → in P1 warning window (60 min)."""
    t = create_ticket(
        ticket_type="problem",
        priority="P1",
        subject="重要功能异常",
        description="...",
    )
    # Created 3h30min ago → deadline 30 min from `now`
    t.created_at = (now - timedelta(minutes=210)).isoformat()
    t.sla_deadline = (now + timedelta(minutes=30)).isoformat()

    report = check_sla_breach(now=now)
    assert len(report.at_risk) == 1
    a = report.at_risk[0]
    assert a.priority == "P1"
    assert a.is_at_risk is True
    assert a.is_breached is False


def test_p2_p3_at_risk_within_warning_windows(now):
    """P2 (4h window) and P3 (12h window) at-risk detection."""
    t_p2 = create_ticket(ticket_type="problem", priority="P2", subject="p2", description="x")
    t_p2.created_at = (now - timedelta(hours=20)).isoformat()
    t_p2.sla_deadline = (now + timedelta(hours=3, minutes=59)).isoformat()  # within 4h window

    t_p3 = create_ticket(ticket_type="problem", priority="P3", subject="p3", description="x")
    t_p3.created_at = (now - timedelta(hours=60)).isoformat()
    t_p3.sla_deadline = (now + timedelta(hours=11, minutes=59)).isoformat()  # within 12h window

    report = check_sla_breach(now=now)
    priorities = sorted(a.priority for a in report.at_risk)
    assert priorities == ["P2", "P3"]


def test_ticket_outside_warning_window_is_not_at_risk(now):
    """P2 with deadline 6h away → outside the 4h warning window → not flagged."""
    t = create_ticket(ticket_type="problem", priority="P2", subject="safe", description="x")
    t.created_at = (now - timedelta(hours=18)).isoformat()
    t.sla_deadline = (now + timedelta(hours=6)).isoformat()

    report = check_sla_breach(now=now)
    assert report.scanned == 0
    assert report.at_risk == []
    assert report.breached == []


# ---------------------------------------------------------------------------
# 2. Breach detection (deadline passed)
# ---------------------------------------------------------------------------

def test_p0_breach_detected_after_deadline(now):
    """P0 deadline passed by 10 min → breach flag flipped + oncall log entry."""
    t = create_ticket(ticket_type="incident", priority="P0", subject="严重事故", description="...")
    # Created 1h 10min ago → deadline passed 10 min ago
    t.created_at = (now - timedelta(minutes=70)).isoformat()
    t.sla_deadline = (now - timedelta(minutes=10)).isoformat()

    counters = _run_with_logging(now=now)
    assert counters["p0_breach_alerts"] == 1
    assert counters["p1_breach_alerts"] == 0
    # Ticket flag should be flipped
    assert t.sla_breached is True

    report = check_sla_breach(now=now)
    assert len(report.breached) == 1
    assert report.breached[0].priority == "P0"
    assert report.breached[0].is_breached is True
    assert report.breached[0].minutes_to_deadline <= 0


def test_p1_breach_escalation_within_4h(now):
    """P1 deadline passed 1h ago → flagged as breached (4h escalation clause)."""
    t = create_ticket(ticket_type="problem", priority="P1", subject="影响业务", description="...")
    t.created_at = (now - timedelta(hours=5)).isoformat()
    t.sla_deadline = (now - timedelta(hours=1)).isoformat()

    counters = _run_with_logging(now=now)
    assert counters["p1_breach_alerts"] == 1
    assert t.sla_breached is True


def test_breached_and_at_risk_classified_separately(now):
    """Both buckets populated and kept disjoint."""
    # P2 already breached
    t1 = create_ticket(ticket_type="problem", priority="P2", subject="breached", description="x")
    t1.created_at = (now - timedelta(hours=30)).isoformat()
    t1.sla_deadline = (now - timedelta(hours=6)).isoformat()
    # P1 at risk (deadline in 30 min, within 1h warning)
    t2 = create_ticket(ticket_type="problem", priority="P1", subject="at-risk", description="x")
    t2.created_at = (now - timedelta(hours=3, minutes=30)).isoformat()
    t2.sla_deadline = (now + timedelta(minutes=30)).isoformat()

    report = check_sla_breach(now=now)
    assert report.scanned == 2
    assert len(report.breached) == 1
    assert len(report.at_risk) == 1
    assert report.breached[0].ticket_id == t1.ticket_id
    assert report.at_risk[0].ticket_id == t2.ticket_id
    # Mutually exclusive flags
    for a in report.breached + report.at_risk:
        assert a.is_breached != a.is_at_risk


# ---------------------------------------------------------------------------
# 3. Negative cases — terminal states, malformed timestamps, etc.
# ---------------------------------------------------------------------------

def test_resolved_or_closed_tickets_are_skipped(now):
    """SLA no longer applies to resolved/closed tickets."""
    t = create_ticket(ticket_type="problem", priority="P0", subject="done", description="x")
    t.created_at = (now - timedelta(hours=2)).isoformat()
    t.sla_deadline = (now - timedelta(hours=1)).isoformat()
    t.status = "resolved"

    report = check_sla_breach(now=now)
    assert report.scanned == 0
    assert report.breached == []


def test_invalid_priority_is_ignored(now):
    """A ticket with bogus priority must not crash the scanner.

    We bypass ``create_ticket`` (which validates priority) by constructing a
    Ticket via ``__new__`` + attribute assignment, then register it directly
    into ``_TICKETS``.
    """
    from tickets import Ticket
    t = Ticket.__new__(Ticket)
    t.ticket_id = "TK-TEST-BAD-P0"
    t.type = "problem"
    t.priority = "P9"  # bogus
    t.subject = "bad"
    t.description = "x"
    t.status = "new"
    t.assignee = None
    t.created_at = now.isoformat()
    t.sla_deadline = (now - timedelta(minutes=5)).isoformat()
    _TICKETS[t.ticket_id] = t

    report = check_sla_breach(now=now)
    # No crash; bad priority => silently skipped
    assert report.scanned == 0


def test_malformed_sla_deadline_is_ignored(now):
    """Garbage deadline → scanner continues, doesn't raise."""
    t = create_ticket(ticket_type="problem", priority="P0", subject="weird", description="x")
    t.sla_deadline = "not-a-datetime"
    report = check_sla_breach(now=now)
    assert report.scanned == 0


# ---------------------------------------------------------------------------
# 4. Dispatch side-effects (oncall.log entries)
# ---------------------------------------------------------------------------

def test_dispatch_writes_oncall_log_for_each_breach(now, tmp_path):
    """dispatch_alerts writes a JSON line per breach + per at-risk.

    Uses P2/P3 priorities to avoid the immediate ``ticket_p0_created``
    notification that ``create_ticket`` fires for P0 tickets — otherwise
    those lines would pollute the log and confuse the assertion.
    """
    # 2 P2 breaches, 1 P3 at-risk
    for i in range(2):
        t = create_ticket(ticket_type="problem", priority="P2", subject=f"p2-{i}", description="x")
        t.created_at = (now - timedelta(hours=30)).isoformat()
        t.sla_deadline = (now - timedelta(minutes=10 + i)).isoformat()
    tp3 = create_ticket(ticket_type="problem", priority="P3", subject="p3-warn", description="x")
    tp3.created_at = (now - timedelta(hours=60, minutes=-1)).isoformat()  # ~60h ago
    tp3.sla_deadline = (now + timedelta(hours=11, minutes=59)).isoformat()  # within 12h window

    report = check_sla_breach(now=now)
    counters = dispatch_alerts(report)
    assert counters["p2_breach_alerts"] == 2
    assert counters["at_risk_warnings"] == 1

    log_file = tmp_path / "logs" / "oncall.log"
    assert log_file.exists()
    lines = [ln for ln in log_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    parsed = [json.loads(ln) for ln in lines]
    events = [e["event"] for e in parsed]
    assert events.count("ticket_sla_breach") == 2
    assert events.count("ticket_sla_at_risk") == 1
    # Severity is warning for P2/P3 breaches (only P0/P1 are critical)
    for e in parsed:
        if e["event"] == "ticket_sla_breach" and e["priority"] in ("P2", "P3"):
            assert e["severity"] == "warning"


# ---------------------------------------------------------------------------
# 5. Celery task wrapper
# ---------------------------------------------------------------------------

def test_celery_task_name_registered():
    """Task is registered under its qualified name (beats schedule uses it)."""
    assert run_sla_breach_check.name == "tickets.tasks.sla_monitor.run_sla_breach_check"


def test_celery_beat_schedule_contains_sla_task():
    """The 30-min beat schedule entry points at the SLA task."""
    from imdf.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule or {}
    entry = schedule.get("sla-breach-check-every-30min")
    assert entry is not None
    assert entry["task"] == "tickets.tasks.sla_monitor.run_sla_breach_check"
    # 30 minutes = 1800 seconds
    assert float(entry["schedule"]) == 1800.0


def test_run_sla_breach_check_eager_returns_summary(now):
    """Calling the task body directly returns the JSON-safe summary dict."""
    # Set up a P0 breach + a P2 at-risk
    t0 = create_ticket(ticket_type="incident", priority="P0", subject="prod-down", description="x")
    t0.created_at = (now - timedelta(minutes=70)).isoformat()
    t0.sla_deadline = (now - timedelta(minutes=5)).isoformat()
    t2 = create_ticket(ticket_type="problem", priority="P2", subject="slow", description="x")
    t2.created_at = (now - timedelta(hours=20)).isoformat()
    t2.sla_deadline = (now + timedelta(hours=3)).isoformat()

    # Patch datetime.utcnow used inside the task so report/alert timestamps align
    import tickets.sla_monitor as sm
    orig_classify_dt = sm._parse_dt
    real_now = now
    sm._parse_dt = orig_classify_dt  # keep original parser
    # Inject `now` indirectly by monkey-patching datetime used inside check_sla_breach

    class _FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return real_now

    import tickets.sla_monitor as sm_mod
    orig_dt = sm_mod.datetime
    sm_mod.datetime = _FrozenDateTime
    try:
        result = run_sla_breach_check.apply().get()
    finally:
        sm_mod.datetime = orig_dt

    assert result["ok"] is True
    assert result["scanned"] == 2
    assert result["breached_count"] == 1
    assert result["at_risk_count"] == 1
    assert result["alerts"]["p0_breach_alerts"] == 1
    assert result["alerts"]["at_risk_warnings"] == 1


def test_run_sla_breach_check_empty_store_returns_zero(now, tmp_path):
    """No open tickets → scanned=0, no alerts dispatched."""
    import tickets.sla_monitor as sm_mod

    class _FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return now

    orig_dt = sm_mod.datetime
    sm_mod.datetime = _FrozenDateTime
    try:
        result = run_sla_breach_check.apply().get()
    finally:
        sm_mod.datetime = orig_dt

    assert result["ok"] is True
    assert result["scanned"] == 0
    assert result["breached_count"] == 0
    assert result["at_risk_count"] == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_with_logging(now: datetime) -> dict:
    """Run check_sla_breach + dispatch_alerts together; return counters."""
    report = check_sla_breach(now=now)
    return dispatch_alerts(report)
