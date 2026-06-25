"""P6-Fix-C-8 / P1-9: 客户细分 (Segments) tests."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

import crm
from crm import _CUSTOMERS
from crm.segments import (
    define_segment, evaluate_segment, match_customers,
    list_segments, get_segment, delete_segment, update_segment_count,
    evaluate_all_segments, get_segment_stats, create_preset,
    PRESET_TEMPLATES, _reset_segments,
)
from crm.routes import router_customers, router_segments


@pytest.fixture(autouse=True)
def _clean():
    _CUSTOMERS.clear()
    _reset_segments()
    yield
    _CUSTOMERS.clear()
    _reset_segments()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router_customers)
    a.include_router(router_segments)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 规则评估单元测试 ──────────────────────────────────────────────────
class TestRuleEvaluation:
    def test_001_simple_eq(self):
        s = define_segment("VIP", rules={"field": "tier", "op": "eq", "value": "strategic"})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        assert evaluate_segment(s, c) is True

    def test_002_simple_ne(self):
        s = define_segment("NotVIP", rules={"field": "tier", "op": "ne", "value": "strategic"})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        assert evaluate_segment(s, c) is False

    def test_003_gt_gte(self):
        s = define_segment("HighLTV", rules={"field": "lifetime_value", "op": "gt", "value": 10000})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        c.lifetime_value = 50000
        assert evaluate_segment(s, c) is True
        c.lifetime_value = 5000
        assert evaluate_segment(s, c) is False

    def test_004_in(self):
        s = define_segment(
            "BigTier",
            rules={"field": "tier", "op": "in", "value": ["large", "strategic"]},
        )
        c1 = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="large")
        c2 = crm.create_customer(company_name="B", contact_name="B", email="b@b.com", tier="smb")
        assert evaluate_segment(s, c1) is True
        assert evaluate_segment(s, c2) is False

    def test_005_contains(self):
        s = define_segment(
            "HasVipTag",
            rules={"field": "tags", "op": "contains", "value": "vip"},
        )
        c = crm.create_customer(
            company_name="A", contact_name="A", email="a@a.com", tags=["vip", "priority"],
        )
        assert evaluate_segment(s, c) is True

    def test_006_and_combinator(self):
        s = define_segment("HighValue", rules={
            "combinator": "and",
            "rules": [
                {"field": "tier", "op": "in", "value": ["large", "strategic"]},
                {"field": "lifetime_value", "op": "gt", "value": 100000},
            ],
        })
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        c.lifetime_value = 200000
        assert evaluate_segment(s, c) is True
        c.lifetime_value = 50000
        assert evaluate_segment(s, c) is False

    def test_007_or_combinator(self):
        s = define_segment("AnyBig", rules={
            "combinator": "or",
            "rules": [
                {"field": "tier", "op": "eq", "value": "strategic"},
                {"field": "industry", "op": "eq", "value": "金融"},
            ],
        })
        c1 = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic", industry="其他")
        c2 = crm.create_customer(company_name="B", contact_name="B", email="b@b.com", tier="smb", industry="金融")
        c3 = crm.create_customer(company_name="C", contact_name="C", email="c@c.com", tier="smb", industry="其他")
        assert evaluate_segment(s, c1) is True
        assert evaluate_segment(s, c2) is True
        assert evaluate_segment(s, c3) is False

    def test_008_derived_followup_count(self):
        s = define_segment("HasFollowup", rules={
            "field": "followup_count", "op": "gte", "value": 1,
        })
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        assert evaluate_segment(s, c) is False
        c.add_followup("communication", "Hi", by="x")
        assert evaluate_segment(s, c) is True

    def test_009_derived_complaint_count(self):
        s = define_segment("Complained", rules={
            "field": "complaint_count", "op": "gte", "value": 1,
        })
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        c.add_followup("complaint", "服务差", by="user")
        assert evaluate_segment(s, c) is True

    def test_010_derived_days_since_signup(self):
        s = define_segment("NewLead", rules={
            "field": "days_since_signup", "op": "lte", "value": 7,
        })
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        # 刚注册, 应该 < 7 天
        assert evaluate_segment(s, c) is True

    def test_011_invalid_field(self):
        s = define_segment("Bad", rules={"field": "unknown_field", "op": "eq", "value": "x"})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        # 未知字段 → False
        assert evaluate_segment(s, c) is False

    def test_012_invalid_op(self):
        s = define_segment("Bad", rules={"field": "tier", "op": "bogus_op", "value": "x"})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        assert evaluate_segment(s, c) is False

    def test_013_match_customers(self):
        for _ in range(3):
            crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        for _ in range(2):
            crm.create_customer(company_name="B", contact_name="B", email="b@b.com", tier="individual")
        s = define_segment("VIP", rules={"field": "tier", "op": "eq", "value": "strategic"})
        matches = match_customers(s)
        assert len(matches) == 3

    def test_020_preset_high_value(self):
        s = create_preset("high_value")
        c = crm.create_customer(
            company_name="A", contact_name="A", email="a@a.com",
            tier="strategic", industry="金融", size="1000+",
        )
        c.lifetime_value = 100000
        c.updated_at = datetime.utcnow().isoformat()
        # 满足所有条件
        assert evaluate_segment(s, c) is True

    def test_021_preset_at_risk_churn(self):
        s = create_preset("at_risk_churn")
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com")
        c.add_followup("complaint", "no good", by="user")
        c.updated_at = (datetime.utcnow() - timedelta(days=60)).isoformat()
        assert evaluate_segment(s, c) is True

    def test_022_preset_unknown_raises(self):
        with pytest.raises(ValueError):
            create_preset("bogus_preset")

    def test_023_evaluate_all_segments(self):
        s1 = define_segment("S1", rules={"field": "tier", "op": "eq", "value": "strategic"})
        s2 = define_segment("S2", rules={"field": "tier", "op": "eq", "value": "individual"})
        c = crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        result = evaluate_all_segments(c)
        assert result[s1.segment_id] is True
        assert result[s2.segment_id] is False

    def test_024_stats(self):
        define_segment("S1", rules={"field": "industry", "op": "eq", "value": "金融"})
        define_segment("S2", rules={"field": "industry", "op": "eq", "value": "其他"})
        crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic", industry="金融")
        s = get_segment_stats()
        assert s["total_segments"] == 2
        assert sum(s["by_id"].values()) == 1

    def test_025_invalid_segment_definition(self):
        with pytest.raises(ValueError):
            define_segment("X", rules={})  # 无 rules / field

    def test_026_update_count(self):
        s = define_segment("S", rules={"field": "tier", "op": "eq", "value": "strategic"})
        for _ in range(3):
            crm.create_customer(company_name="A", contact_name="A", email="a@a.com", tier="strategic")
        counts = update_segment_count()
        assert counts[s.segment_id] == 3


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestSegmentRoutes:
    def test_030_define_via_api(self, client):
        r = client.post("/api/v1/crm/segments", json={
            "name": "VIP",
            "description": "战略客户",
            "rules": {"field": "tier", "op": "eq", "value": "strategic"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "VIP"
        assert data["segment_id"].startswith("SG-")

    def test_031_define_invalid_400(self, client):
        r = client.post("/api/v1/crm/segments", json={
            "name": "Bad", "rules": {},
        })
        assert r.status_code == 400

    def test_032_preset_via_api(self, client):
        r = client.post("/api/v1/crm/segments/preset/high_value")
        assert r.status_code == 200
        assert r.json()["name"] == "高价值客户"

    def test_033_preset_invalid_400(self, client):
        r = client.post("/api/v1/crm/segments/preset/bogus")
        assert r.status_code == 400

    def test_034_list_via_api(self, client):
        client.post("/api/v1/crm/segments", json={
            "name": "A", "rules": {"field": "tier", "op": "eq", "value": "strategic"},
        })
        client.post("/api/v1/crm/segments", json={
            "name": "B", "rules": {"field": "tier", "op": "eq", "value": "individual"},
        })
        r = client.get("/api/v1/crm/segments")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_035_get_one(self, client):
        r1 = client.post("/api/v1/crm/segments", json={
            "name": "X", "rules": {"field": "tier", "op": "eq", "value": "strategic"},
        })
        sid = r1.json()["segment_id"]
        r = client.get(f"/api/v1/crm/segments/{sid}")
        assert r.status_code == 200

    def test_036_get_404(self, client):
        r = client.get("/api/v1/crm/segments/SG-FAKE")
        assert r.status_code == 404

    def test_037_match_customers_via_api(self, client):
        # 创建几个客户
        for _ in range(2):
            client.post("/api/v1/crm/customers", json={
                "company_name": "A", "contact_name": "A", "email": "a@a.com", "tier": "strategic",
            })
        client.post("/api/v1/crm/customers", json={
            "company_name": "B", "contact_name": "B", "email": "b@b.com", "tier": "individual",
        })
        # 定义 segment
        r1 = client.post("/api/v1/crm/segments", json={
            "name": "VIP", "rules": {"field": "tier", "op": "eq", "value": "strategic"},
        })
        sid = r1.json()["segment_id"]
        r = client.get(f"/api/v1/crm/segments/{sid}/customers")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_038_delete_via_api(self, client):
        r1 = client.post("/api/v1/crm/segments", json={
            "name": "X", "rules": {"field": "tier", "op": "eq", "value": "x"},
        })
        sid = r1.json()["segment_id"]
        r = client.delete(f"/api/v1/crm/segments/{sid}")
        assert r.status_code == 200

    def test_039_delete_404(self, client):
        r = client.delete("/api/v1/crm/segments/SG-FAKE")
        assert r.status_code == 404

    def test_040_meta_route(self, client):
        r = client.get("/api/v1/crm/segments/_meta")
        assert r.status_code == 200
        data = r.json()
        assert "tier" in data["supported_fields"]
        assert "high_value" in data["presets"]

    def test_041_stats_route(self, client):
        client.post("/api/v1/crm/segments", json={
            "name": "A", "rules": {"field": "tier", "op": "eq", "value": "x"},
        })
        r = client.get("/api/v1/crm/segments/stats")
        assert r.status_code == 200
        assert r.json()["total_segments"] == 1
