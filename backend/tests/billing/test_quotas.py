"""P4-10-W1: Quota tests (4+ tests).

Covers:
- 12-dimension soft/hard limits
- consume() atomic check + record
- snapshot() with all dimensions
- upgrade flow frees / tightens limits
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.quotas import (
    QuotaService, QuotaLevel, InMemoryQuotaTracker, JsonlQuotaTracker,
    SOFT_THRESHOLD_PCT, BILLING_USAGE_LOG_DDL, BILLING_USAGE_LOG_DDL_SQLITE,
)
from billing.plans import FEATURE_DIMENSIONS, get_config


class TestQuotaCheck:
    def test_001_check_within_limits_allows(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker, soft_threshold_pct=0.8)
        d = svc.check("u1", "pro", "datasets", qty=10)
        assert d.level == QuotaLevel.OK
        assert d.allowed is True
        assert d.current == 0
        assert d.limit == 100  # pro datasets limit

    def test_002_soft_warning_at_80_percent(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker, soft_threshold_pct=0.8)
        # Pro datasets limit = 100; consume 80 first
        for _ in range(80):
            tracker.record("u1", "datasets")
        # Consume 1 more — should be soft warning
        d = svc.check("u1", "pro", "datasets", qty=1)
        assert d.level == QuotaLevel.SOFT_WARNING
        assert d.allowed is True
        assert d.reason.startswith("approaching")

    def test_003_hard_block_at_100_percent(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker, soft_threshold_pct=0.8)
        # Fill to 100
        for _ in range(100):
            tracker.record("u1", "datasets")
        d = svc.check("u1", "pro", "datasets", qty=1)
        assert d.level == QuotaLevel.HARD_BLOCK
        assert d.allowed is False
        assert "exceeded" in d.reason

    def test_004_free_plan_zero_limit_blocks(self):
        """Free plan has 0 for tickets → hard block."""
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker, soft_threshold_pct=0.8)
        d = svc.check("u1", "free", "tickets", qty=1)
        assert d.level == QuotaLevel.HARD_BLOCK
        assert d.allowed is False
        assert "does not include" in d.reason


class TestQuotaConsume:
    def test_005_consume_atomic_record(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        # Consume 5 — allowed
        d1 = svc.consume("u1", "pro", "datasets", 5)
        assert d1.allowed
        assert tracker.current("u1", "datasets") == 5
        # Consume 95 more — should be allowed
        d2 = svc.consume("u1", "pro", "datasets", 95)
        assert d2.allowed
        assert tracker.current("u1", "datasets") == 100
        # 1 more — blocked
        d3 = svc.consume("u1", "pro", "datasets", 1)
        assert not d3.allowed
        assert tracker.current("u1", "datasets") == 100  # not recorded

    def test_006_consume_with_block_records_when_flagged(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        for _ in range(100):
            tracker.record("u1", "datasets")
        # Block + record_on_block
        d = svc.consume("u1", "pro", "datasets", 1, record_on_block=True)
        assert not d.allowed
        assert tracker.current("u1", "datasets") == 101


class TestQuotaSnapshot:
    def test_007_snapshot_all_12_dimensions(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        tracker.record("u1", "datasets", 50)
        tracker.record("u1", "ai_tokens", 800_000)  # 80% of 1M
        snap = svc.snapshot("u1", "pro")
        assert snap["user_id"] == "u1"
        assert snap["plan_id"] == "pro"
        assert len(snap["dimensions"]) == 12
        ds = snap["dimensions"]["datasets"]
        assert ds["current"] == 50
        assert ds["limit"] == 100
        assert ds["level"] == "ok"
        # ai_tokens: 800k/1M = 80% — soft warning
        ai = snap["dimensions"]["ai_tokens"]
        assert ai["current"] == 800_000
        assert ai["level"] == "soft_warning"

    def test_008_enterprise_unlimited_returns_infinity(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        snap = svc.snapshot("u1", "enterprise")
        # 10 of 12 dimensions are unlimited (sla_uptime + white_label are specific values)
        unlimited_dims = ["datasets", "tasks", "operator_calls", "ai_tokens",
                          "storage_gb", "team_members", "tickets",
                          "audit_retention_days", "exports_per_month", "integrations"]
        for dim in unlimited_dims:
            info = snap["dimensions"][dim]
            assert info["level"] == "infinity", f"{dim} should be infinity, got {info['level']}"
            assert info["allowed"] is True
        # sla_uptime + white_label: 99.99% and 1 respectively
        assert snap["dimensions"]["sla_uptime"]["level"] == "ok"
        assert snap["dimensions"]["white_label"]["level"] == "ok"


class TestQuotaUnknown:
    def test_009_unknown_plan_returns_unknown_level(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        d = svc.check("u1", "nonexistent", "datasets", 1)
        assert d.level == QuotaLevel.UNKNOWN
        assert d.allowed is False

    def test_010_unknown_dimension_returns_unknown(self):
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        d = svc.check("u1", "pro", "fake_dimension", 1)
        assert d.level == QuotaLevel.UNKNOWN
        assert d.allowed is False


class TestQuotaUpgradeScenario:
    def test_011_upgrade_from_free_to_pro_relaxes_limits(self):
        """User on free plan, dataset limit 3; upgrade to pro (100)."""
        tracker = InMemoryQuotaTracker()
        svc = QuotaService(tracker)
        # Free plan: 3 datasets
        for _ in range(3):
            tracker.record("u1", "datasets")
        d_free = svc.check("u1", "free", "datasets", 1)
        assert not d_free.allowed
        # Upgrade to pro: same usage, but limit is now 100
        d_pro = svc.check("u1", "pro", "datasets", 1)
        assert d_pro.allowed
        assert d_pro.level == QuotaLevel.OK


class TestJsonlQuotaTracker:
    def test_012_jsonl_persistence(self, tmp_path):
        path = tmp_path / "quota.jsonl"
        t1 = JsonlQuotaTracker(str(path))
        t1.record("u1", "datasets", 10)
        t1.record("u1", "ai_tokens", 5000)
        t2 = JsonlQuotaTracker(str(path))
        assert t2.current("u1", "datasets") == 10
        assert t2.current("u1", "ai_tokens") == 5000
        snap = t2.snapshot("u1")
        assert snap == {"datasets": 10, "ai_tokens": 5000}


class TestSQL:
    def test_013_billing_usage_log_ddl(self):
        assert "billing_usage_log" in BILLING_USAGE_LOG_DDL
        assert "billing_usage_log" in BILLING_USAGE_LOG_DDL_SQLITE
        assert "user_id" in BILLING_USAGE_LOG_DDL
