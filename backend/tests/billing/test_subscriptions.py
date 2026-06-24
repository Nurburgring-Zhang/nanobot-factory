"""P4-10-W1: Subscription tests (3+ tests)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.subscriptions import (
    Subscription, SubscriptionService, SubscriptionStatus,
    InMemorySubscriptionStore, JsonlSubscriptionStore,
    LoggingNotificationHook, BILLING_SUBSCRIPTIONS_DDL,
    BILLING_SUBSCRIPTIONS_DDL_SQLITE,
)
from billing.orders import OrderService, InMemoryOrderStore


class TestSubscriptionCreate:
    def test_001_create_basic_subscription(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc, LoggingNotificationHook())
        sub = svc.create(user_id="u1", plan_id="pro", period="monthly", currency="USD")
        assert sub.subscription_id.startswith("sub_")
        assert sub.user_id == "u1"
        assert sub.plan_id == "pro"
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.current_period_start != sub.current_period_end
        assert sub.cancel_at_period_end is False

    def test_002_duplicate_active_subscription_raises(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        svc.create(user_id="u1", plan_id="pro")
        with pytest.raises(ValueError):
            svc.create(user_id="u1", plan_id="business")


class TestSubscriptionChangePlan:
    def test_003_upgrade_charges_difference(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        svc.create(user_id="u1", plan_id="starter", period="monthly", currency="USD")
        result = svc.change_plan(user_id="u1", new_plan_id="pro",
                                 period="monthly", currency="USD")
        assert result["direction"] == "upgrade"
        assert result["old_plan_id"] == "starter"
        assert result["new_plan_id"] == "pro"
        assert result["prorated_amount_cents"] >= 0
        # sub now has pro
        sub = svc.get_by_user("u1")
        assert sub.plan_id == "pro"

    def test_004_downgrade_credits_difference(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        svc.create(user_id="u1", plan_id="pro", period="monthly", currency="USD")
        result = svc.change_plan(user_id="u1", new_plan_id="starter",
                                 period="monthly", currency="USD")
        assert result["direction"] == "downgrade"
        # Downgrade: prorated_amount should be negative (credit)
        assert result["prorated_amount_cents"] <= 0


class TestSubscriptionCancel:
    def test_005_cancel_at_period_end(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        svc.create(user_id="u1", plan_id="pro")
        sub = svc.cancel(user_id="u1", at_period_end=True)
        assert sub.cancel_at_period_end is True
        assert sub.status == SubscriptionStatus.ACTIVE  # still active until period end

    def test_006_cancel_immediately(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        svc.create(user_id="u1", plan_id="pro")
        sub = svc.cancel(user_id="u1", at_period_end=False)
        assert sub.status == SubscriptionStatus.CANCELLED


class TestSubscriptionRenewal:
    def test_007_renewal_creates_order(self):
        store = InMemorySubscriptionStore()
        order_store = InMemoryOrderStore()
        order_svc = OrderService(order_store)
        svc = SubscriptionService(store, order_svc)
        sub = svc.create(user_id="u1", plan_id="pro")
        order = svc.renew(sub.subscription_id, payment_method="mock")
        assert order.amount_cents == 9900  # Pro monthly
        assert order.metadata.get("kind") == "renewal"
        assert order.metadata.get("subscription_id") == sub.subscription_id
        # Mark renewal succeeded
        sub2 = svc.mark_renewal_succeeded(sub.subscription_id)
        assert sub2.status == SubscriptionStatus.ACTIVE

    def test_008_renewal_failed_sets_past_due(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        sub = svc.create(user_id="u1", plan_id="pro")
        sub2 = svc.mark_renewal_failed(sub.subscription_id, reason="card_declined")
        assert sub2.status == SubscriptionStatus.PAST_DUE


class TestRenewalCron:
    def test_009_cron_sends_reminder_at_7_days(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        hook = LoggingNotificationHook()
        svc = SubscriptionService(store, order_svc, hook, renewal_window_days=7)
        sub = svc.create(user_id="u1", plan_id="pro")
        # Force period_end to 7 days from now
        new_end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        sub.current_period_end = new_end
        store.save(sub)
        result = svc.run_renewal_cron(dry_run=False)
        assert result["reminders_sent"] >= 1
        assert result["dry_run"] is False

    def test_010_cron_expires_cancelled(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        sub = svc.create(user_id="u1", plan_id="pro")
        # Cancel at period end
        svc.cancel(user_id="u1", at_period_end=True)
        # Force period_end to past
        sub = store.get(sub.subscription_id)
        sub.current_period_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        store.save(sub)
        result = svc.run_renewal_cron(dry_run=False)
        assert result["expired"] >= 1
        sub2 = store.get(sub.subscription_id)
        assert sub2.status == SubscriptionStatus.EXPIRED

    def test_011_cron_dry_run(self):
        store = InMemorySubscriptionStore()
        order_svc = OrderService(InMemoryOrderStore())
        svc = SubscriptionService(store, order_svc)
        sub = svc.create(user_id="u1", plan_id="pro")
        sub.current_period_end = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        store.save(sub)
        result = svc.run_renewal_cron(dry_run=True)
        assert result["dry_run"] is True
        # No actual renewal happened
        sub2 = store.get(sub.subscription_id)
        assert sub2.last_renewal_order_id is None


class TestSubscriptionJsonlStore:
    def test_012_jsonl_persistence(self, tmp_path):
        path = tmp_path / "subs.jsonl"
        s1 = JsonlSubscriptionStore(str(path))
        sub = Subscription(
            subscription_id="sub_test1", user_id="u1", plan_id="pro",
            status=SubscriptionStatus.ACTIVE,
            current_period_start="2026-06-24T00:00:00+00:00",
            current_period_end="2026-07-24T00:00:00+00:00",
            cancel_at_period_end=False,
            created_at="2026-06-24T00:00:00+00:00",
            updated_at="2026-06-24T00:00:00+00:00",
        )
        s1.save(sub)
        s2 = JsonlSubscriptionStore(str(path))
        fetched = s2.get("sub_test1")
        assert fetched is not None
        assert fetched.plan_id == "pro"


class TestSubscriptionSQL:
    def test_013_ddl_present(self):
        assert "billing_subscriptions" in BILLING_SUBSCRIPTIONS_DDL
        assert "billing_subscriptions" in BILLING_SUBSCRIPTIONS_DDL_SQLITE
        assert "cancel_at_period_end" in BILLING_SUBSCRIPTIONS_DDL
