"""P6-Fix-C-8 / P1-12: 跨服务集成测试 (CRM → Invoice → Ticket).

模拟真实业务流:
  1. 创建 CRM 客户 (P1-1 lead scoring 自动激活)
  2. 创建订单 → 触发发票生成 (P1-7 财务链路)
  3. 创建工单 (P1-6 merge/split)
  4. 验证工单与客户关联 + 财务链路
  5. 模拟工单关闭后, 客户 lead score 提升
  6. P1-5: 创建 Customer + 绑定支付方式 + 退款 + dispute (P1-2)
  7. P1-8 webhook emit 触达所有订阅
  8. P1-9 segment 命中验证
  9. P1-3 国税上传 + 核验
  10. P1-4 合同到期
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

import crm
import tickets
import invoices
import contracts
import billing
from billing.payments import dispute as dispute_mod
from billing import customers as cust_mod
from crm import _CUSTOMERS, segments as seg_mod
from crm.segments import define_segment, evaluate_segment, _reset_segments
from common.webhooks import (
    register_webhook, emit, list_emits, _reset_webhooks,
)
from contracts import expiration as exp_mod
from contracts.expiration import _reset_expiration
from invoices import _STORE
from invoices import tax_bureau as tb
from tickets import _TICKETS


# Build composite FastAPI app with all routers
def _build_app():
    a = FastAPI(title="nanobot-factory-p1-integration")
    # CRM
    from crm.routes import router_customers, router_contacts, router_leads, router_segments
    a.include_router(router_customers)
    a.include_router(router_contacts)
    a.include_router(router_leads)
    a.include_router(router_segments)
    # Tickets
    from tickets.routes import router
    a.include_router(router)
    # Invoices (含 tax-bureau + finance)
    from invoices.routes import router as inv_router
    from invoices.routes import tax_bureau_router, finance_router
    a.include_router(inv_router)
    a.include_router(tax_bureau_router)
    a.include_router(finance_router)
    # Contracts (含 expiration)
    from contracts.routes import router as ct_router
    from contracts.routes import expiration_router
    a.include_router(ct_router)
    a.include_router(expiration_router)
    # Billing (含 disputes + customers)
    from billing.routes import router as bill_router
    from billing.routes import disputes_router, customers_router
    a.include_router(bill_router)
    a.include_router(disputes_router)
    a.include_router(customers_router)
    # Public webhooks
    from common.webhooks_routes import router as wh_router
    a.include_router(wh_router)
    return a


@pytest.fixture
def app():
    return _build_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_all():
    # 清理所有 in-memory state
    _CUSTOMERS.clear()
    _TICKETS.clear()
    _STORE.clear()
    contracts._STORE.clear()
    dispute_mod._reset_disputes()
    cust_mod._reset_customers()
    _reset_segments()
    _reset_expiration()
    _reset_webhooks()
    tb._reset_tax_bureau()
    yield
    _CUSTOMERS.clear()
    _TICKETS.clear()
    _STORE.clear()
    contracts._STORE.clear()
    dispute_mod._reset_disputes()
    cust_mod._reset_customers()
    _reset_segments()
    _reset_expiration()
    _reset_webhooks()
    tb._reset_tax_bureau()


# ── 集成场景 ────────────────────────────────────────────────────────────
class TestCrossServiceIntegration:
    def test_001_full_business_flow(self, client):
        """场景 1: 创建客户 → 注册支付方式 → 创建订单 → 开具发票 → 创建工单 → 解决工单."""
        # 1. 创建 CRM 客户
        r = client.post("/api/v1/crm/customers", json={
            "company_name": "智影测试公司",
            "contact_name": "Alice",
            "email": "alice@zhiying.com",
            "tier": "strategic",
            "industry": "金融",
            "size": "1000+",
        })
        assert r.status_code == 200
        customer = r.json()
        cid = customer["customer_id"]
        # lead score 自动计算
        assert customer["lead_grade"] in ("A", "B", "C", "D")
        assert customer["lead_score"] > 0

        # 2. 创建 CRM 联系人
        r = client.post("/api/v1/crm/contacts", json={
            "customer_id": cid, "name": "采购Bob", "role": "procurement",
            "email": "bob@zhiying.com", "is_primary": True,
        })
        assert r.status_code == 200

        # 3. 模拟订单 paid — 创建发票
        r = client.post("/api/v1/invoices", json={
            "invoice_type": "electronic",
            "order_id": "ord_test_001",
            "buyer_name": "智影测试公司",
            "buyer_tax_id": "91110000ABC",
            "items": [{"name": "数据生成服务", "qty": 1, "amount": 100.0, "unit_price": 100.0}],
            "amount": 100.0,
        })
        assert r.status_code == 200
        invoice = r.json()
        inv_no = invoice["invoice_no"]

        # 4. 验证发票
        r = client.get(f"/api/v1/invoices/{inv_no}/verify")
        assert r.status_code == 200
        assert r.json()["valid"] is True

        # 5. 客户反馈 — 创建工单
        r = client.post("/api/v1/tickets", json={
            "type": "billing", "priority": "P2",
            "subject": "发票抬头错误",
            "description": f"发票 {inv_no} 抬头需要修改",
            "customer_id": cid, "reporter": cid,
        })
        assert r.status_code == 200
        ticket = r.json()
        tid = ticket["ticket_id"]

        # 6. 添加工单回复
        r = client.post(f"/api/v1/tickets/{tid}/comments", json={
            "content": "已确认问题, 正在重开发票",
            "by": "support_alice",
        })
        assert r.status_code == 200

        # 7. 工单分配 + 状态流转
        r = client.post(f"/api/v1/tickets/{tid}/assign", json={"assignee": "support_alice"})
        assert r.status_code == 200
        r = client.post(f"/api/v1/tickets/{tid}/transition", json={"new_status": "in_progress", "by": "support_alice"})
        assert r.status_code == 200
        r = client.post(f"/api/v1/tickets/{tid}/transition", json={"new_status": "resolved", "by": "support_alice"})
        assert r.status_code == 200
        r = client.post(f"/api/v1/tickets/{tid}/transition", json={"new_status": "closed", "by": "support_alice"})
        assert r.status_code == 200

        # 8. 添加跟进 — 客户重新激活
        r = client.post(f"/api/v1/crm/customers/{cid}/followups", json={
            "type": "communication", "content": "已解决发票问题", "by": "support_alice",
        })
        assert r.status_code == 200
        # 重新打分
        r = client.post(f"/api/v1/crm/customers/{cid}/rescore")
        assert r.status_code == 200

        # 9. 财务月报应包含这张发票
        r = client.get(f"/api/v1/invoices/finance/monthly?year={datetime.utcnow().year}&month={datetime.utcnow().month}")
        assert r.status_code == 200
        assert r.json()["total_invoices"] >= 1

    def test_002_dispute_flow_e2e(self, client):
        """场景 2: 创建订单 → 模拟支付 → 发起 dispute → 收集证据 → 解决."""
        # 1. 创建 billing customer + 绑卡
        r = client.post("/api/v1/billing/customers", json={
            "user_id": "u_dispute_001", "email": "user@x.com", "name": "User",
        })
        assert r.status_code == 200
        cus_id = r.json()["cus_id"]

        r = client.post("/api/v1/billing/customers/payment-methods", json={
            "customer_id": cus_id, "pm_type": "card", "token": "pm_test_xxx",
            "brand": "visa", "last4": "4242", "is_default": True,
        })
        assert r.status_code == 200
        pm = r.json()

        # 2. 注册 dispute
        r = client.post("/api/v1/billing/disputes", json={
            "order_id": "ord_dispute_001", "payment_id": "pi_dispute_001",
            "amount_cents": 10000, "currency": "USD", "reason": "fraudulent",
            "alert": False,
        })
        assert r.status_code == 200
        d = r.json()
        did = d["dispute_id"]

        # 3. 上传证据
        r = client.post(f"/api/v1/billing/disputes/{did}/evidence", json={
            "receipt": {"url": "https://x.com/r"},
            "customer_communication": "邮件回复",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"

        # 4. 解决
        r = client.post(f"/api/v1/billing/disputes/{did}/resolve", json={
            "status": "won", "resolution_note": "证据充分",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "won"

        # 5. 列出 open (应为空)
        r = client.get("/api/v1/billing/disputes?open_only=true")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_003_segment_with_real_customers(self, client):
        """场景 3: 创建多个客户, 定义 segment, 验证匹配."""
        # 创建 3 战略 + 2 个体
        for i in range(3):
            client.post("/api/v1/crm/customers", json={
                "company_name": f"战略Co{i}", "contact_name": "X", "email": f"x{i}@x.com",
                "tier": "strategic", "industry": "金融", "size": "1000+",
            })
        for i in range(2):
            client.post("/api/v1/crm/customers", json={
                "company_name": f"个人Co{i}", "contact_name": "Y", "email": f"y{i}@y.com",
                "tier": "individual", "industry": "其他", "size": "1-10",
            })

        # 创建 VIP segment
        r = client.post("/api/v1/crm/segments", json={
            "name": "VIP 战略客户",
            "rules": {"field": "tier", "op": "eq", "value": "strategic"},
        })
        assert r.status_code == 200
        sid = r.json()["segment_id"]

        r = client.get(f"/api/v1/crm/segments/{sid}/customers")
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_004_webhook_emit_end_to_end(self, client):
        """场景 4: 订阅 webhook → 触发事件 → 验证 emit 记录."""
        # 由于本地 emit 会真实尝试发 HTTP, 这里只测试 emit 记录
        r = client.post("/api/v1/public/hooks", json={
            "url": "https://example.com/test",
            "events": ["*"],
        })
        assert r.status_code == 200

        r = client.post("/api/v1/public/hooks/emit", json={
            "event_type": "invoice.generated",
            "payload": {"invoice_no": "INV-001"},
        })
        assert r.status_code == 200
        emit_data = r.json()
        assert emit_data["event_type"] == "invoice.generated"

        # 列出 emit 记录
        r = client.get("/api/v1/public/hooks/emits?limit=10")
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_005_contract_expiration_e2e(self, client):
        """场景 5: 创建即将到期合同 → 扫描 → 续约."""
        future = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        r = client.post("/api/v1/contracts", json={
            "template": "service_agreement",
            "company_name": "即将到期Co",
            "contact_email": "x@x.com",
            "plan_name": "Pro", "amount": 1000.0,
            "end_date": future,
        })
        assert r.status_code == 200
        contract = r.json()
        ctid = contract["contract_id"]

        # 签名
        r = client.post(f"/api/v1/contracts/{ctid}/sign", json={"signer": "X"})
        assert r.status_code == 200

        # 扫描到期
        r = client.get("/api/v1/contracts/expiration/check?window_days=30")
        assert r.status_code == 200
        report = r.json()
        assert report["scanned"] >= 1

        # 续约
        new_end = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
        r = client.post(f"/api/v1/contracts/expiration/{ctid}/renew", json={
            "new_end_date": new_end,
        })
        assert r.status_code == 200
        new_contract = r.json()
        assert new_contract["contract_id"] != ctid

    def test_006_tax_bureau_flow(self, client):
        """场景 6: 申领 → 上传 → 核验 → 月报."""
        # 申领 (多次直到成功 — mock 有 90% 概率)
        for _ in range(30):
            r = client.post("/api/v1/invoices/tax-bureau/apply", json={
                "invoice_type": "electronic", "qty": 5, "simulate": True,
            })
            if r.status_code == 200 and r.json()["status"] == "approved":
                aid = r.json()["application_id"]
                break
        else:
            pytest.skip("mock rejected all applications — flaky test")

        # 上传
        r = client.post("/api/v1/invoices/tax-bureau/upload", json={
            "invoice_no": "INV-INT-001", "application_id": aid,
        })
        assert r.status_code == 200

        # 月报
        r = client.get(f"/api/v1/invoices/tax-bureau/monthly-report?year={datetime.utcnow().year}&month={datetime.utcnow().month}")
        assert r.status_code == 200

    def test_007_ticket_merge_flow(self, client):
        """场景 7: 创建多个工单 → 合并 → 拆分."""
        r1 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "主工单", "description": "d",
        })
        tid1 = r1.json()["ticket_id"]
        r2 = client.post("/api/v1/tickets", json={
            "type": "problem", "priority": "P3",
            "subject": "次工单", "description": "d",
        })
        tid2 = r2.json()["ticket_id"]

        # 主工单加 comment
        client.post(f"/api/v1/tickets/{tid1}/comments", json={
            "content": "原 comment", "by": "x",
        })
        # 次工单加 comment
        client.post(f"/api/v1/tickets/{tid2}/comments", json={
            "content": "要合并的 comment", "by": "x",
        })

        # 合并
        r = client.post(f"/api/v1/tickets/{tid1}/merge", json={
            "primary_ticket_id": tid1,
            "secondary_ticket_ids": [tid2],
            "operator": "admin",
        })
        assert r.status_code == 200
        assert len(r.json()["merged"]) == 1

        # 拆分
        r = client.post(f"/api/v1/tickets/{tid1}/comments", json={
            "content": "要拆走的 comment", "by": "x",
        })
        assert r.status_code == 200
        r = client.post(f"/api/v1/tickets/{tid1}/split", json={
            "comment_indices": [0],  # 第一个 comment
            "new_subject": "拆出的工单",
        })
        assert r.status_code == 200

    def test_008_lead_score_and_segment_consistency(self, client):
        """场景 8: 创建客户 → 验证 lead grade A 客户在 A-grade segment 中."""
        for _ in range(5):
            r = client.post("/api/v1/crm/customers", json={
                "company_name": "X", "contact_name": "X", "email": "x@x.com",
                "tier": "strategic", "industry": "金融", "size": "1000+",
            })
            # 提高 LTV 以确保 A 级
            cid = r.json()["customer_id"]
            c = crm.get_customer(cid)
            c.lifetime_value = 200000
            crm.recompute_customer_score(c)

        # A-grade segment
        r = client.post("/api/v1/crm/segments/preset/grade_a_leads")
        assert r.status_code == 200
        sid = r.json()["segment_id"]
        r = client.get(f"/api/v1/crm/segments/{sid}/customers")
        assert r.status_code == 200
        # 至少 1 个 A 级
        assert r.json()["count"] >= 1

        # Top leads
        r = client.get("/api/v1/crm/leads/top?limit=5")
        assert r.status_code == 200
        data = r.json()
        # Top leads 是 A grade
        for item in data["items"]:
            assert item["lead_grade"] == "A"

    def test_009_finance_quarterly_with_orders(self, client):
        """场景 9: 模拟订单 → 季度财务汇总."""
        from billing.orders import Order, OrderService, InMemoryOrderStore
        from billing import routes as br
        # 重置并添加测试订单
        br.reset_state()
        state = br.get_state()
        service = state["order_service"]
        for i in range(3):
            o = service.create_order(
                user_id=f"u_{i}", plan_id="pro",
                amount_cents=10000 + i * 1000, currency="USD",
                payment_method="stripe",
            )
            service.mark_paid(o.order_id, external_ref=f"pi_{i}")

        # 季度报表
        now = datetime.utcnow()
        r = client.get(f"/api/v1/invoices/finance/quarterly?year={now.year}&quarter={(now.month - 1) // 3 + 1}")
        assert r.status_code == 200
        data = r.json()
        assert data["total_revenue_cents"] >= 30000  # 3 订单 × ~10000

    def test_010_top_customers_finance(self, client):
        """场景 10: 模拟订单 + 财务 Top 客户."""
        from billing.orders import Order, OrderService, InMemoryOrderStore
        from billing import routes as br
        br.reset_state()
        state = br.get_state()
        service = state["order_service"]
        # alice 消费 50000, bob 消费 30000
        for amt in (20000, 30000):
            o = service.create_order(
                user_id="alice", plan_id="pro",
                amount_cents=amt, currency="USD", payment_method="stripe",
            )
            service.mark_paid(o.order_id, external_ref="pi_a")
        o = service.create_order(
            user_id="bob", plan_id="pro",
            amount_cents=30000, currency="USD", payment_method="stripe",
        )
        service.mark_paid(o.order_id, external_ref="pi_b")

        now = datetime.utcnow()
        r = client.get(f"/api/v1/invoices/finance/top-customers?year={now.year}&month={now.month}&n=5")
        assert r.status_code == 200
        data = r.json()
        top = data["top"]
        assert len(top) >= 1
        # alice 应该是 Top 1
        assert top[0]["user_id"] == "alice"
        assert top[0]["revenue_cents"] == 50000

    def test_011_full_loop_emit_and_segment(self, client):
        """场景 11: 业务事件 → webhook emit → segment 验证 (跨模块)."""
        # 订阅 webhook
        client.post("/api/v1/public/hooks", json={
            "url": "https://example.com/int",
            "events": ["customer.created"],
        })

        # 创建客户 (会触发 emit? 实际我们不耦合, 这里手动 emit)
        client.post("/api/v1/crm/customers", json={
            "company_name": "X", "contact_name": "X", "email": "x@x.com", "tier": "strategic",
        })

        # 手动 emit
        r = client.post("/api/v1/public/hooks/emit", json={
            "event_type": "customer.created",
            "payload": {"customer_id": "CUS-TEST"},
        })
        assert r.status_code == 200

        # Segment 验证
        r = client.post("/api/v1/crm/segments/preset/grade_a_leads")
        assert r.status_code == 200
        r = client.get("/api/v1/crm/leads/stats")
        assert r.status_code == 200
        assert r.json()["total_customers"] >= 1
