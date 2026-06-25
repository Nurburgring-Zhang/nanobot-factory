"""
P4-10-W2: 发票 HTTP API
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, EmailStr

from . import (
    TEMPLATE_TYPES,
    generate_invoice,
    verify_invoice,
    get_invoice,
    list_invoices,
    save_invoice_pdf,
    save_invoice_ofd,
    on_order_paid,
    calc_tax,
)
from .tax_bureau import (
    APPLICATION_STATUSES, UPLOAD_STATUSES, INVOICE_TYPES_SUPPORTED,
    ApplicationRecord, UploadRecord, VerifyResult,
    apply_invoice_numbers, get_application, list_applications, consume_application,
    report_to_tax_bureau, get_upload, list_uploads,
    verify_via_tax_bureau,
    monthly_report, monthly_report_for,
)
from .financial_report import (
    MonthlyFinancialReport,
    generate_monthly_report, get_revenue_by_payment_method,
    get_top_customers_by_revenue, generate_quarterly_report, export_report_csv,
)

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])
tax_bureau_router = APIRouter(prefix="/api/v1/invoices/tax-bureau", tags=["invoices-tax-bureau"])
finance_router = APIRouter(prefix="/api/v1/invoices/finance", tags=["invoices-finance"])


class InvoiceItem(BaseModel):
    name: str
    spec: str = "标准"
    qty: int = 1
    unit_price: float = 0.0
    amount: float = 0.0


class InvoiceCreate(BaseModel):
    invoice_type: str = Field("electronic", description="vat_normal/vat_special/electronic")
    order_id: str
    buyer_name: str
    buyer_tax_id: Optional[str] = None
    seller_name: str = "智影纳米机器人科技有限公司"
    seller_tax_id: str = "91110000XXXXXXXX5X"
    items: List[InvoiceItem]
    amount: float = Field(..., gt=0)
    tax_rate: float = 0.13


@router.get("/types")
def list_types():
    return {"types": [{"key": k, "name": v} for k, v in TEMPLATE_TYPES.items()]}


@router.post("")
def create_invoice(req: InvoiceCreate):
    try:
        inv = generate_invoice(
            invoice_type=req.invoice_type,
            order_id=req.order_id,
            buyer_name=req.buyer_name,
            buyer_tax_id=req.buyer_tax_id,
            seller_name=req.seller_name,
            seller_tax_id=req.seller_tax_id,
            items=[i.model_dump() for i in req.items],
            amount=req.amount,
            tax_rate=req.tax_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        save_invoice_pdf(inv)
        save_invoice_ofd(inv)
    except Exception:
        pass
    return inv.to_dict()


@router.get("")
def list_all(
    invoice_type: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
):
    items = list_invoices(invoice_type=invoice_type, order_id=order_id)
    return {"items": [i.to_dict() for i in items], "total": len(items)}


@router.get("/{invoice_no}")
def get_one(invoice_no: str):
    inv = get_invoice(invoice_no)
    if not inv:
        raise HTTPException(status_code=404, detail="invoice not found")
    return inv.to_dict()


@router.get("/{invoice_no}/pdf")
def download_pdf(invoice_no: str):
    inv = get_invoice(invoice_no)
    if not inv:
        raise HTTPException(status_code=404, detail="invoice not found")
    path = save_invoice_pdf(inv)
    with open(path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{invoice_no}.pdf"'})


@router.get("/{invoice_no}/ofd")
def download_ofd(invoice_no: str):
    inv = get_invoice(invoice_no)
    if not inv:
        raise HTTPException(status_code=404, detail="invoice not found")
    path = save_invoice_ofd(inv)
    with open(path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="application/ofd", headers={"Content-Disposition": f'attachment; filename="{invoice_no}.ofd"'})


@router.get("/{invoice_no}/verify")
def verify(invoice_no: str):
    return verify_invoice(invoice_no)


@router.post("/_hook/on_order_paid")
def hook_on_order_paid(
    order_id: str,
    buyer_name: str,
    amount: float,
    buyer_tax_id: Optional[str] = None,
):
    inv = on_order_paid(order_id, buyer_name, buyer_tax_id, amount)
    return inv.to_dict()


@router.get("/_meta/calc_tax")
def api_calc_tax(amount: float, rate: float = 0.13, inclusive: bool = True):
    return calc_tax(amount, rate, inclusive)


# ============================================================================
# P1-3: 国税平台对接 API
# ============================================================================
class ApplyInvoiceNumbersRequest(BaseModel):
    invoice_type: str = Field("electronic", pattern=r"^(vat_normal|vat_special|electronic)$")
    qty: int = Field(..., ge=1, le=1000)
    operator: Optional[str] = Field(None, max_length=64)
    simulate: bool = True


class ReportInvoiceRequest(BaseModel):
    invoice_no: str = Field(..., min_length=1, max_length=64)
    application_id: str = Field(..., min_length=1, max_length=64)
    invoice_type: str = Field("electronic", pattern=r"^(vat_normal|vat_special|electronic)$")


class VerifyInvoiceRequest(BaseModel):
    invoice_no: str = Field(..., min_length=1, max_length=64)
    verify_code: str = Field(..., min_length=4, max_length=16)


@tax_bureau_router.post("/apply")
def tb_apply(req: ApplyInvoiceNumbersRequest):
    try:
        rec = apply_invoice_numbers(
            invoice_type=req.invoice_type,
            qty=req.qty,
            operator=req.operator,
            simulate=req.simulate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rec.to_dict()


@tax_bureau_router.get("/apply")
def tb_list_applications(status: Optional[str] = Query(None)):
    if status and status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status!r}")
    items = list_applications(status=status)
    return {
        "count": len(items),
        "items": [a.to_dict() for a in items],
    }


@tax_bureau_router.get("/apply/{application_id}")
def tb_get_application(application_id: str):
    a = get_application(application_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"application {application_id!r} not found")
    return a.to_dict()


@tax_bureau_router.post("/upload")
def tb_upload(req: ReportInvoiceRequest):
    try:
        rec = report_to_tax_bureau(
            invoice_no=req.invoice_no,
            application_id=req.application_id,
            invoice_type=req.invoice_type,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rec.to_dict()


@tax_bureau_router.get("/upload")
def tb_list_uploads(invoice_no: Optional[str] = Query(None, max_length=64)):
    items = list_uploads(invoice_no=invoice_no)
    return {"count": len(items), "items": [u.to_dict() for u in items]}


@tax_bureau_router.get("/upload/{upload_id}")
def tb_get_upload(upload_id: str):
    u = get_upload(upload_id)
    if not u:
        raise HTTPException(status_code=404, detail=f"upload {upload_id!r} not found")
    return u.to_dict()


@tax_bureau_router.post("/verify")
def tb_verify(req: VerifyInvoiceRequest):
    res = verify_via_tax_bureau(req.invoice_no, req.verify_code)
    return res.to_dict()


@tax_bureau_router.get("/monthly-report")
def tb_monthly_report(year: int = Query(..., ge=2000, le=2100), month: int = Query(..., ge=1, le=12)):
    try:
        return monthly_report(year, month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@tax_bureau_router.get("/_meta")
def tb_meta():
    return {
        "application_statuses": APPLICATION_STATUSES,
        "upload_statuses": UPLOAD_STATUSES,
        "invoice_types": INVOICE_TYPES_SUPPORTED,
        "monthly_deadline_day": 15,
    }


# ============================================================================
# P1-7: 财务月度报表 API
# ============================================================================
@finance_router.get("/monthly")
def fin_monthly(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    try:
        rpt = generate_monthly_report(year, month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rpt.to_dict()


@finance_router.get("/monthly/csv")
def fin_monthly_csv(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    try:
        rpt = generate_monthly_report(year, month)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    csv_text = export_report_csv(rpt)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="finance-{year}-{month:02d}.csv"'},
    )


@finance_router.get("/quarterly")
def fin_quarterly(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
):
    try:
        return generate_quarterly_report(year, quarter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@finance_router.get("/revenue-by-method")
def fin_revenue_by_method(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    return {
        "year": year, "month": month,
        "by_method_cents": get_revenue_by_payment_method(year, month),
    }


@finance_router.get("/top-customers")
def fin_top_customers(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    n: int = Query(10, ge=1, le=100),
):
    return {
        "year": year, "month": month,
        "top": get_top_customers_by_revenue(year, month, n=n),
    }
