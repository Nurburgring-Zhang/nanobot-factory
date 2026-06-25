"""P6-Fix-C-8 / P1-2: Dispute / Chargeback (Stripe) tests.

Verifies:
- register_dispute / get_dispute / list_open_disputes / dispute_stats
- upload_evidence / resolve_dispute 状态机
- Stripe webhook charge.dispute.created / charge.dispute.closed 翻译
- Routes: POST /disputes, GET /disputes, POST /evidence, POST /resolve
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from billing.payments import dispute as dispute_mod
from billing.payments.stripe_provider import StripeProvider
from billing.routes import disputes_router as _real_disputes_router, webhook_router
from fastapi import APIRouter

# Build a properly-prefixed dispute router for tests
disputes_router = APIRouter(prefix="/api/v1/billing")
disputes_router.include_router(_real_disputes_router)


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_disputes():
    dispute_mod._reset_disputes()
    yield
    dispute_mod._reset_disputes()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(disputes_router)
    a.include_router(webhook_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestDisputeModule:
    def test_001_register_dispute(self):
        d = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1",
            amount_cents=10000, currency="USD",
            reason="fraudulent", alert=False,
        )
        assert d.dispute_id.startswith("dp_")
        assert d.status == "needs_response"
        assert d.reason == "fraudulent"
        assert d.evidence_due_by is not None

    def test_002_register_invalid_reason_raises(self):
        with pytest.raises(ValueError):
            dispute_mod.register_dispute(
                order_id="ord_1", payment_id="pi_1",
                amount_cents=1000, reason="bad_reason", alert=False,
            )

    def test_003_register_zero_amount_raises(self):
        with pytest.raises(ValueError):
            dispute_mod.register_dispute(
                order_id="ord_1", payment_id="pi_1",
                amount_cents=0, alert=False,
            )

    def test_004_get_by_order(self):
        d1 = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        d2 = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_2", amount_cents=200, alert=False,
        )
        items = dispute_mod.get_disputes_by_order("ord_1")
        assert len(items) == 2
        assert d1 in items and d2 in items

    def test_005_upload_evidence(self):
        d = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        updated = dispute_mod.upload_evidence(
            d.dispute_id,
            {"receipt": {"url": "https://x.com/r"}, "customer_communication": "邮件回复"},
        )
        assert updated.status == "under_review"
        assert updated.evidence["receipt"]["url"] == "https://x.com/r"

    def test_006_upload_evidence_closed_raises(self):
        d = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        dispute_mod.resolve_dispute(d.dispute_id, "lost", resolution_note="close")
        with pytest.raises(ValueError):
            dispute_mod.upload_evidence(d.dispute_id, {"x": 1})

    def test_007_resolve_won(self):
        d = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        r = dispute_mod.resolve_dispute(d.dispute_id, "won", "证据充分")
        assert r.status == "won"
        assert r.closed_at is not None
        assert r.resolution_note == "证据充分"

    def test_008_resolve_invalid_status_raises(self):
        d = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        with pytest.raises(ValueError):
            dispute_mod.resolve_dispute(d.dispute_id, "bogus")

    def test_009_list_open(self):
        d1 = dispute_mod.register_dispute(
            order_id="ord_1", payment_id="pi_1", amount_cents=100, alert=False,
        )
        d2 = dispute_mod.register_dispute(
            order_id="ord_2", payment_id="pi_2", amount_cents=200, alert=False,
        )
        dispute_mod.resolve_dispute(d1.dispute_id, "won")
        open_items = dispute_mod.list_open_disputes()
        assert d1 not in open_items
        assert d2 in open_items

    def test_010_stats(self):
        dispute_mod.register_dispute(
            order_id="o1", payment_id="p1", amount_cents=100, reason="fraudulent", alert=False,
        )
        dispute_mod.register_dispute(
            order_id="o2", payment_id="p2", amount_cents=200, reason="duplicate", alert=False,
        )
        s = dispute_mod.dispute_stats()
        assert s["total_disputes"] == 2
        assert s["open_amount_cents"] == 300
        assert s["by_reason"]["fraudulent"] == 1
        assert s["by_reason"]["duplicate"] == 1


# ── 2. Stripe webhook 翻译 ──────────────────────────────────────────────
class TestStripeDisputeWebhook:
    def test_020_dispute_created_event_translation(self):
        prov = StripeProvider(mode="mock")
        payload = {
            "id": "evt_dp_001",
            "type": "charge.dispute.created",
            "created": 1700000000,
            "data": {
                "object": {
                    "id": "dp_001",
                    "charge": "ch_001",
                    "amount": 5000,
                    "currency": "usd",
                    "reason": "fraudulent",
                    "metadata": {"order_id": "ord_test_1"},
                }
            },
        }
        body = json.dumps(payload).encode("utf-8")
        event = prov._decode_event(payload)
        assert event.event_type == "charge.dispute.created"
        assert event.status == "disputed"
        assert event.order_id == "ord_test_1"
        assert event.amount_cents == 5000
        assert event.currency == "USD"

    def test_021_dispute_closed_event_translation(self):
        prov = StripeProvider(mode="mock")
        payload = {
            "id": "evt_dp_002",
            "type": "charge.dispute.closed",
            "created": 1700000000,
            "data": {
                "object": {
                    "id": "dp_002",
                    "status": "won",
                    "metadata": {"order_id": "ord_test_2"},
                }
            },
        }
        event = prov._decode_event(payload)
        assert event.event_type == "charge.dispute.closed"
        assert event.status == "disputed"

    def test_022_dispute_with_missing_metadata(self):
        prov = StripeProvider(mode="mock")
        payload = {
            "id": "evt_dp_003",
            "type": "charge.dispute.created",
            "data": {"object": {"id": "dp_3", "amount": 1000, "currency": "eur"}},
        }
        event = prov._decode_event(payload)
        assert event.order_id == ""  # metadata 缺失


# ── 3. HTTP API 路由测试 ─────────────────────────────────────────────────
class TestDisputeRoutes:
    def test_030_register_via_api(self, client):
        r = client.post("/api/v1/billing/disputes", json={
            "order_id": "ord_001",
            "payment_id": "pi_001",
            "amount_cents": 5000,
            "currency": "USD",
            "reason": "fraudulent",
            "alert": False,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["dispute_id"].startswith("dp_")
        assert data["order_id"] == "ord_001"
        assert data["reason"] == "fraudulent"

    def test_031_register_invalid_reason_400(self, client):
        r = client.post("/api/v1/billing/disputes", json={
            "order_id": "ord_001", "payment_id": "pi_001",
            "amount_cents": 100, "reason": "bogus",
        })
        assert r.status_code == 400

    def test_032_list_disputes(self, client):
        client.post("/api/v1/billing/disputes", json={
            "order_id": "o1", "payment_id": "p1", "amount_cents": 100, "alert": False,
        })
        client.post("/api/v1/billing/disputes", json={
            "order_id": "o2", "payment_id": "p2", "amount_cents": 200, "alert": False,
        })
        r = client.get("/api/v1/billing/disputes")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_033_list_open_only(self, client):
        r1 = client.post("/api/v1/billing/disputes", json={
            "order_id": "o1", "payment_id": "p1", "amount_cents": 100, "alert": False,
        })
        client.post("/api/v1/billing/disputes", json={
            "order_id": "o2", "payment_id": "p2", "amount_cents": 200, "alert": False,
        })
        client.post(f"/api/v1/billing/disputes/{r1.json()['dispute_id']}/resolve", json={
            "status": "won",
        })
        r = client.get("/api/v1/billing/disputes?open_only=true")
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_034_get_one_404(self, client):
        r = client.get("/api/v1/billing/disputes/dp_nonexistent")
        assert r.status_code == 404

    def test_035_upload_evidence_via_api(self, client):
        r1 = client.post("/api/v1/billing/disputes", json={
            "order_id": "o1", "payment_id": "p1", "amount_cents": 100, "alert": False,
        })
        did = r1.json()["dispute_id"]
        r = client.post(f"/api/v1/billing/disputes/{did}/evidence", json={
            "receipt": {"url": "https://x.com/r"},
            "customer_communication": "邮件往来记录",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"

    def test_036_resolve_via_api(self, client):
        r1 = client.post("/api/v1/billing/disputes", json={
            "order_id": "o1", "payment_id": "p1", "amount_cents": 100, "alert": False,
        })
        did = r1.json()["dispute_id"]
        r = client.post(f"/api/v1/billing/disputes/{did}/resolve", json={
            "status": "lost", "resolution_note": "证据不足",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "lost"

    def test_037_stats_route(self, client):
        client.post("/api/v1/billing/disputes", json={
            "order_id": "o1", "payment_id": "p1", "amount_cents": 100, "alert": False,
        })
        r = client.get("/api/v1/billing/disputes/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_disputes"] == 1
        assert "by_status" in data
        assert "win_rate_pct" in data
