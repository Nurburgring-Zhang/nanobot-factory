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

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


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
