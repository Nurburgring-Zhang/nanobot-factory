"""P4-10-W1: Plans module tests (3 tests)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend is on path
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from billing.plans import (
    FEATURE_DIMENSIONS, FEATURE_LABELS, PLAN_CATALOG, PLAN_CONFIGS,
    get_plan, get_config, get_plan_with_config, list_plans,
    tier_rank, is_upgrade, is_downgrade, price_for,
)
from billing.seed_data import get_seed_plans, get_feature_dimensions, get_seed_plan_ids


class TestPlanCatalog:
    """5 plan tiers with proper structure."""

    def test_001_five_plans_in_canonical_order(self):
        """Catalog has 5 plans: free → starter → pro → business → enterprise."""
        plans = list_plans()
        assert len(plans) == 5
        ids = [p.plan_id for p in plans]
        assert ids == ["free", "starter", "pro", "business", "enterprise"]

    def test_002_twelve_feature_dimensions(self):
        """Exactly 12 feature dimensions, used by quotas.py."""
        assert len(FEATURE_DIMENSIONS) == 12
        assert len(FEATURE_LABELS) == 12
        expected = {
            "datasets", "tasks", "operator_calls", "ai_tokens", "storage_gb",
            "team_members", "tickets", "audit_retention_days", "sla_uptime",
            "exports_per_month", "integrations", "white_label",
        }
        assert set(FEATURE_DIMENSIONS) == expected

    def test_003_prices_match_spec(self):
        """Prices in cents match the spec: Free $0, Starter $29, Pro $99, Business $299, Enterprise=custom."""
        plans = {p.plan_id: p for p in PLAN_CATALOG}
        assert plans["free"].monthly_price_usd == 0
        assert plans["free"].monthly_price_cny == 0
        assert plans["starter"].monthly_price_usd == 2900  # $29
        assert plans["starter"].monthly_price_cny == 2900  # ¥29
        assert plans["pro"].monthly_price_usd == 9900  # $99
        assert plans["pro"].monthly_price_cny == 9900  # ¥99
        assert plans["business"].monthly_price_usd == 29900  # $299
        assert plans["business"].monthly_price_cny == 29900  # ¥299
        assert plans["enterprise"].is_custom is True
        assert plans["enterprise"].monthly_price_usd == 0


class TestPlanLookup:
    """Lookup functions."""

    def test_004_get_plan_returns_correct_object(self):
        p = get_plan("pro")
        assert p.plan_id == "pro"
        assert p.tier == "pro"
        with pytest.raises(KeyError):
            get_plan("nonexistent")

    def test_005_get_config_returns_12dim_limits(self):
        cfg = get_config("pro")
        assert cfg.plan_id == "pro"
        assert len(cfg.limits) == 12
        assert cfg.limits["datasets"] == 100
        assert cfg.limits["ai_tokens"] == 1_000_000
        assert "operator_calls" in cfg.overflow_policy

    def test_006_get_plan_with_config_dict(self):
        d = get_plan_with_config("business")
        assert d["plan_id"] == "business"
        assert d["monthly_price_usd"] == 29900
        assert d["limits"]["team_members"] == 50
        assert d["limits"]["sla_uptime"] == 999


class TestUpgradeDowngrade:
    """Plan transition logic."""

    def test_007_tier_rank_ordering(self):
        assert tier_rank("free") < tier_rank("starter")
        assert tier_rank("starter") < tier_rank("pro")
        assert tier_rank("pro") < tier_rank("business")
        assert tier_rank("business") < tier_rank("enterprise")

    def test_008_is_upgrade_downgrade(self):
        assert is_upgrade("free", "pro") is True
        assert is_upgrade("pro", "free") is False
        assert is_downgrade("pro", "free") is True
        assert is_upgrade("pro", "pro") is False
        assert is_downgrade("pro", "pro") is False

    def test_009_price_for_monthly_yearly(self):
        # Pro monthly USD
        assert price_for("pro", "monthly", "usd") == 9900
        # Pro monthly CNY
        assert price_for("pro", "monthly", "cny") == 9900
        # Pro yearly USD (10x monthly = 99000, but our spec = 99000)
        assert price_for("pro", "yearly", "usd") == 99000
        with pytest.raises(ValueError):
            price_for("pro", "weekly", "usd")


class TestSeedData:
    """Seed data module for first-run."""

    def test_010_seed_plans_returns_5(self):
        plans = get_seed_plans()
        assert len(plans) == 5
        assert plans[0]["plan_id"] == "free"

    def test_011_feature_dimensions_helper(self):
        dims = get_feature_dimensions()
        assert len(dims) == 12
        assert "ai_tokens" in dims

    def test_012_seed_plan_ids_canonical_order(self):
        ids = get_seed_plan_ids()
        assert ids == ["free", "starter", "pro", "business", "enterprise"]
