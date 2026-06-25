"""P6-Fix-C-8 / P1-1: Lead scoring tests.

Verifies:
- compute_lead_score() 纯函数 (deterministic)
- 新建客户自动打分 (route 层)
- get_top_leads / get_lead_stats 正确性
- 重算全部 / 单客户刷新
- 路由: GET /crm/leads/top, /stats, /recompute, /{id}/rescore
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

import crm
from crm import (
    compute_lead_score, recompute_customer_score, get_top_leads,
    get_lead_stats, _CUSTOMERS,
)
from crm.routes import router_customers, router_leads
from fastapi import FastAPI


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_customers():
    _CUSTOMERS.clear()
    yield
    _CUSTOMERS.clear()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router_customers)
    a.include_router(router_leads)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 纯函数测试 ─────────────────────────────────────────────────────────
class TestLeadScoreComputation:
    def test_001_strategic_high_ltv_high_score(self):
        now = datetime.utcnow()
        score = compute_lead_score(
            tier="strategic",
            industry="金融",
            size="1000+",
            followups=[{"type": "contract", "at": now.isoformat()}],
            lifetime_value=100000.0,
            updated_at=now.isoformat(),
            now=now,
        )
        assert score["grade"] == "A"
        assert score["score"] >= 130

    def test_002_individual_no_followup_low_score(self):
        now = datetime.utcnow()
        score = compute_lead_score(
            tier="individual",
            industry="其他",
            size="1-10",
            followups=[],
            lifetime_value=0.0,
            updated_at=(now - timedelta(days=200)).isoformat(),
            now=now,
        )
        assert score["grade"] == "D"
        assert score["score"] < 50

    def test_003_mid_market_with_recent_activity(self):
        now = datetime.utcnow()
        score = compute_lead_score(
            tier="mid_market",
            industry="互联网/科技",
            size="51-200",
            followups=[{"type": "contract", "at": now.isoformat()},
                       {"type": "communication", "at": now.isoformat()}],
            lifetime_value=10000.0,
            updated_at=now.isoformat(),
            now=now,
        )
        assert score["grade"] in ("B", "A", "C")

    def test_004_recency_7days_bonus(self):
        now = datetime.utcnow()
        s1 = compute_lead_score(
            tier="smb", industry="其他", size="11-50",
            followups=[], lifetime_value=0.0,
            updated_at=(now - timedelta(days=2)).isoformat(), now=now,
        )
        s2 = compute_lead_score(
            tier="smb", industry="其他", size="11-50",
            followups=[], lifetime_value=0.0,
            updated_at=(now - timedelta(days=120)).isoformat(), now=now,
        )
        assert s1["score"] > s2["score"]

    def test_005_breakdown_present(self):
        now = datetime.utcnow()
        score = compute_lead_score(
            tier="large", industry="金融", size="201-1000",
            followups=[], lifetime_value=1000.0,
            updated_at=now.isoformat(), now=now,
        )
        assert "breakdown" in score
        assert "tier_base" in score["breakdown"]
        assert "industry_bonus" in score["breakdown"]
        assert "ltv_score" in score["breakdown"]


# ── 2. 客户级打分 ─────────────────────────────────────────────────────────
class TestCustomerScoring:
    def test_010_new_customer_auto_scored(self):
        c = crm.create_customer(
            company_name="ACME战略公司",
            contact_name="张三",
            email="z@a.com",
            tier="strategic",
            industry="金融",
            size="1000+",
        )
        recompute_customer_score(c)
        assert c.lead_grade in ("A", "B")
        assert c.lead_score > 0
        assert "tier_base" in c.lead_score_breakdown

    def test_011_recompute_all(self):
        crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="smb")
        crm.create_customer(company_name="B", contact_name="B", email="b@b.com", tier="strategic")
        n = crm.recompute_all_scores()
        assert n == 2
        for c in _CUSTOMERS.values():
            assert c.lead_score > 0

    def test_012_get_top_leads(self):
        for i in range(5):
            crm.create_customer(
                company_name=f"Co{i}", contact_name="X", email=f"x{i}@x.com",
                tier=("strategic" if i % 2 == 0 else "individual"),
            )
        crm.recompute_all_scores()
        top = get_top_leads(limit=3)
        assert len(top) == 3
        # sorted desc
        assert top[0].lead_score >= top[1].lead_score >= top[2].lead_score

    def test_013_get_top_leads_by_grade(self):
        crm.create_customer(company_name="Co1", contact_name="X", email="x@x.com", tier="strategic")
        crm.create_customer(company_name="Co2", contact_name="Y", email="y@y.com", tier="individual")
        crm.recompute_all_scores()
        a_leads = get_top_leads(limit=10, grade="A")
        # 至少有一个 strategic 客户
        assert all(c.lead_grade == "A" for c in a_leads)

    def test_014_get_lead_stats(self):
        crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        crm.create_customer(company_name="B", contact_name="B", email="b@b.com", tier="individual")
        crm.recompute_all_scores()
        s = get_lead_stats()
        assert s["total_customers"] == 2
        assert "A" in s["by_grade"]
        assert "D" in s["by_grade"]
        assert s["avg_lead_score"] > 0

    def test_015_add_followup_affects_score(self):
        c = crm.create_customer(
            company_name="Test", contact_name="X", email="t@t.com",
            tier="smb", industry="互联网/科技", size="11-50",
        )
        recompute_customer_score(c)
        score_before = c.lead_score
        c.add_followup("contract", "重要合同签订", by="sales")
        recompute_customer_score(c)
        assert c.lead_score > score_before


# ── 3. 路由测试 ──────────────────────────────────────────────────────────
class TestLeadRoutes:
    def test_020_create_customer_returns_lead_score(self, client):
        r = client.post("/api/v1/crm/customers", json={
            "company_name": "Test Co",
            "contact_name": "Alice",
            "email": "a@a.com",
            "tier": "strategic",
            "industry": "金融",
            "size": "1000+",
        })
        assert r.status_code == 200
        data = r.json()
        assert "lead_score" in data
        assert "lead_grade" in data
        assert data["lead_grade"] in ("A", "B", "C", "D")

    def test_021_top_leads_route(self, client):
        for i in range(3):
            client.post("/api/v1/crm/customers", json={
                "company_name": f"Co{i}", "contact_name": "X",
                "email": f"x{i}@x.com", "tier": "strategic",
            })
        r = client.get("/api/v1/crm/leads/top?limit=2")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] <= 2

    def test_022_stats_route(self, client):
        client.post("/api/v1/crm/customers", json={
            "company_name": "X", "contact_name": "X", "email": "x@x.com", "tier": "strategic",
        })
        r = client.get("/api/v1/crm/leads/stats")
        assert r.status_code == 200
        assert "by_grade" in r.json()

    def test_023_recompute_all_route(self, client):
        client.post("/api/v1/crm/customers", json={
            "company_name": "X", "contact_name": "X", "email": "x@x.com", "tier": "smb",
        })
        r = client.post("/api/v1/crm/leads/recompute")
        assert r.status_code == 200
        assert "recomputed" in r.json()

    def test_024_rescore_one_route(self, client):
        r1 = client.post("/api/v1/crm/customers", json={
            "company_name": "Y", "contact_name": "Y", "email": "y@y.com", "tier": "strategic",
        })
        cid = r1.json()["customer_id"]
        r2 = client.post(f"/api/v1/crm/customers/{cid}/rescore")
        assert r2.status_code == 200
        assert r2.json()["customer_id"] == cid
