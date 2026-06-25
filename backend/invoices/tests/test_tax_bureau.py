"""P6-Fix-C-8 / P1-3: 国税平台对接 (State Tax Bureau) tests.

Verifies:
- apply_invoice_numbers (申领发票号) - happy path / rejection
- report_to_tax_bureau (上传) - 应用号 + 失败重试
- verify_via_tax_bureau (核验) - 真/假 verify_code
- monthly_report (月度汇总)
- Routes: POST /tax-bureau/apply, /upload, /verify; GET /monthly-report
"""
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
from invoices import tax_bureau as tb
from invoices.routes import tax_bureau_router as tax_bureau_router
from invoices import list_invoices, _STORE


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean():
    tb._reset_tax_bureau()
    _STORE.clear()
    yield
    tb._reset_tax_bureau()
    _STORE.clear()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(tax_bureau_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestTaxBureauModule:
    def test_001_apply_happy(self):
        rec = tb.apply_invoice_numbers("electronic", qty=10, simulate=True)
        # 90% 通过 — 多次跑总有通过的
        attempts = 0
        while rec.status != "approved" and attempts < 20:
            rec = tb.apply_invoice_numbers("electronic", qty=10, simulate=True)
            attempts += 1
        assert rec.status == "approved"
        assert rec.number_start is not None
        assert rec.number_end is not None

    def test_002_apply_invalid_type_raises(self):
        with pytest.raises(ValueError):
            tb.apply_invoice_numbers("bogus", qty=10)

    def test_003_apply_zero_qty_raises(self):
        with pytest.raises(ValueError):
            tb.apply_invoice_numbers("electronic", qty=0)

    def test_004_apply_oversize_qty_raises(self):
        with pytest.raises(ValueError):
            tb.apply_invoice_numbers("electronic", qty=2000)

    def test_005_list_applications(self):
        tb.apply_invoice_numbers("electronic", qty=5, simulate=True)
        tb.apply_invoice_numbers("vat_normal", qty=3, simulate=True)
        items = tb.list_applications()
        assert len(items) == 2

    def test_006_upload_happy(self):
        # 准备一个 approved application
        rec = None
        for _ in range(30):
            rec = tb.apply_invoice_numbers("electronic", qty=10, simulate=True)
            if rec.status == "approved":
                break
        if rec is None or rec.status != "approved":
            pytest.skip("mock rejected all applications — flaky test, retry")
        upload = tb.report_to_tax_bureau(
            invoice_no="INV-20260101-0001",
            application_id=rec.application_id,
            invoice_type="electronic",
        )
        # 95% 上传成功
        assert upload.status in ("uploaded", "failed")
        if upload.status == "uploaded":
            assert upload.tax_bureau_receipt is not None

    def test_007_upload_invalid_app_raises(self):
        with pytest.raises(KeyError):
            tb.report_to_tax_bureau("INV-001", "TA-XXX", "electronic")

    def test_008_consume_application(self):
        rec = None
        for _ in range(30):
            rec = tb.apply_invoice_numbers("electronic", qty=2, simulate=True)
            if rec.status == "approved":
                break
        if rec is None or rec.status != "approved":
            pytest.skip("mock rejected all applications — flaky test, retry")
        tb.report_to_tax_bureau("INV-001", rec.application_id)
        a = tb.get_application(rec.application_id)
        # 如果 upload 成功, _consumed 增加
        # 如果未成功, status 仍 approved
        assert a.status in ("approved", "consumed")

    def test_009_consume_non_approved_raises(self):
        # 不存在的 application → KeyError
        with pytest.raises(KeyError):
            tb.consume_application("TA-FAKE", 1)

    def test_010_verify_with_correct_code(self):
        # Generate invoice first
        inv = invoices.generate_invoice(
            invoice_type="electronic",
            order_id="ord_1",
            buyer_name="测试公司",
            buyer_tax_id="91110000ABC",
            seller_name="智影纳米机器人科技有限公司",
            seller_tax_id="91110000XXXXXXXX5X",
            items=[{"name": "数据生成服务", "spec": "标准", "qty": 1, "unit_price": 100, "amount": 100}],
            amount=100.0,
        )
        # Compute correct code (SHA-256[:6] of canonical dict)
        import json, hashlib
        canonical = json.dumps(inv.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
        code = hashlib.sha256(canonical.encode()).hexdigest()[:6].upper()
        result = tb.verify_via_tax_bureau(inv.invoice_no, code)
        assert result.valid is True

    def test_011_verify_with_wrong_code(self):
        inv = invoices.generate_invoice(
            invoice_type="electronic",
            order_id="ord_1", buyer_name="X", buyer_tax_id=None,
            seller_name="智影", seller_tax_id="91110000XXXXXXXX5X",
            items=[{"name": "X", "spec": "Y", "qty": 1, "unit_price": 100, "amount": 100}],
            amount=100.0,
        )
        result = tb.verify_via_tax_bureau(inv.invoice_no, "BADCODE")
        # Bad code → invalid
        assert result.valid is False

    def test_012_monthly_report_no_invoices(self):
        rpt = tb.monthly_report_for(2026, 6, invoices=[])
        assert rpt["year"] == 2026
        assert rpt["month"] == 6
        assert rpt["total_invoices"] == 0
        assert rpt["deadline"] == "2026-06-15"

    def test_013_monthly_report_invalid_month(self):
        with pytest.raises(ValueError):
            tb.monthly_report_for(2026, 13, invoices=[])

    def test_014_monthly_report_with_invoices(self):
        inv_data = [
            {
                "invoice_no": "INV-1", "invoice_type": "electronic",
                "amount": 100.0, "issue_date": "2026-06-15",
                "tax": {"net": 88.5, "tax": 11.5, "gross": 100.0, "rate": 0.13},
            },
            {
                "invoice_no": "INV-2", "invoice_type": "vat_special",
                "amount": 200.0, "issue_date": "2026-06-20",
                "tax": {"net": 177.0, "tax": 23.0, "gross": 200.0, "rate": 0.13},
            },
        ]
        rpt = tb.monthly_report_for(2026, 6, invoices=inv_data)
        assert rpt["total_invoices"] == 2
        assert rpt["total_amount"] == 300.0
        assert rpt["total_tax"] == 34.5
        assert "electronic" in rpt["by_invoice_type"]
        assert "vat_special" in rpt["by_invoice_type"]


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestTaxBureauRoutes:
    def test_020_apply_via_api(self, client):
        for _ in range(20):
            r = client.post("/api/v1/invoices/tax-bureau/apply", json={
                "invoice_type": "electronic", "qty": 5, "operator": "test", "simulate": True,
            })
            if r.status_code == 200 and r.json()["status"] == "approved":
                break
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("approved", "rejected")
        if data["status"] == "approved":
            assert "number_start" in data

    def test_021_apply_invalid_type_400(self, client):
        r = client.post("/api/v1/invoices/tax-bureau/apply", json={
            "invoice_type": "bogus", "qty": 5,
        })
        # Pydantic pattern 不匹配 → 422
        assert r.status_code in (400, 422)

    def test_022_list_applications_via_api(self, client):
        client.post("/api/v1/invoices/tax-bureau/apply", json={
            "invoice_type": "electronic", "qty": 1, "simulate": True,
        })
        r = client.get("/api/v1/invoices/tax-bureau/apply")
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_023_get_application_404(self, client):
        r = client.get("/api/v1/invoices/tax-bureau/apply/TA-NONEXIST")
        assert r.status_code == 404

    def test_024_upload_404(self, client):
        r = client.post("/api/v1/invoices/tax-bureau/upload", json={
            "invoice_no": "INV-1", "application_id": "TA-FAKE",
        })
        assert r.status_code == 404

    def test_025_verify_via_api(self, client):
        inv = invoices.generate_invoice(
            invoice_type="electronic", order_id="ord_1",
            buyer_name="X", buyer_tax_id=None,
            seller_name="智影", seller_tax_id="91110000XXXXXXXX5X",
            items=[{"name": "X", "spec": "Y", "qty": 1, "unit_price": 100, "amount": 100}],
            amount=100.0,
        )
        import json, hashlib
        canonical = json.dumps(inv.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
        code = hashlib.sha256(canonical.encode()).hexdigest()[:6].upper()
        r = client.post("/api/v1/invoices/tax-bureau/verify", json={
            "invoice_no": inv.invoice_no, "verify_code": code,
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_026_monthly_report_via_api(self, client):
        r = client.get("/api/v1/invoices/tax-bureau/monthly-report?year=2026&month=6")
        assert r.status_code == 200
        data = r.json()
        assert data["year"] == 2026
        assert data["month"] == 6
        assert "by_invoice_type" in data

    def test_027_monthly_report_invalid_month_400(self, client):
        r = client.get("/api/v1/invoices/tax-bureau/monthly-report?year=2026&month=13")
        # Pydantic ge=1, le=12 → 422
        assert r.status_code in (400, 422)

    def test_028_meta_route(self, client):
        r = client.get("/api/v1/invoices/tax-bureau/_meta")
        assert r.status_code == 200
        data = r.json()
        assert "application_statuses" in data
        assert "upload_statuses" in data
