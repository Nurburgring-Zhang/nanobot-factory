"""P4-10-W1: Order system tests (5 tests)."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.orders import (
    Order, OrderService, OrderStatus, InMemoryOrderStore,
    JsonlOrderStore, can_transition, TERMINAL_STATUSES,
    BILLING_ORDERS_DDL, BILLING_ORDERS_DDL_SQLITE,
)


class TestOrderCreate:
    def test_001_create_order_pending(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=9900, currency="USD",
                                 payment_method="mock")
        assert order.status == OrderStatus.PENDING
        assert order.amount_cents == 9900
        assert order.currency == "USD"
        assert order.order_id.startswith("ord_")
        assert order.created_at
        assert order.paid_at is None
        # verify it was saved
        fetched = store.get(order.order_id)
        assert fetched is not None
        assert fetched.plan_id == "pro"

    def test_002_create_order_invalid_amount(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        with pytest.raises(ValueError):
            svc.create_order(user_id="u1", plan_id="pro", amount_cents=-100, currency="USD")
        with pytest.raises(ValueError):
            svc.create_order(user_id="u1", plan_id="pro", amount_cents=100, currency="EUR")


class TestOrderStateMachine:
    def test_003_pending_to_paid_transition(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro", amount_cents=9900, currency="USD")
        # mark_paid should go pending → paid → fulfilled (combined)
        paid = svc.mark_paid(order.order_id, external_ref="pi_test_123")
        assert paid.status == OrderStatus.FULFILLED
        assert paid.paid_at is not None
        assert paid.fulfilled_at is not None
        assert paid.external_ref == "pi_test_123"

    def test_004_invalid_transition_raises(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro", amount_cents=9900, currency="USD")
        svc.mark_paid(order.order_id)
        # Now FULFILLED — should not be able to cancel
        with pytest.raises(ValueError):
            svc.cancel(order.order_id)

    def test_005_refund_after_payment(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro", amount_cents=9900, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_1")
        refunded = svc.refund(order.order_id, reason="customer_request")
        assert refunded.status == OrderStatus.REFUNDED
        assert refunded.refunded_at is not None
        assert refunded.refund_reason == "customer_request"


class TestOrderCancel:
    def test_006_cancel_pending_order(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro", amount_cents=9900, currency="USD")
        cancelled = svc.cancel(order.order_id, reason="user_changed_mind")
        assert cancelled.status == OrderStatus.CANCELLED
        assert cancelled.metadata.get("cancel_reason") == "user_changed_mind"


class TestOrderList:
    def test_007_list_filter_by_user_and_status(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        o1 = svc.create_order(user_id="u1", plan_id="pro", amount_cents=9900, currency="USD")
        o2 = svc.create_order(user_id="u1", plan_id="starter", amount_cents=2900, currency="USD")
        o3 = svc.create_order(user_id="u2", plan_id="pro", amount_cents=9900, currency="USD")
        svc.mark_paid(o1.order_id)
        # u1 orders
        u1_orders = svc.list_for_user("u1")
        assert len(u1_orders) == 2
        # All paid orders
        paid = svc.store.list(status=OrderStatus.FULFILLED)
        assert len(paid) == 1
        assert paid[0].order_id == o1.order_id


class TestOrderJsonlStore:
    def test_008_jsonl_store_persistence(self, tmp_path):
        path = tmp_path / "orders.jsonl"
        store1 = JsonlOrderStore(str(path))
        order = Order(
            order_id="ord_test1", user_id="u1", plan_id="pro",
            amount_cents=9900, currency="USD",
            status=OrderStatus.PENDING, payment_method="mock",
            created_at="2026-06-24T04:00:00+00:00",
        )
        store1.save(order)
        # New store reads from same file
        store2 = JsonlOrderStore(str(path))
        fetched = store2.get("ord_test1")
        assert fetched is not None
        assert fetched.amount_cents == 9900
        assert fetched.status == OrderStatus.PENDING


class TestStateMachineHelpers:
    def test_009_can_transition_table(self):
        # pending → paid / failed / cancelled
        assert can_transition(OrderStatus.PENDING, OrderStatus.PAID) is True
        assert can_transition(OrderStatus.PENDING, OrderStatus.FAILED) is True
        assert can_transition(OrderStatus.PENDING, OrderStatus.CANCELLED) is True
        assert can_transition(OrderStatus.PENDING, OrderStatus.FULFILLED) is False
        # paid → fulfilled / refunded
        assert can_transition(OrderStatus.PAID, OrderStatus.FULFILLED) is True
        assert can_transition(OrderStatus.PAID, OrderStatus.REFUNDED) is True
        # terminal → nothing
        for term in (OrderStatus.FULFILLED, OrderStatus.FAILED,
                     OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            assert len([s for s in OrderStatus
                        if can_transition(term, s)]) == 0
        assert OrderStatus.FULFILLED in TERMINAL_STATUSES


class TestOrderSQL:
    def test_010_ddl_strings_present(self):
        assert "CREATE TABLE" in BILLING_ORDERS_DDL
        assert "billing_orders" in BILLING_ORDERS_DDL
        assert "CREATE TABLE" in BILLING_ORDERS_DDL_SQLITE
        assert "billing_orders" in BILLING_ORDERS_DDL_SQLITE
