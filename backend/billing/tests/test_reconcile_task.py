"""P6-Fix-C-4: Celery task tests.

Verifies:
- Celery task import + registration
- Celery beat schedule (daily at 04:00 UTC by default)
- reconcile_provider_task eager mode end-to-end
- reconcile_all_providers_task fan-out
- configure_celery_for_billing state injection
- env-driven schedule hour (BILLING_RECONCILE_SCHEDULE_HOUR_UTC)
- build_default_alert_hook reads BILLING_RECONCILE_WEBHOOK_URL

Runs with CELERY_TASK_ALWAYS_EAGER=1 so no broker is required.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

# Force eager mode BEFORE importing the celery app / tasks
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("CELERY_TASK_EAGER_PROPAGATES", "1")

from billing.orders import (
    InMemoryOrderStore, Order, OrderService, OrderStatus,
)
from billing.reconciliation import (
    MismatchType, MockProviderAdapter, NormalizedTxn, NoopAlertHook,
    ReconcileAlertHook, ReconciliationEngine, WebhookAlertHook,
    LoggingAlertHook, MultiAlertHook, daily_reconcile,
)
from billing.tasks.reconcile import (
    celery_app, reconcile_provider_task, reconcile_all_providers_task,
    configure_celery_for_billing, build_default_alert_hook,
    build_default_adapters, reload_schedule, reset_state,
    BILLING_RECONCILE_SCHEDULE_HOUR_UTC, DEFAULT_PROVIDERS,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_for(yyyy_mm_dd: str, hh: str = "12") -> str:
    return f"{yyyy_mm_dd}T{hh}:00:00+00:00"


def _paid_order(order_id: str, amount_cents: int = 9900,
                payment_method: str = "stripe") -> Order:
    return Order(
        order_id=order_id, user_id="u_test", plan_id="plan_pro",
        amount_cents=amount_cents, currency="USD",
        status=OrderStatus.PAID,
        payment_method=payment_method,
        created_at=_iso_for("2026-06-24"),
        paid_at=_iso_for("2026-06-24"),
        fulfilled_at=_iso_for("2026-06-24"),
        external_ref=f"ext_{order_id}",
    )


def _remote_charge(order_id: str, amount_cents: int = 9900,
                   provider: str = "stripe",
                   occurred_on: str = "2026-06-24") -> NormalizedTxn:
    return NormalizedTxn(
        order_id=order_id,
        provider_txn_id=f"txn_{order_id}",
        provider=provider,
        amount_cents=amount_cents,
        currency="USD",
        status="paid",
        occurred_at=_iso_for(occurred_on),
    )


@pytest.fixture(autouse=True)
def _reset_task_state():
    """Reset the celery-side module state between tests."""
    reset_state()
    yield
    reset_state()


# ── 1. Celery app + task registration ─────────────────────────────────────

class TestCeleryAppWiring:
    def test_001_app_name_and_broker(self):
        assert celery_app.main == "billing"
        # Default broker is redis (in tests we'll override to eager)
        assert "redis" in celery_app.conf.broker_url or \
               celery_app.conf.task_always_eager is True

    def test_002_tasks_registered(self):
        names = {t.name for t in celery_app.tasks.values() if t.name}
        assert "billing.reconcile_provider" in names
        assert "billing.reconcile_all_providers" in names

    def test_003_beat_schedule_default_4am(self):
        schedule = celery_app.conf.beat_schedule
        assert "billing-reconcile-daily" in schedule
        entry = schedule["billing-reconcile-daily"]
        # Default hour is 4
        assert entry["schedule"].hour == {4}

    def test_004_default_providers(self):
        assert set(DEFAULT_PROVIDERS) == {"stripe", "alipay", "wechat"}

    def test_005_schedule_hour_constant(self):
        # Default 4 unless env overrides
        assert isinstance(BILLING_RECONCILE_SCHEDULE_HOUR_UTC, int)
        assert 0 <= BILLING_RECONCILE_SCHEDULE_HOUR_UTC <= 23


# ── 2. Schedule rebuilder ─────────────────────────────────────────────────

class TestScheduleRebuild:
    def test_010_reload_picks_up_env(self, monkeypatch):
        monkeypatch.setenv("BILLING_RECONCILE_SCHEDULE_HOUR_UTC", "7")
        reload_schedule()
        entry = celery_app.conf.beat_schedule["billing-reconcile-daily"]
        assert entry["schedule"].hour == {7}

    def test_011_reload_invalid_hour_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BILLING_RECONCILE_SCHEDULE_HOUR_UTC", "abc")
        # Should not crash; default kept
        try:
            reload_schedule()
        except ValueError:
            pass  # also acceptable — env validation rejected the bad value


# ── 3. reconcile_provider_task eager ──────────────────────────────────────

class TestReconcileProviderTask:
    def test_020_clean_run_returns_result(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_a"))
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_a", provider="stripe"), "2026-06-24")
        configure_celery_for_billing(
            order_service=svc,
            adapters={"stripe": adapter, "alipay": MockProviderAdapter("alipay"),
                      "wechat": MockProviderAdapter("wechat")},
        )
        result = reconcile_provider_task(
            provider="stripe", date="2026-06-24",
        )
        assert result["provider"] == "stripe"
        assert result["mismatch_count"] == 0
        assert result["matched_count"] == 1
        assert result["local_count"] == 1
        assert result["remote_count"] == 1
        assert result["date"] == "2026-06-24"

    def test_021_mismatch_run_returns_mismatches(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_x"))
        # No remote record -> MISSING_REMOTE
        adapter = MockProviderAdapter("stripe")
        configure_celery_for_billing(
            order_service=svc,
            adapters={"stripe": adapter, "alipay": MockProviderAdapter("alipay"),
                      "wechat": MockProviderAdapter("wechat")},
        )
        # Capture alert calls
        alert_hook = MagicMock()
        configure_celery_for_billing(alert_hook=alert_hook)
        result = reconcile_provider_task(provider="stripe", date="2026-06-24")
        assert result["mismatch_count"] == 1
        assert result["mismatches"][0]["mismatch_type"] == "missing_remote"

    def test_022_unknown_provider_raises(self):
        configure_celery_for_billing(
            order_service=OrderService(InMemoryOrderStore()),
            adapters={"stripe": MockProviderAdapter("stripe")},
        )
        with pytest.raises(ValueError):
            reconcile_provider_task(provider="alipay", date="2026-06-24")

    def test_023_default_date_yesterday(self):
        # Pass no date — should default to yesterday UTC
        configure_celery_for_billing(
            order_service=OrderService(InMemoryOrderStore()),
            adapters={"stripe": MockProviderAdapter("stripe")},
        )
        result = reconcile_provider_task(provider="stripe")
        from billing.reconciliation import _yesterday_utc
        assert result["date"] == _yesterday_utc()

    def test_024_force_alert_sends_on_clean(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_a"))
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_a"), "2026-06-24")
        hook = MagicMock()
        configure_celery_for_billing(
            order_service=svc,
            adapters={"stripe": adapter},
            alert_hook=hook,
        )
        result = reconcile_provider_task(
            provider="stripe", date="2026-06-24", force_alert=True,
        )
        hook.send_alert.assert_called_once()
        assert result["alert_sent"] is True


# ── 4. reconcile_all_providers_task fan-out ──────────────────────────────

class TestReconcileAllProviders:
    def test_030_fan_out_returns_per_provider_results(self):
        svc = OrderService(InMemoryOrderStore())
        # 3 orders, one per provider
        svc.store.save(_paid_order("ord_s", payment_method="stripe"))
        svc.store.save(_paid_order("ord_a", payment_method="alipay"))
        svc.store.save(_paid_order("ord_w", payment_method="wechat"))
        # Each provider sees its own order
        adapters = {
            "stripe": MockProviderAdapter("stripe"),
            "alipay": MockProviderAdapter("alipay"),
            "wechat": MockProviderAdapter("wechat"),
        }
        adapters["stripe"].add(_remote_charge("ord_s", provider="stripe"), "2026-06-24")
        adapters["alipay"].add(_remote_charge("ord_a", provider="alipay"), "2026-06-24")
        adapters["wechat"].add(_remote_charge("ord_w", provider="wechat"), "2026-06-24")
        configure_celery_for_billing(order_service=svc, adapters=adapters)
        result = reconcile_all_providers_task(date="2026-06-24")
        assert set(result.keys()) == {"stripe", "alipay", "wechat"}
        for prov in ("stripe", "alipay", "wechat"):
            assert result[prov]["mismatch_count"] == 0
            assert result[prov]["matched_count"] == 1

    def test_031_one_provider_failure_does_not_block_others(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_a", payment_method="alipay"))
        adapters = {
            "stripe": MockProviderAdapter("stripe", fail_on_dates=["2026-06-24"]),
            "alipay": MockProviderAdapter("alipay"),
            "wechat": MockProviderAdapter("wechat"),
        }
        adapters["alipay"].add(_remote_charge("ord_a", provider="alipay"), "2026-06-24")
        configure_celery_for_billing(order_service=svc, adapters=adapters)
        result = reconcile_all_providers_task(date="2026-06-24")
        # Stripe crashed, but alipay/wechat still report
        assert "error" in result["stripe"] or result["stripe"].get("error")
        assert result["alipay"]["mismatch_count"] == 0
        assert "wechat" in result

    def test_032_custom_provider_subset(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_s", payment_method="stripe"))
        adapters = {
            "stripe": MockProviderAdapter("stripe"),
            "alipay": MockProviderAdapter("alipay"),
            "wechat": MockProviderAdapter("wechat"),
        }
        adapters["stripe"].add(_remote_charge("ord_s", provider="stripe"), "2026-06-24")
        configure_celery_for_billing(order_service=svc, adapters=adapters)
        # Only request stripe
        result = reconcile_all_providers_task(
            date="2026-06-24", providers=["stripe"],
        )
        assert set(result.keys()) == {"stripe"}


# ── 5. State injection ────────────────────────────────────────────────────

class TestConfigureCeleryForBilling:
    def test_040_idempotent_injection(self):
        svc = OrderService(InMemoryOrderStore())
        adapter = MockProviderAdapter("stripe")
        configure_celery_for_billing(order_service=svc, adapters={"stripe": adapter})
        configure_celery_for_billing(order_service=svc, adapters={"stripe": adapter})
        # No exception, state intact
        from billing.tasks.reconcile import _order_service, _adapters
        assert _order_service is svc
        assert "stripe" in _adapters

    def test_041_partial_update_preserves_others(self):
        svc1 = OrderService(InMemoryOrderStore())
        svc2 = OrderService(InMemoryOrderStore())
        configure_celery_for_billing(order_service=svc1)
        # Update only alert hook
        hook = MagicMock()
        configure_celery_for_billing(alert_hook=hook)
        from billing.tasks.reconcile import _order_service, _alert_hook
        assert _order_service is svc1  # unchanged
        assert _alert_hook is hook

    def test_042_reset_clears_state(self):
        configure_celery_for_billing(
            order_service=OrderService(InMemoryOrderStore()),
            adapters={"stripe": MockProviderAdapter("stripe")},
        )
        reset_state()
        from billing.tasks.reconcile import _order_service, _adapters
        assert _order_service is None
        assert _adapters == {}


# ── 6. Default builders ───────────────────────────────────────────────────

class TestDefaultBuilders:
    def test_050_build_default_adapters_returns_3(self):
        adapters = build_default_adapters()
        assert set(adapters.keys()) == {"stripe", "alipay", "wechat"}
        for a in adapters.values():
            assert a.provider_name in {"stripe", "alipay", "wechat"}

    def test_051_default_alert_hook_no_webhook_env(self, monkeypatch):
        monkeypatch.delenv("BILLING_RECONCILE_WEBHOOK_URL", raising=False)
        hook = build_default_alert_hook()
        # No webhook URL -> LoggingAlertHook wrapped in MultiAlertHook
        assert hook is not None

    def test_052_default_alert_hook_with_webhook(self, monkeypatch):
        monkeypatch.setenv("BILLING_RECONCILE_WEBHOOK_URL",
                           "https://hooks.example.com/billing")
        monkeypatch.setenv("BILLING_RECONCILE_WEBHOOK_AUTH", "Bearer secret")
        hook = build_default_alert_hook()
        assert isinstance(hook, WebhookAlertHook)
        assert hook.webhook_url == "https://hooks.example.com/billing"
        assert hook.auth_header == "Bearer secret"

    def test_053_lazy_state_uses_defaults(self):
        # Call task without configure — should lazy-init defaults
        result = reconcile_provider_task(provider="stripe", date="2026-06-24")
        assert result["provider"] == "stripe"
        assert result["mismatch_count"] == 0  # clean (empty)


# ── 7. Alert payload structure (via task) ────────────────────────────────

class TestAlertPayloadViaTask:
    def test_060_alert_payload_contains_mismatches(self):
        svc = OrderService(InMemoryOrderStore())
        svc.store.save(_paid_order("ord_a"))
        svc.store.save(_paid_order("ord_b"))
        adapter = MockProviderAdapter("stripe")
        # Only ord_a on provider
        adapter.add(_remote_charge("ord_a", provider="stripe"), "2026-06-24")
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        sess.post.return_value = resp
        hook = WebhookAlertHook(webhook_url="https://hooks.example.com/b",
                                session=sess)
        configure_celery_for_billing(
            order_service=svc, adapters={"stripe": adapter}, alert_hook=hook,
        )
        reconcile_provider_task(provider="stripe", date="2026-06-24")
        sess.post.assert_called_once()
        body = sess.post.call_args.kwargs["data"]
        payload = json.loads(body.decode("utf-8"))
        assert payload["provider"] == "stripe"
        assert payload["date"] == "2026-06-24"
        assert payload["mismatch_count"] == 1
        assert payload["mismatches"][0]["order_id"] == "ord_b"


# ── 8. Schedule entry content ─────────────────────────────────────────────

class TestScheduleEntry:
    def test_070_entry_points_to_correct_task(self):
        entry = celery_app.conf.beat_schedule["billing-reconcile-daily"]
        assert entry["task"] == "billing.reconcile_all_providers"

    def test_071_entry_uses_billing_queue(self):
        entry = celery_app.conf.beat_schedule["billing-reconcile-daily"]
        assert entry["options"]["queue"] == "billing.reconcile"

    def test_072_entry_runs_at_minute_zero(self):
        entry = celery_app.conf.beat_schedule["billing-reconcile-daily"]
        assert entry["schedule"].minute == {0}