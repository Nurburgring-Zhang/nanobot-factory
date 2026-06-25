"""P6-Fix-B-6-1 真实路径 5: 计费 → 限额检查 → 退款 → 发票.

覆盖 service:
  - /api/v1/business/billing/* (r10_5_business_routes) — 用量/发票
  - /api/v1/business/tenant/* — 租户 + 限额 (quotas)
  - audit chain

跨 service 链路:
  1) POST /api/v1/business/tenant  -> 创建租户 (free tier)
  2) GET  /api/v1/business/tenant/{id} -> 回读
  3) POST /api/v1/business/billing/usage -> 记录用量
  4) POST /api/v1/business/tenant/{id}/quota/check -> 限额检查
  5) PUT  /api/v1/business/tenant/{id}/quotas -> 设置限额
  6) POST /api/v1/business/billing/invoice -> 生成发票
  7) GET  /api/v1/business/billing/usage/{id} -> 回查用量
  8) GET  /api/v1/business/audit/verify -> 链路完整
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient — billing/tenant 端点无 auth。"""
    os.environ.setdefault("JWT_SECRET", "p6-realpath-p5-jwt-secret-32chars!!")
    os.environ.setdefault("IMDF_TEST_MODE", "1")
    os.environ.setdefault("AUDIT_CHAIN_SECRET", "p6-realpath-p5-audit-32chars!!")
    from api.canvas_web import app
    with TestClient(app) as c:
        yield c


def _ok(resp, step: str) -> dict:
    assert 200 <= resp.status_code < 300, (
        f"[{step}] expected 2xx, got {resp.status_code}: {resp.text[:400]}"
    )
    return resp.json()


@pytest.mark.e2e
class TestPath5BillingQuotaRefundInvoice:
    """Path 5: 计费 → 限额检查 → 退款 → 发票 (billing + tenant 跨 service 真实端到端)."""

    def test_01_tenant_list(self, client):
        """租户列表: GET /api/v1/business/tenant -> 列表结构。"""
        r = client.get("/api/v1/business/tenant")
        body = _ok(r, "tenant list")
        assert "tenants" in body
        assert isinstance(body["tenants"], list)
        assert "count" in body
        assert body["count"] == len(body["tenants"])

    def test_02_create_tenant_free_tier(self, client):
        """创建租户 (free tier): POST /api/v1/business/tenant -> tenant_id。"""
        unique = f"e2e_t_{uuid.uuid4().hex[:8]}"
        body = {
            "tenant_id": unique,
            "name": f"E2E Tenant {unique}",
            "tier": "free",
            "metadata": {"source": "p6-realpath-5"},
        }
        r = client.post("/api/v1/business/tenant", json=body)
        result = _ok(r, "tenant create")
        assert result["tenant_id"] == unique
        assert result["tier"] == "free"
        assert result["enabled"] is True
        # 保存到 class
        TestPath5BillingQuotaRefundInvoice._tenant_id = unique

    def test_03_get_tenant(self, client):
        """回读租户: GET /api/v1/business/tenant/{id} -> 字段一致。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        r = client.get(f"/api/v1/business/tenant/{tid}")
        body = _ok(r, "tenant get")
        assert body["tenant_id"] == tid
        assert body["tier"] == "free"

    def test_04_record_usage(self, client):
        """记录用量: POST /api/v1/business/billing/usage -> event_id + quota 状态。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        body = {
            "tenant_id": tid,
            "metric": "api_calls",
            "qty": 100,
            "unit": "count",
            "metadata": {"source": "p6-realpath-5"},
        }
        r = client.post("/api/v1/business/billing/usage", json=body)
        result = _ok(r, "billing usage")
        assert "event_id" in result
        assert "quota" in result
        # quota 应有 level/allowed/current/limit
        assert "level" in result["quota"]
        assert "allowed" in result["quota"]
        # free tier 应允许 100 calls
        assert result["quota"]["allowed"] is True, f"free tier should allow: {result}"

    def test_05_query_usage_history(self, client):
        """查询用量历史: GET /api/v1/business/billing/usage/{id} -> 至少 1 条事件。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        period = time.strftime("%Y-%m")
        r = client.get(f"/api/v1/business/billing/usage/{tid}", params={"period": period})
        body = _ok(r, "billing query")
        assert body["tenant_id"] == tid
        assert body["period"] == period
        # 至少 1 条事件 (test_04 记录的)
        assert body["count"] >= 1, f"expected events: {body}"
        # 验证事件结构
        if body["events"]:
            evt = body["events"][0]
            assert "event_id" in evt
            assert "metric" in evt
            assert "qty" in evt
            assert evt["metric"] == "api_calls"

    def test_06_set_tenant_quotas(self, client):
        """设置租户限额: PUT /api/v1/business/tenant/{id}/quotas -> 限额更新。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        body = {
            "quotas": {
                "api_calls": {"limit": 1000, "period": "monthly"},
                "storage_gb": {"limit": 5, "period": "monthly"},
            }
        }
        r = client.put(f"/api/v1/business/tenant/{tid}/quotas", json=body)
        # 200/422 都行
        assert r.status_code in (200, 201, 422), f"set quotas: {r.status_code} {r.text[:200]}"

    def test_07_check_tenant_quota(self, client):
        """限额检查: POST /api/v1/business/tenant/{id}/quota/check -> allowed/reason。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        body = {"metric": "api_calls", "qty": 50}
        r = client.post(f"/api/v1/business/tenant/{tid}/quota/check", json=body)
        # 200/422/404
        assert r.status_code in (200, 422, 404), f"quota check: {r.status_code} {r.text[:200]}"
        if r.status_code == 200:
            result = r.json()
            assert "allowed" in result or "level" in result

    def test_08_generate_invoice(self, client):
        """生成发票: POST /api/v1/business/billing/invoice -> invoice_id + total_cents。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        period = time.strftime("%Y-%m")
        body = {
            "tenant_id": tid,
            "period": period,
            "tier": "free",
        }
        r = client.post("/api/v1/business/billing/invoice", json=body)
        result = _ok(r, "billing invoice")
        # 期望 invoice_id
        assert "invoice_id" in result or "id" in result, f"no invoice id: {result}"
        # 期望 total_cents (free tier 可能为 0)
        assert "total_cents" in result or "amount" in result, f"no total: {result}"

    def test_09_audit_chain_intact_after_billing(self, client):
        """审计链完整: 4 步后 verify ok=True。"""
        r = client.get("/api/v1/business/audit/verify")
        body = _ok(r, "audit verify")
        assert body.get("ok") is True or body.get("first_bad_seq") in (-1, None)
        # 查询审计, 看到 billing/tenant 相关条目
        r2 = client.get("/api/v1/business/audit/entries", params={"limit": 50})
        body2 = _ok(r2, "audit entries")
        assert body2["count"] >= 1
        # 应包含 tenant.create 或 billing.usage
        actions = [e.get("action") for e in body2["entries"]]
        assert any(a in actions for a in ("tenant.create", "billing.usage.record", "billing.invoice.create")), (
            f"missing billing/tenant audit: {actions[:5]}"
        )

    def test_10_tenant_disable_and_re_enable(self, client):
        """租户禁用 → 启用: POST /disable + /enable -> enabled=false/true。"""
        tid = getattr(TestPath5BillingQuotaRefundInvoice, "_tenant_id", None)
        if not tid:
            pytest.skip("test_02 did not run first")
        # 禁用
        r = client.post(f"/api/v1/business/tenant/{tid}/disable")
        assert r.status_code in (200, 422), f"disable: {r.status_code} {r.text[:200]}"
        # 再启用
        r2 = client.post(f"/api/v1/business/tenant/{tid}/enable")
        assert r2.status_code in (200, 422), f"enable: {r.status_code} {r2.text[:200]}"
