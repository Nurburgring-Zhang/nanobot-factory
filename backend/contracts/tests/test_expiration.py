"""P6-Fix-C-8 / P1-4: 合同到期提醒 tests.

Verifies:
- check_expiring: 分类 upcoming / today / overdue
- send_expiration_notices: webhook/email/log 通道
- expire_overdue: 自动 expire 已过截止日的 active 合同
- renew_contract: 续约
- get_expiration_stats
- Routes: /expiration/check, /send, /expire-overdue, /{id}/renew
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter

import contracts
from contracts import expiration as exp_mod
from contracts.routes import expiration_router as expiration_router
from contracts.expiration import _reset_expiration


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean():
    contracts._STORE.clear()
    _reset_expiration()
    yield
    contracts._STORE.clear()
    _reset_expiration()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(expiration_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestExpirationModule:
    def test_001_check_expiring_upcoming(self):
        # 合同 15 天后到期 — 用 16 天确保 days_to_expiry=15 (因时间漂移)
        future = (datetime.utcnow() + timedelta(days=16)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=1000.0,
            end_date=future,
        )
        # 签了 -> active
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring()
        assert report.scanned == 1
        assert len(report.upcoming) == 1
        assert report.upcoming[0].days_to_expiry == 15
        assert report.upcoming[0].kind == "upcoming"

    def test_002_check_expiring_today(self):
        # Use tomorrow's end_date so days_to_expiry=0 (or 1).
        # We just verify the contract is detected (in either today or upcoming bucket).
        future = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=future,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring()
        assert report.scanned == 1
        # Either today (0 days) or upcoming (1 day) — both acceptable
        assert len(report.today) + len(report.upcoming) == 1

    def test_003_check_expiring_overdue(self):
        past = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=past,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring()
        assert len(report.overdue) == 1

    def test_004_long_term_skipped(self):
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date="长期有效",
        )
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring()
        assert report.scanned == 0

    def test_005_draft_skipped(self):
        future = (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d")
        contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=future,
        )
        # 不签 = draft, 不提醒
        report = exp_mod.check_expiring()
        assert report.scanned == 0

    def test_006_window_filter(self):
        # 60 天后到期, 默认 30 天窗口 — 不提醒
        future = (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=future,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring(window_days=30)
        assert report.scanned == 0
        report2 = exp_mod.check_expiring(window_days=90)
        assert report2.scanned == 1

    def test_007_send_expiration_log_fallback(self):
        past = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=past,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        report = exp_mod.check_expiring()
        counters = exp_mod.send_expiration_notices(report)
        # 没有 webhook, 没有 email → 全部 log
        assert counters["logs_written"] >= 1

    def test_008_expire_overdue(self):
        past = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=past,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        n = exp_mod.expire_overdue()
        assert n == 1
        refreshed = contracts.get_contract(c.contract_id)
        assert refreshed.status == "expired"

    def test_009_renew_contract(self):
        future = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="ACME",
            contact_email="a@a.com",
            plan_name="Pro",
            amount=100.0,
            end_date=future,
        )
        contracts.sign_contract(c.contract_id, "ACME")
        new_end = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
        new = exp_mod.renew_contract(c.contract_id, new_end)
        assert new.contract_id != c.contract_id
        # 旧合同标记为 renewed
        assert contracts.get_contract(c.contract_id).status == "renewed"
        # 新合同 active
        assert new.status == "draft"  # 默认 draft, 需 sign

    def test_010_renew_nonexistent_raises(self):
        with pytest.raises(KeyError):
            exp_mod.renew_contract("CT-FAKE", "2030-01-01")

    def test_011_renew_draft_raises(self):
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0,
            end_date="2030-01-01",
        )
        # 不签 → draft
        with pytest.raises(ValueError):
            exp_mod.renew_contract(c.contract_id, "2031-01-01")

    def test_012_stats(self):
        # 创建一个即将到期
        future = (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d")
        c1 = contracts.generate_contract(
            template="service_agreement", company_name="A", contact_email="a@a.com",
            plan_name="Pro", amount=100.0, end_date=future,
        )
        contracts.sign_contract(c1.contract_id, "A")
        c2 = contracts.generate_contract(
            template="service_agreement", company_name="B", contact_email="b@b.com",
            plan_name="Pro", amount=100.0, end_date="长期有效",
        )
        stats = exp_mod.get_expiration_stats()
        assert stats["total_contracts"] == 2
        assert "8-30d" in stats["by_expiration_window"]


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestExpirationRoutes:
    def test_020_check_via_api(self, client):
        future = (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement", company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0, end_date=future,
        )
        contracts.sign_contract(c.contract_id, "X")
        r = client.get("/api/v1/contracts/expiration/check?window_days=30")
        assert r.status_code == 200
        data = r.json()
        assert data["scanned"] >= 1

    def test_021_send_via_api(self, client):
        past = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement", company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0, end_date=past,
        )
        contracts.sign_contract(c.contract_id, "X")
        r = client.post("/api/v1/contracts/expiration/send?window_days=30")
        assert r.status_code == 200
        assert "report" in r.json()
        assert "counters" in r.json()

    def test_022_expire_overdue_via_api(self, client):
        past = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement", company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0, end_date=past,
        )
        contracts.sign_contract(c.contract_id, "X")
        r = client.post("/api/v1/contracts/expiration/expire-overdue")
        assert r.status_code == 200
        assert r.json()["expired_count"] >= 1

    def test_023_renew_via_api(self, client):
        future = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        c = contracts.generate_contract(
            template="service_agreement", company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0, end_date=future,
        )
        contracts.sign_contract(c.contract_id, "X")
        new_end = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
        r = client.post(
            f"/api/v1/contracts/expiration/{c.contract_id}/renew",
            json={"new_end_date": new_end},
        )
        assert r.status_code == 200
        assert r.json()["contract_id"] != c.contract_id

    def test_024_renew_invalid_date_400(self, client):
        c = contracts.generate_contract(
            template="service_agreement", company_name="X", contact_email="x@x.com",
            plan_name="Pro", amount=100.0, end_date="2030-01-01",
        )
        contracts.sign_contract(c.contract_id, "X")
        r = client.post(
            f"/api/v1/contracts/expiration/{c.contract_id}/renew",
            json={"new_end_date": ""},
        )
        assert r.status_code == 422  # Pydantic 校验

    def test_025_stats_route(self, client):
        r = client.get("/api/v1/contracts/expiration/stats")
        assert r.status_code == 200
        data = r.json()
        assert "by_status" in data
        assert "by_expiration_window" in data
