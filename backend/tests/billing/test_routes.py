"""P4-10-W1: API/route tests using FastAPI TestClient.

Covers the full HTTP surface (plans, orders, payment, webhook, refund,
subscription, quotas, admin).
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from billing.routes import router as billing_router, reset_state


@pytest.fixture
def client():
    """Fresh billing router per test."""
    reset_state()
    app = FastAPI()
    app.include_router(billing_router)
    return TestClient(app)


class TestPlansEndpoints:
    def test_001_list_plans(self, client):
        r = client.get("/api/v1/billing/plans")
        assert r.status_code == 200
        plans = r.json()
        assert len(plans) == 5
        assert plans[0]["plan_id"] == "free"
        assert plans[2]["plan_id"] == "pro"

    def test_002_get_plan_detail(self, client):
        r = client.get("/api/v1/billing/plans/pro")
        assert r.status_code == 200
        d = r.json()
        assert d["plan_id"] == "pro"
        assert d["monthly_price_usd"] == 9900
        assert d["limits"]["datasets"] == 100

    def test_003_get_plan_not_found(self, client):
        r = client.get("/api/v1/billing/plans/nonexistent")
        assert r.status_code == 404

    def test_004_current_user_plan_default(self, client):
        r = client.get("/api/v1/billing/plans/current/user?user_id=u1")
        assert r.status_code == 200
        d = r.json()
        assert d["plan_id"] == "free"


class TestOrdersEndpoints:
    def test_005_create_order(self, client):
        body = {"user_id": "u1", "plan_id": "pro", "currency": "USD", "period": "monthly"}
        r = client.post("/api/v1/billing/orders", json=body)
        assert r.status_code == 200
        o = r.json()
        assert o["plan_id"] == "pro"
        assert o["amount_cents"] == 9900
        assert o["status"] == "pending"

    def test_006_create_order_invalid_plan(self, client):
        body = {"user_id": "u1", "plan_id": "unknown", "currency": "USD", "period": "monthly"}
        r = client.post("/api/v1/billing/orders", json=body)
        assert r.status_code == 400

    def test_007_list_orders_filter_by_user(self, client):
        # Create 2 orders for u1, 1 for u2
        for _ in range(2):
            client.post("/api/v1/billing/orders", json={
                "user_id": "u1", "plan_id": "starter", "currency": "USD", "period": "monthly",
            })
        client.post("/api/v1/billing/orders", json={
            "user_id": "u2", "plan_id": "pro", "currency": "USD", "period": "monthly",
        })
        r = client.get("/api/v1/billing/orders?user_id=u1")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 2

    def test_008_cancel_order(self, client):
        body = {"user_id": "u1", "plan_id": "starter", "currency": "USD", "period": "monthly"}
        r = client.post("/api/v1/billing/orders", json=body)
        order_id = r.json()["order_id"]
        r2 = client.post(f"/api/v1/billing/orders/{order_id}/cancel?reason=user_cancel")
        assert r2.status_code == 200
        assert r2.json()["status"] == "cancelled"


class TestPaymentEndpoints:
    def test_009_create_payment_returns_checkout_url(self, client):
        body = {"user_id": "u1", "plan_id": "pro", "currency": "USD", "period": "monthly",
                "payment_method": "stripe"}
        r = client.post("/api/v1/billing/orders", json=body)
        order_id = r.json()["order_id"]
        r2 = client.post(f"/api/v1/billing/payment/{order_id}", json={})
        assert r2.status_code == 200
        d = r2.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/c/pay/")

    def test_010_full_flow_order_to_paid_via_webhook(self, client):
        """End-to-end: order → payment → webhook → mark paid."""
        body = {"user_id": "u_e2e", "plan_id": "pro", "currency": "USD", "period": "monthly",
                "payment_method": "stripe"}
        r = client.post("/api/v1/billing/orders", json=body)
        order = r.json()
        order_id = order["order_id"]
        # Create payment
        r2 = client.post(f"/api/v1/billing/payment/{order_id}", json={})
        assert r2.status_code == 200
        # Build webhook
        payload = json.dumps({
            "id": "evt_test_e2e",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_e2e",
                "client_reference_id": order_id,
                "amount": 9900,
                "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        sig = f"t={ts},v1={v1}"
        r3 = client.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": sig, "content-type": "application/json"},
        )
        assert r3.status_code == 200
        # Order should now be fulfilled
        r4 = client.get(f"/api/v1/billing/orders/{order_id}")
        assert r4.json()["status"] == "fulfilled"


class TestRefundEndpoint:
    def test_011_refund_paid_order(self, client):
        body = {"user_id": "u_refund", "plan_id": "pro", "currency": "USD", "period": "monthly",
                "payment_method": "stripe"}
        r = client.post("/api/v1/billing/orders", json=body)
        order = r.json()
        order_id = order["order_id"]
        # Pay
        client.post(f"/api/v1/billing/payment/{order_id}", json={})
        # Mark paid via webhook
        payload = json.dumps({
            "id": "evt_refund", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_refund", "client_reference_id": order_id,
                "amount": 9900, "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": f"t={ts},v1={v1}",
                     "content-type": "application/json"},
        )
        # Refund
        r3 = client.post(f"/api/v1/billing/refund/{order_id}",
                          json={"reason": "customer_request"})
        assert r3.status_code == 200
        assert r3.json()["status"] == "refunded"


class TestSubscriptionEndpoints:
    def test_012_create_subscription(self, client):
        r = client.post("/api/v1/billing/subscription/user/u1/create?plan_id=pro&period=monthly&currency=USD")
        assert r.status_code == 200
        assert r.json()["plan_id"] == "pro"

    def test_013_get_user_subscription(self, client):
        client.post("/api/v1/billing/subscription/user/u1/create?plan_id=pro")
        r = client.get("/api/v1/billing/subscription/user/u1")
        assert r.status_code == 200
        assert r.json()["subscription"]["plan_id"] == "pro"

    def test_014_change_plan_upgrade(self, client):
        client.post("/api/v1/billing/subscription/user/u1/create?plan_id=starter")
        r = client.post(
            "/api/v1/billing/subscription/user/u1/change-plan",
            json={"new_plan_id": "pro", "period": "monthly", "currency": "USD"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["direction"] == "upgrade"
        assert d["new_plan_id"] == "pro"

    def test_015_cancel_subscription(self, client):
        client.post("/api/v1/billing/subscription/user/u1/create?plan_id=pro")
        r = client.post(
            "/api/v1/billing/subscription/user/u1/cancel",
            json={"at_period_end": True},
        )
        assert r.status_code == 200
        assert r.json()["cancel_at_period_end"] is True

    def test_016_run_renewal_cron(self, client):
        r = client.post("/api/v1/billing/subscription/cron/renewal?dry_run=true")
        assert r.status_code == 200
        d = r.json()
        assert "reminders_sent" in d
        assert d["dry_run"] is True


class TestQuotaEndpoints:
    def test_017_user_quotas(self, client):
        r = client.get("/api/v1/billing/quotas/user/u1?plan_id=pro")
        assert r.status_code == 200
        d = r.json()
        assert len(d["dimensions"]) == 12

    def test_018_check_quota_blocks_at_limit(self, client):
        # Set up a pro subscription for u1
        client.post("/api/v1/billing/subscription/user/u1/create?plan_id=pro&period=monthly&currency=USD")
        # Consume 100 datasets on pro (limit 100)
        for _ in range(100):
            client.post(
                "/api/v1/billing/quotas/user/u1/consume",
                json={"dimension": "datasets", "qty": 1},
            )
        r = client.post(
            "/api/v1/billing/quotas/check",
            json={"user_id": "u1", "plan_id": "pro",
                  "dimension": "datasets", "qty": 1},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["level"] == "hard_block"
        assert d["allowed"] is False

    def test_019_consume_quota_endpoint(self, client):
        # Create pro subscription for u1
        client.post("/api/v1/billing/subscription/user/u1/create?plan_id=pro&period=monthly&currency=USD")
        r = client.post(
            "/api/v1/billing/quotas/user/u1/consume",
            json={"dimension": "datasets", "qty": 5},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["allowed"] is True


class TestAdminEndpoints:
    def test_020_admin_revenue_summary(self, client):
        # Create a paid order
        body = {"user_id": "u_admin", "plan_id": "pro", "currency": "USD",
                "period": "monthly", "payment_method": "stripe"}
        r = client.post("/api/v1/billing/orders", json=body)
        order_id = r.json()["order_id"]
        # Mark paid via webhook
        payload = json.dumps({
            "id": "evt_admin", "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_admin",
                                 "client_reference_id": order_id,
                                 "amount": 9900, "currency": "usd"}},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post("/api/v1/billing/webhook/stripe", content=payload,
                    headers={"stripe-signature": f"t={ts},v1={v1}",
                             "content-type": "application/json"})
        r2 = client.get("/api/v1/billing/admin/revenue")
        assert r2.status_code == 200
        d = r2.json()
        assert d["paid_orders"] >= 1
        assert d["revenue_cents_by_currency"].get("USD", 0) >= 9900

    def test_021_admin_list_orders(self, client):
        client.post("/api/v1/billing/orders", json={
            "user_id": "u_admin_list", "plan_id": "starter", "currency": "USD",
            "period": "monthly",
        })
        r = client.get("/api/v1/billing/admin/orders?limit=10")
        assert r.status_code == 200
        d = r.json()
        assert len(d["orders"]) >= 1

    def test_022_admin_customers(self, client):
        r = client.get("/api/v1/billing/admin/customers")
        assert r.status_code == 200
        assert "customers" in r.json()

    def test_023_admin_global_usage(self, client):
        r = client.get("/api/v1/billing/admin/usage")
        assert r.status_code == 200
        d = r.json()
        assert "by_dimension" in d
        assert len(d["by_dimension"]) == 12
