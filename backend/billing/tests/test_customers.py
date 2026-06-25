"""P6-Fix-C-8 / P1-5: Stripe Customer + PaymentMethod tests."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter

from billing import customers as cust_mod
from billing.routes import customers_router as _real_cust_router

# Build a properly-prefixed router for tests
customers_router = APIRouter(prefix="/api/v1/billing")
customers_router.include_router(_real_cust_router)


@pytest.fixture(autouse=True)
def _clean():
    cust_mod._reset_customers()
    yield
    cust_mod._reset_customers()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(customers_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestCustomerModule:
    def test_001_register_customer(self):
        c = cust_mod.register_customer(
            user_id="u_001", email="a@a.com", name="Alice",
        )
        assert c.cus_id.startswith("cus_")
        assert c.user_id == "u_001"
        assert c.email == "a@a.com"

    def test_002_register_twice_returns_same(self):
        c1 = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        c2 = cust_mod.register_customer(user_id="u_001", email="a2@a.com", name="A2")
        assert c1.cus_id == c2.cus_id
        assert c2.email == "a2@a.com"  # 更新

    def test_003_register_missing_fields_raises(self):
        with pytest.raises(ValueError):
            cust_mod.register_customer(user_id="", email="a@a.com", name="A")
        with pytest.raises(ValueError):
            cust_mod.register_customer(user_id="u", email="", name="A")

    def test_004_get_by_user(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        fetched = cust_mod.get_customer_by_user("u_001")
        assert fetched is not None
        assert fetched.cus_id == c.cus_id

    def test_005_get_by_user_nonexistent(self):
        assert cust_mod.get_customer_by_user("u_nonexistent") is None

    def test_010_attach_payment_method(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        pm = cust_mod.attach_payment_method(
            customer_id=c.cus_id, pm_type="card", token="pm_test_001",
            brand="visa", last4="4242", exp_month=12, exp_year=2030, is_default=True,
        )
        assert pm.pm_id.startswith("pm_")
        assert pm.is_default is True
        assert pm.brand == "visa"
        assert pm.last4 == "4242"
        # customer default_payment_method_id updated
        assert c.default_payment_method_id == pm.pm_id

    def test_011_attach_invalid_type_raises(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        with pytest.raises(ValueError):
            cust_mod.attach_payment_method(c.cus_id, "bogus", "tok")

    def test_012_attach_unknown_customer_raises(self):
        with pytest.raises(KeyError):
            cust_mod.attach_payment_method("cus_fake", "card", "tok")

    def test_013_attach_missing_token_raises(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        with pytest.raises(ValueError):
            cust_mod.attach_payment_method(c.cus_id, "card", "")

    def test_014_list_payment_methods(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        cust_mod.attach_payment_method(c.cus_id, "card", "tok1", last4="1111")
        cust_mod.attach_payment_method(c.cus_id, "alipay", "tok2")
        cust_mod.attach_payment_method(c.cus_id, "card", "tok3", last4="3333")
        all_pms = cust_mod.list_payment_methods(c.cus_id)
        assert len(all_pms) == 3
        cards = cust_mod.list_payment_methods(c.cus_id, pm_type="card")
        assert len(cards) == 2

    def test_015_detach_payment_method(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        pm = cust_mod.attach_payment_method(c.cus_id, "card", "tok1", is_default=True)
        ok = cust_mod.detach_payment_method(pm.pm_id)
        assert ok is True
        assert cust_mod.list_payment_methods(c.cus_id) == []
        # Default cleared
        c2 = cust_mod.get_customer(c.cus_id)
        assert c2.default_payment_method_id is None

    def test_016_detach_nonexistent(self):
        assert cust_mod.detach_payment_method("pm_fake") is False

    def test_017_get_default(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        pm1 = cust_mod.attach_payment_method(c.cus_id, "card", "tok1", is_default=True)
        pm2 = cust_mod.attach_payment_method(c.cus_id, "alipay", "tok2")
        default = cust_mod.get_default_payment_method(c.cus_id)
        assert default.pm_id == pm1.pm_id

    def test_018_set_default(self):
        c = cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A")
        pm1 = cust_mod.attach_payment_method(c.cus_id, "card", "tok1", is_default=True)
        pm2 = cust_mod.attach_payment_method(c.cus_id, "alipay", "tok2")
        cust_mod.set_default_payment_method(pm2.pm_id)
        # pm2 现在是 default
        c2 = cust_mod.get_customer(c.cus_id)
        assert c2.default_payment_method_id == pm2.pm_id
        # pm1.is_default = False
        assert cust_mod.get_payment_method(pm1.pm_id).is_default is False

    def test_019_set_default_unknown_raises(self):
        with pytest.raises(KeyError):
            cust_mod.set_default_payment_method("pm_fake")

    def test_020_customer_stats(self):
        cust_mod.register_customer(user_id="u_001", email="a@a.com", name="A", provider="stripe", currency="USD")
        cust_mod.register_customer(user_id="u_002", email="b@b.com", name="B", provider="alipay", currency="CNY")
        c = cust_mod.register_customer(user_id="u_003", email="c@c.com", name="C", provider="stripe", currency="USD")
        cust_mod.attach_payment_method(c.cus_id, "card", "tok1")
        s = cust_mod.customer_stats()
        assert s["total_customers"] == 3
        assert s["total_payment_methods"] == 1
        assert s["by_provider"]["stripe"] == 2
        assert s["by_pm_type"]["card"] == 1


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestCustomerRoutes:
    def test_030_register_via_api(self, client):
        r = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "Alice",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["cus_id"].startswith("cus_")

    def test_031_register_missing_400(self, client):
        r = client.post("/api/v1/billing/customers", json={
            "user_id": "", "email": "a@a.com", "name": "A",
        })
        assert r.status_code == 422

    def test_032_get_by_id(self, client):
        r1 = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        cid = r1.json()["cus_id"]
        r = client.get(f"/api/v1/billing/customers/{cid}")
        assert r.status_code == 200
        assert r.json()["cus_id"] == cid

    def test_033_get_by_user(self, client):
        client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        r = client.get("/api/v1/billing/customers/by-user/u_001")
        assert r.status_code == 200
        assert r.json()["user_id"] == "u_001"

    def test_034_attach_pm(self, client):
        r1 = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        cid = r1.json()["cus_id"]
        r = client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cid, "pm_type": "card", "token": "tok_test",
            "brand": "visa", "last4": "4242", "is_default": True,
        })
        assert r.status_code == 200
        assert r.json()["pm_id"].startswith("pm_")

    def test_035_list_pms(self, client):
        r1 = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        cid = r1.json()["cus_id"]
        client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cid, "pm_type": "card", "token": "tok1", "is_default": True,
        })
        client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cid, "pm_type": "alipay", "token": "tok2",
        })
        r = client.get(f"/api/v1/billing/customers/{cid}/payment-methods")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_036_default_pm(self, client):
        r1 = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        cid = r1.json()["cus_id"]
        r2 = client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cid, "pm_type": "card", "token": "tok1", "is_default": True,
        })
        r = client.get(f"/api/v1/billing/customers/{cid}/payment-methods/default")
        assert r.status_code == 200
        assert r.json()["pm_id"] == r2.json()["pm_id"]

    def test_037_detach_pm(self, client):
        r1 = client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        cid = r1.json()["cus_id"]
        r2 = client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cid, "pm_type": "card", "token": "tok1",
        })
        r = client.delete(f"/api/v1/billing/customers/payment-methods/{r2.json()['pm_id']}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    def test_038_stats_route(self, client):
        client.post("/api/v1/billing/customers", json={
            "user_id": "u_001", "email": "a@a.com", "name": "A",
        })
        r = client.get("/api/v1/billing/customers/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_customers"] == 1
        assert "by_provider" in data
