"""P6-Fix-C-8 / P1-7: 财务月度报表 tests."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter

import invoices
from invoices import _STORE
from invoices.financial_report import (
    generate_monthly_report, get_revenue_by_payment_method,
    get_top_customers_by_revenue, generate_quarterly_report, export_report_csv,
    MonthlyFinancialReport,
)
from invoices.routes import finance_router as finance_router


@pytest.fixture(autouse=True)
def _clean():
    _STORE.clear()
    yield
    _STORE.clear()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(finance_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestFinancialReportModule:
    def test_001_generate_with_invoices(self):
        invoices_list = [
            {
                "invoice_no": "INV-1", "invoice_type": "electronic",
                "amount": 100.0, "issue_date": "2026-06-15",
                "tax": {"net": 88.5, "tax": 11.5, "gross": 100.0, "rate": 0.13},
            },
            {
                "invoice_no": "INV-2", "invoice_type": "electronic",
                "amount": 200.0, "issue_date": "2026-06-20",
                "tax": {"net": 177.0, "tax": 23.0, "gross": 200.0, "rate": 0.13},
            },
        ]
        rpt = generate_monthly_report(2026, 6, invoices=invoices_list, orders=[])
        assert rpt.total_invoices == 2
        assert rpt.total_invoice_amount_cents == 30000  # 300 元 = 30000 分
        assert rpt.total_tax_cents == 3450  # 34.5 元 = 3450 分

    def test_002_generate_with_orders(self):
        from dataclasses import dataclass
        @dataclass
        class FakeOrder:
            order_id: str = "o1"
            user_id: str = "u1"
            plan_id: str = "pro"
            amount_cents: int = 9900
            currency: str = "USD"
            status = "paid"
            payment_method: str = "stripe"
            created_at: str = "2026-06-15T00:00:00+00:00"
        orders = [FakeOrder()]
        rpt = generate_monthly_report(2026, 6, invoices=[], orders=orders)
        assert rpt.total_orders == 1
        assert rpt.paid_orders == 1
        assert rpt.total_revenue_cents == 9900
        assert rpt.by_payment_method["stripe"] == 9900

    def test_003_top_customers(self):
        from dataclasses import dataclass
        @dataclass
        class FakeOrder:
            order_id: str = ""
            user_id: str = ""
            plan_id: str = "pro"
            amount_cents: int = 0
            currency: str = "USD"
            status = "paid"
            payment_method: str = "stripe"
            created_at: str = "2026-06-15T00:00:00+00:00"
        orders = [
            FakeOrder(order_id="o1", user_id="alice", amount_cents=10000),
            FakeOrder(order_id="o2", user_id="bob", amount_cents=5000),
            FakeOrder(order_id="o3", user_id="alice", amount_cents=2000),
        ]
        rpt = generate_monthly_report(2026, 6, invoices=[], orders=orders)
        assert rpt.top_customers[0]["user_id"] == "alice"
        assert rpt.top_customers[0]["revenue_cents"] == 12000

    def test_004_invalid_month(self):
        with pytest.raises(ValueError):
            generate_monthly_report(2026, 13, invoices=[], orders=[])

    def test_005_invalid_year(self):
        with pytest.raises(ValueError):
            generate_monthly_report(1999, 1, invoices=[], orders=[])

    def test_006_quarterly(self):
        result = generate_quarterly_report(2026, 2)
        assert result["year"] == 2026
        assert result["quarter"] == 2
        assert len(result["monthly_breakdown"]) == 3

    def test_007_quarterly_invalid(self):
        with pytest.raises(ValueError):
            generate_quarterly_report(2026, 5)

    def test_008_export_csv(self):
        rpt = generate_monthly_report(2026, 6, invoices=[], orders=[])
        csv_text = export_report_csv(rpt)
        assert "维度" in csv_text
        assert "2026" in csv_text
        assert "总订单数" in csv_text

    def test_009_revenue_by_method(self):
        from dataclasses import dataclass
        @dataclass
        class FakeOrder:
            order_id: str = "o1"
            user_id: str = "u1"
            plan_id: str = "pro"
            amount_cents: int = 1000
            currency: str = "USD"
            status = "paid"
            payment_method: str = "stripe"
            created_at: str = "2026-06-15T00:00:00+00:00"
        orders = [FakeOrder(payment_method="stripe"), FakeOrder(payment_method="alipay", amount_cents=2000)]
        result = get_revenue_by_payment_method.__wrapped__ if hasattr(get_revenue_by_payment_method, '__wrapped__') else None
        # Use generate_monthly_report directly
        rpt = generate_monthly_report(2026, 6, invoices=[], orders=orders)
        assert rpt.by_payment_method["stripe"] == 1000
        assert rpt.by_payment_method["alipay"] == 2000

    def test_010_top_customers_helper(self):
        from dataclasses import dataclass
        @dataclass
        class FakeOrder:
            order_id: str = "o1"
            user_id: str = "u1"
            plan_id: str = "pro"
            amount_cents: int = 1000
            currency: str = "USD"
            status = "paid"
            payment_method: str = "stripe"
            created_at: str = "2026-06-15T00:00:00+00:00"
        orders = [FakeOrder(user_id="alice"), FakeOrder(user_id="bob", amount_cents=2000)]
        rpt = generate_monthly_report(2026, 6, invoices=[], orders=orders)
        top = rpt.top_customers
        assert top[0]["user_id"] == "bob"  # 2000 > 1000


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestFinancialReportRoutes:
    def test_020_monthly_route(self, client):
        r = client.get("/api/v1/invoices/finance/monthly?year=2026&month=6")
        assert r.status_code == 200
        data = r.json()
        assert data["year"] == 2026
        assert data["month"] == 6
        assert "total_revenue_cents" in data

    def test_021_monthly_invalid_400(self, client):
        r = client.get("/api/v1/invoices/finance/monthly?year=2026&month=13")
        # Pydantic ge=1, le=12 → 422
        assert r.status_code in (400, 422)

    def test_022_monthly_csv_route(self, client):
        r = client.get("/api/v1/invoices/finance/monthly/csv?year=2026&month=6")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        text = r.text
        assert "维度" in text

    def test_023_quarterly_route(self, client):
        r = client.get("/api/v1/invoices/finance/quarterly?year=2026&quarter=1")
        assert r.status_code == 200
        data = r.json()
        assert data["quarter"] == 1
        assert len(data["monthly_breakdown"]) == 3

    def test_024_quarterly_invalid_400(self, client):
        r = client.get("/api/v1/invoices/finance/quarterly?year=2026&quarter=5")
        # Pydantic ge=1, le=4 → 422
        assert r.status_code in (400, 422)

    def test_025_revenue_by_method_route(self, client):
        r = client.get("/api/v1/invoices/finance/revenue-by-method?year=2026&month=6")
        assert r.status_code == 200
        data = r.json()
        assert "by_method_cents" in data

    def test_026_top_customers_route(self, client):
        r = client.get("/api/v1/invoices/finance/top-customers?year=2026&month=6&n=5")
        assert r.status_code == 200
        data = r.json()
        assert "top" in data
        assert len(data["top"]) <= 5
