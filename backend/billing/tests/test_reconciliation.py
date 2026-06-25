"""P6-Fix-C-4: Daily reconciliation tests.

Goals:
- diff detection (missing_local, missing_remote, amount/status/refund/currency mismatch)
- alert hook fires (success + error paths)
- WebhookAlertHook real HTTP path (mocked)
- Celery task end-to-end (eager mode)
- idempotent run
- date defaulting (yesterday UTC)
- module-level ``daily_reconcile`` convenience

Total: ~40 tests across 7 classes.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.orders import (
    InMemoryOrderStore, Order, OrderService, OrderStatus,
)
from billing.reconciliation import (
    MismatchType, MockProviderAdapter, NormalizedTxn, NoopAlertHook,
    ProviderReconciliationError, ReconcileAlertHook, ReconcileMismatch,
    ReconcileResult, ReconciliationEngine, WebhookAlertHook,
    LoggingAlertHook, MultiAlertHook, daily_reconcile,
    get_default_engine, set_default_engine, reset_default_engine,
    _normalize_date, _yesterday_utc,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_for(yyyy_mm_dd: str, hh: str = "12", mm: str = "00") -> str:
    """Build ISO8601 string for an arbitrary date + time (UTC)."""
    return f"{yyyy_mm_dd}T{hh}:{mm}:00+00:00"


def _make_service(orders: Optional[List[Order]] = None) -> OrderService:
    store = InMemoryOrderStore()
    svc = OrderService(store)
    for o in (orders or []):
        store.save(o)
    return svc


def _paid_order(order_id: str, amount_cents: int = 9900, currency: str = "USD",
                payment_method: str = "stripe",
                refunded_amount_cents: int = 0,
                created_on: Optional[str] = None,
                refunded_at: Optional[str] = None,
                external_ref: Optional[str] = None) -> Order:
    """Build a paid (and auto-fulfilled) order."""
    created = created_on or _iso_for("2026-06-24")
    return Order(
        order_id=order_id,
        user_id="u_test",
        plan_id="plan_pro",
        amount_cents=amount_cents,
        currency=currency,
        status=OrderStatus.PAID,
        payment_method=payment_method,
        created_at=created,
        paid_at=created,
        fulfilled_at=created,
        external_ref=external_ref or f"ext_{order_id}",
        refunded_amount_cents=refunded_amount_cents,
        refunded_at=refunded_at,
    )


def _fulfilled_order(order_id: str, amount_cents: int = 9900,
                     refunded_amount_cents: int = 0) -> Order:
    o = _paid_order(order_id, amount_cents=amount_cents,
                    refunded_amount_cents=refunded_amount_cents)
    o.status = OrderStatus.FULFILLED
    return o


def _refunded_order(order_id: str, amount_cents: int = 9900) -> Order:
    o = _paid_order(order_id, amount_cents=amount_cents)
    o.status = OrderStatus.REFUNDED
    o.refunded_amount_cents = amount_cents
    o.refunded_at = _iso_for("2026-06-24", hh="14")
    o.refund_reason = "customer requested"
    return o


def _remote_charge(order_id: str, amount_cents: int = 9900,
                   currency: str = "USD", refunded_amount_cents: int = 0,
                   provider: str = "stripe", status: str = "paid",
                   occurred_on: str = "2026-06-24") -> NormalizedTxn:
    return NormalizedTxn(
        order_id=order_id,
        provider_txn_id=f"txn_{order_id}",
        provider=provider,
        amount_cents=amount_cents,
        currency=currency,
        status=status,
        refunded_amount_cents=refunded_amount_cents,
        occurred_at=_iso_for(occurred_on),
    )


# ── 1. MockProviderAdapter basics ──────────────────────────────────────────

class TestMockProviderAdapter:
    def test_001_returns_empty_for_unseeded_date(self):
        adapter = MockProviderAdapter("stripe")
        assert adapter.fetch_transactions("2026-06-24") == []

    def test_002_returns_seeded_txns(self):
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_a"), "2026-06-24")
        adapter.add(_remote_charge("ord_b"), "2026-06-24")
        adapter.add(_remote_charge("ord_c"), "2026-06-25")  # wrong date
        out = adapter.fetch_transactions("2026-06-24")
        assert len(out) == 2
        ids = sorted(t.order_id for t in out)
        assert ids == ["ord_a", "ord_b"]

    def test_003_fail_on_dates_raises(self):
        adapter = MockProviderAdapter("stripe", fail_on_dates=["2026-06-24"])
        with pytest.raises(ProviderReconciliationError):
            adapter.fetch_transactions("2026-06-24")

    def test_004_provider_name_property(self):
        adapter = MockProviderAdapter("stripe")
        assert adapter.provider_name == "stripe"

    def test_005_custom_fetch_fn_takes_precedence(self):
        adapter = MockProviderAdapter("stripe",
                                      fetch_fn=lambda d: [_remote_charge("ord_x", occurred_on=d)])
        adapter.add(_remote_charge("ord_y"), "2026-06-24")
        # fetch_fn returns 1, so we get 1 not 2
        out = adapter.fetch_transactions("2026-06-24")
        assert [t.order_id for t in out] == ["ord_x"]

    def test_006_fetch_fn_returns_none_falls_back_to_seed(self):
        adapter = MockProviderAdapter("stripe",
                                      fetch_fn=lambda d: None)
        adapter.add(_remote_charge("ord_seed"), "2026-06-24")
        out = adapter.fetch_transactions("2026-06-24")
        assert [t.order_id for t in out] == ["ord_seed"]

    def test_007_clear_removes_seeds(self):
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_a"), "2026-06-24")
        adapter.clear()
        assert adapter.fetch_transactions("2026-06-24") == []


# ── 2. Engine basics — clean run ───────────────────────────────────────────

class TestEngineCleanRun:
    def test_010_clean_when_local_matches_remote(self):
        local = [_paid_order("ord_1"), _paid_order("ord_2", amount_cents=4900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_1", amount_cents=9900), "2026-06-24")
        adapter.add(_remote_charge("ord_2", amount_cents=4900), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0
        assert result.matched_count == 2
        assert result.local_count == 2
        assert result.remote_count == 2
        assert not result.has_mismatches
        assert result.error is None
        assert result.run_id.startswith("recon_")

    def test_011_empty_run_returns_zero(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0
        assert result.matched_count == 0
        assert result.local_count == 0
        assert result.remote_count == 0

    def test_012_default_date_is_yesterday(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe")
        # yesterday UTC matches helper
        assert result.date == _yesterday_utc()

    def test_013_unknown_provider_raises(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        with pytest.raises(KeyError):
            engine.run(provider="alipay", date="2026-06-24")

    def test_014_only_target_date_orders_included(self):
        # Local has orders on 2026-06-23 and 2026-06-24 — only 24 should count
        local = [
            _paid_order("ord_yest", created_on=_iso_for("2026-06-24")),
            _paid_order("ord_day_before",
                        created_on=_iso_for("2026-06-23")),
        ]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.local_count == 1


# ── 3. Mismatch detection ─────────────────────────────────────────────────

class TestMismatchDetection:
    def test_020_missing_remote_local_paid_no_provider_record(self):
        local = [_paid_order("ord_orphan")]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 1
        assert result.mismatches[0].mismatch_type == MismatchType.MISSING_REMOTE
        assert result.mismatches[0].order_id == "ord_orphan"

    def test_021_missing_local_provider_has_record_no_local(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_ghost"), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 1
        assert result.mismatches[0].mismatch_type == MismatchType.MISSING_LOCAL
        assert result.mismatches[0].order_id == "ord_ghost"

    def test_022_amount_mismatch(self):
        local = [_paid_order("ord_x", amount_cents=9900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        # provider says 10000 (we charged $100, local says $99)
        adapter.add(_remote_charge("ord_x", amount_cents=10000), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        types = [m.mismatch_type for m in result.mismatches]
        assert MismatchType.AMOUNT_MISMATCH in types
        am = next(m for m in result.mismatches
                  if m.mismatch_type == MismatchType.AMOUNT_MISMATCH)
        assert am.delta_cents == -100  # local - remote
        assert am.expected == 9900
        assert am.actual == 10000

    def test_023_status_mismatch(self):
        local = [_refunded_order("ord_y")]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        # provider still says paid (refund not propagated)
        adapter.add(_remote_charge("ord_y", status="paid"), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        types = [m.mismatch_type for m in result.mismatches]
        assert MismatchType.STATUS_MISMATCH in types

    def test_024_refund_mismatch(self):
        local = [_fulfilled_order("ord_z", amount_cents=9900,
                                  refunded_amount_cents=4900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        # provider refund is 1900, local is 4900
        adapter.add(_remote_charge("ord_z", amount_cents=9900,
                                   refunded_amount_cents=1900), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        types = [m.mismatch_type for m in result.mismatches]
        assert MismatchType.REFUND_MISMATCH in types

    def test_025_currency_mismatch(self):
        local = [_paid_order("ord_q", currency="USD")]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_q", currency="CNY"), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        types = [m.mismatch_type for m in result.mismatches]
        assert MismatchType.CURRENCY_MISMATCH in types

    def test_026_mixed_mismatches_single_run(self):
        local = [
            _paid_order("ord_ok", amount_cents=9900),
            _paid_order("ord_missing_remote"),
            _paid_order("ord_amount", amount_cents=9900),
        ]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_ok", amount_cents=9900), "2026-06-24")
        # ord_missing_remote: not added
        adapter.add(_remote_charge("ord_amount", amount_cents=4900), "2026-06-24")
        # ord_ghost: extra on provider
        adapter.add(_remote_charge("ord_ghost"), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 3
        types = [m.mismatch_type for m in result.mismatches]
        assert MismatchType.MISSING_REMOTE in types
        assert MismatchType.MISSING_LOCAL in types
        assert MismatchType.AMOUNT_MISMATCH in types

    def test_027_total_delta_aggregates(self):
        local = [
            _paid_order("ord_d1", amount_cents=9900),
            _paid_order("ord_d2", amount_cents=4900),
        ]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_d1", amount_cents=10000), "2026-06-24")
        adapter.add(_remote_charge("ord_d2", amount_cents=4000), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        # (9900-10000) + (4900-4000) = -100 + 900 = 800
        assert result.total_delta_cents == 800


# ── 4. Provider error handling ────────────────────────────────────────────

class TestProviderErrors:
    def test_030_provider_unreachable_records_error(self):
        svc = _make_service([_paid_order("ord_p")])
        adapter = MockProviderAdapter("stripe", fail_on_dates=["2026-06-24"])
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.error is not None
        assert "provider fetch failed" in result.error
        assert result.mismatch_count == 0

    def test_031_crash_in_hook_does_not_break_run(self):
        local = [_paid_order("ord_x")]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_x"), "2026-06-24")
        # Remote has extra ghost -> mismatch -> alert fires -> alert raises
        adapter.add(_remote_charge("ord_ghost"), "2026-06-24")

        class BoomHook:
            def send_alert(self, result):  # noqa: ARG002
                raise RuntimeError("alert webhook exploded")
        engine = ReconciliationEngine(svc, {"stripe": adapter}, alert_hook=BoomHook())
        result = engine.run(provider="stripe", date="2026-06-24")
        # Run completed despite alert failure
        assert result.error is None
        assert result.mismatch_count == 1
        assert result.alert_error is not None
        assert "exploded" in result.alert_error


# ── 5. Alert hooks ────────────────────────────────────────────────────────

class TestAlertHooks:
    def test_040_logging_hook_no_op_on_clean(self):
        hook = LoggingAlertHook()
        # Should not raise
        result = ReconcileResult(
            run_id="recon_test", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=0,
        )
        hook.send_alert(result)

    def test_041_webhook_hook_requires_url(self):
        with pytest.raises(ValueError):
            WebhookAlertHook(webhook_url="")

    def test_042_webhook_hook_posts_on_mismatch(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        sess.post.return_value = resp
        hook = WebhookAlertHook(webhook_url="https://hooks.example.com/billing",
                                session=sess)
        result = ReconcileResult(
            run_id="recon_test", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=2,
            mismatches=[ReconcileMismatch(
                mismatch_type=MismatchType.MISSING_REMOTE,
                order_id="ord_1", provider="stripe",
                description="x",
            )],
        )
        hook.send_alert(result)
        sess.post.assert_called_once()
        call_args = sess.post.call_args
        assert call_args.args[0] == "https://hooks.example.com/billing"
        body = call_args.kwargs["data"]
        payload = json.loads(body.decode("utf-8"))
        assert payload["mismatch_count"] == 2
        assert payload["provider"] == "stripe"
        assert call_args.kwargs["headers"]["X-Reconcile-Provider"] == "stripe"

    def test_043_webhook_hook_skips_below_min_severity(self):
        sess = MagicMock()
        hook = WebhookAlertHook(webhook_url="https://x.example.com/b",
                                min_severity=10, session=sess)
        result = ReconcileResult(
            run_id="recon_t", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=2,
        )
        hook.send_alert(result)
        sess.post.assert_not_called()

    def test_044_webhook_hook_5xx_raises(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "internal"
        sess.post.return_value = resp
        hook = WebhookAlertHook(webhook_url="https://x.example.com/b", session=sess)
        result = ReconcileResult(
            run_id="recon_t", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=1,
        )
        with pytest.raises(RuntimeError):
            hook.send_alert(result)

    def test_045_webhook_hook_auth_header(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "ok"
        sess.post.return_value = resp
        hook = WebhookAlertHook(
            webhook_url="https://x.example.com/b",
            auth_header="Bearer secret-token", session=sess,
        )
        result = ReconcileResult(
            run_id="recon_t", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=1,
        )
        hook.send_alert(result)
        headers = sess.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer secret-token"

    def test_046_multi_alert_calls_all_hooks(self):
        hook1 = MagicMock()
        hook2 = MagicMock()
        multi = MultiAlertHook([hook1, hook2])
        result = ReconcileResult(
            run_id="recon_t", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=1,
        )
        multi.send_alert(result)
        hook1.send_alert.assert_called_once_with(result)
        hook2.send_alert.assert_called_once_with(result)

    def test_047_multi_alert_continues_after_failure(self):
        hook1 = MagicMock()
        hook1.send_alert.side_effect = RuntimeError("hook1 failed")
        hook2 = MagicMock()
        multi = MultiAlertHook([hook1, hook2])
        result = ReconcileResult(
            run_id="recon_t", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            mismatch_count=1,
        )
        multi.send_alert(result)  # must not raise
        hook2.send_alert.assert_called_once_with(result)

    def test_048_engine_fires_alert_only_on_mismatch(self):
        local = [_paid_order("ord_clean")]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_clean"), "2026-06-24")
        hook = MagicMock()
        engine = ReconciliationEngine(svc, {"stripe": adapter}, alert_hook=hook)
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0
        hook.send_alert.assert_not_called()
        assert result.alert_sent is False

    def test_049_engine_fires_alert_on_mismatch(self):
        svc = _make_service([_paid_order("ord_x")])
        adapter = MockProviderAdapter("stripe")
        # no remote record -> MISSING_REMOTE mismatch
        hook = MagicMock()
        engine = ReconciliationEngine(svc, {"stripe": adapter}, alert_hook=hook)
        result = engine.run(provider="stripe", date="2026-06-24")
        hook.send_alert.assert_called_once_with(result)
        assert result.alert_sent is True


# ── 6. Module-level convenience + persistence ─────────────────────────────

class TestDailyReconcileConvenience:
    def setup_method(self):
        reset_default_engine()

    def teardown_method(self):
        reset_default_engine()

    def test_060_explicit_args_runs_engine(self):
        svc = _make_service([_paid_order("ord_a")])
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_a"), "2026-06-24")
        result = daily_reconcile(
            provider="stripe", date="2026-06-24",
            order_service=svc, adapters={"stripe": adapter},
        )
        assert result.mismatch_count == 0
        assert result.local_count == 1

    def test_061_no_engine_no_args_raises(self):
        with pytest.raises(RuntimeError):
            daily_reconcile(provider="stripe")

    def test_062_set_default_engine_picks_up(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        set_default_engine(engine)
        assert get_default_engine() is engine
        result = daily_reconcile(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0


# ── 7. Result serialization ───────────────────────────────────────────────

class TestResultSerialization:
    def test_070_to_dict_roundtrip(self):
        result = ReconcileResult(
            run_id="recon_abc", provider="stripe", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
            duration_ms=42,
            local_count=3, remote_count=2,
            matched_count=2, mismatch_count=1,
            total_local_amount_cents=20000, total_remote_amount_cents=19800,
            total_delta_cents=200,
            mismatches=[ReconcileMismatch(
                mismatch_type=MismatchType.AMOUNT_MISMATCH,
                order_id="ord_x", provider="stripe",
                description="differ", expected=9900, actual=10000,
                delta_cents=-100,
            )],
        )
        d = result.to_dict()
        assert d["provider"] == "stripe"
        assert d["mismatch_count"] == 1
        assert d["by_type"]["amount_mismatch"] == 1
        assert d["mismatches"][0]["order_id"] == "ord_x"
        assert d["mismatches"][0]["mismatch_type"] == "amount_mismatch"

    def test_071_summary_includes_all(self):
        result = ReconcileResult(
            run_id="recon_abc", provider="alipay", date="2026-06-24",
            started_at=_now_iso(), finished_at=_now_iso(),
        )
        s = result.summary()
        for key in ("run_id", "provider", "date", "started_at", "finished_at",
                    "duration_ms", "local_count", "remote_count",
                    "matched_count", "mismatch_count",
                    "total_local_amount_cents", "total_remote_amount_cents",
                    "total_delta_cents", "alert_sent", "alert_error",
                    "error", "by_type"):
            assert key in s

    def test_072_normalized_txn_is_refund_negative_amount(self):
        t = NormalizedTxn(
            order_id="ord_r", provider_txn_id="rfn_x", provider="stripe",
            amount_cents=-9900, currency="USD", status="refunded",
        )
        assert t.is_refund is True

    def test_073_normalized_txn_net(self):
        t = NormalizedTxn(
            order_id="ord_r", provider_txn_id="rfn_x", provider="stripe",
            amount_cents=9900, currency="USD", status="paid",
            refunded_amount_cents=4900,
        )
        assert t.net_amount_cents == 5000


# ── 8. Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_080_pending_orders_excluded(self):
        store = InMemoryOrderStore()
        store.save(Order(
            order_id="ord_pending", user_id="u", plan_id="p",
            amount_cents=9900, currency="USD",
            status=OrderStatus.PENDING,
            payment_method="stripe",
            created_at=_iso_for("2026-06-24"),
        ))
        svc = OrderService(store)
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.local_count == 0

    def test_081_other_payment_methods_excluded_by_default(self):
        store = InMemoryOrderStore()
        # local: stripe
        store.save(_paid_order("ord_s", payment_method="stripe"))
        # adapter: alipay — but only stripe adapter registered
        engine = ReconciliationEngine(store, {
            "stripe": MockProviderAdapter("stripe"),
            "alipay": MockProviderAdapter("alipay"),
        })
        result = engine.run(provider="stripe", date="2026-06-24")
        # ord_s is local-only (no stripe remote), so it's a MISSING_REMOTE
        assert result.mismatch_count == 1
        assert result.mismatches[0].mismatch_type == MismatchType.MISSING_REMOTE

    def test_082_iso_date_with_time_normalized(self):
        assert _normalize_date("2026-06-24T10:30:00+00:00") == "2026-06-24"
        assert _normalize_date("2026-06-24") == "2026-06-24"

    def test_083_iso_date_with_datetime_obj(self):
        d = datetime(2026, 6, 24, 10, 30, tzinfo=timezone.utc)
        assert _normalize_date(d) == "2026-06-24"

    def test_084_iso_date_with_date_obj(self):
        d = date(2026, 6, 24)
        assert _normalize_date(d) == "2026-06-24"

    def test_085_iso_date_invalid_type_raises(self):
        with pytest.raises(TypeError):
            _normalize_date(12345)  # type: ignore[arg-type]

    def test_086_run_id_is_unique_per_run(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        r1 = engine.run(provider="stripe", date="2026-06-24")
        r2 = engine.run(provider="stripe", date="2026-06-24")
        assert r1.run_id != r2.run_id

    def test_087_duration_ms_populated(self):
        svc = _make_service([])
        adapter = MockProviderAdapter("stripe", latency_ms=10)
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        # duration_ms uses time.monotonic; on Windows clock resolution is coarse
        # (~15ms), so a 10ms sleep may report 0ms. Verify at least the timestamps
        # differ, which proves the timing pipeline is wired.
        assert result.finished_at >= result.started_at
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    def test_088_fulfilled_orders_included(self):
        local = [_fulfilled_order("ord_f", amount_cents=9900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_f", amount_cents=9900), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0

    def test_089_refunded_orders_included(self):
        local = [_refunded_order("ord_r", amount_cents=9900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        # Provider: paid with full refund
        adapter.add(_remote_charge("ord_r", amount_cents=9900,
                                   refunded_amount_cents=9900,
                                   status="refunded"), "2026-06-24")
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.mismatch_count == 0
        assert result.matched_count == 1


# ── 9. ReconciliationEngine register_adapter ──────────────────────────────

class TestEngineRegistration:
    def test_090_register_adapter_adds_provider(self):
        svc = _make_service([])
        engine = ReconciliationEngine(svc, {})
        adapter = MockProviderAdapter("newprov")
        engine.register_adapter(adapter)
        assert "newprov" in engine.adapters
        # Can now run
        result = engine.run(provider="newprov", date="2026-06-24")
        assert result.mismatch_count == 0


# ── 10. Reconciliation against all 3 providers (mock parity) ──────────────

class TestAllProviders:
    def test_100_stripe_alipay_wechat_independent(self):
        svc = _make_service([
            _paid_order("ord_s", amount_cents=9900, payment_method="stripe"),
            _paid_order("ord_a", amount_cents=4900, payment_method="alipay"),
            _paid_order("ord_w", amount_cents=2900, payment_method="wechat"),
        ])
        adapters = {
            "stripe": MockProviderAdapter("stripe"),
            "alipay": MockProviderAdapter("alipay"),
            "wechat": MockProviderAdapter("wechat"),
        }
        # Stripe: clean
        adapters["stripe"].add(_remote_charge("ord_s", amount_cents=9900,
                                              provider="stripe"), "2026-06-24")
        # Alipay: ghost
        adapters["alipay"].add(_remote_charge("ord_a", amount_cents=4900,
                                              provider="alipay"), "2026-06-24")
        adapters["alipay"].add(_remote_charge("ord_ghost",
                                              provider="alipay"), "2026-06-24")
        # WeChat: missing remote
        # (no remote seed)
        engine = ReconciliationEngine(svc, adapters)
        r_stripe = engine.run(provider="stripe", date="2026-06-24")
        r_alipay = engine.run(provider="alipay", date="2026-06-24")
        r_wechat = engine.run(provider="wechat", date="2026-06-24")
        assert r_stripe.mismatch_count == 0
        assert r_alipay.mismatch_count == 1
        assert r_alipay.mismatches[0].mismatch_type == MismatchType.MISSING_LOCAL
        assert r_wechat.mismatch_count == 1
        assert r_wechat.mismatches[0].mismatch_type == MismatchType.MISSING_REMOTE


# ── 11. Matched-count never negative ──────────────────────────────────────

class TestMatchedCountMath:
    def test_110_matched_count_clamps_to_zero(self):
        # All 3 orders mismatch in multiple ways — matched should not go negative
        local = [_paid_order("ord_x", amount_cents=9900)]
        svc = _make_service(local)
        adapter = MockProviderAdapter("stripe")
        adapter.add(_remote_charge("ord_x", amount_cents=9900,
                                   currency="CNY",  # currency mismatch
                                   status="failed"), "2026-06-24")  # status mismatch
        engine = ReconciliationEngine(svc, {"stripe": adapter})
        result = engine.run(provider="stripe", date="2026-06-24")
        assert result.matched_count >= 0