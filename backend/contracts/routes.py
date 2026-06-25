"""
P4-10-W2: 合同 HTTP API
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import (
    TEMPLATES,
    generate_contract,
    get_contract,
    list_contracts,
    sign_contract,
    save_contract_pdf,
    on_order_paid,
)
from .expiration import (
    check_expiring, send_expiration_notices,
    expire_overdue, renew_contract, get_expiration_stats,
    EXPIRATION_DEFAULT_WINDOW_DAYS,
)

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])
expiration_router = APIRouter(prefix="/api/v1/contracts/expiration", tags=["contracts-expiration"])


class ContractCreate(BaseModel):
    template: str = Field(..., description="服务协议/service_agreement | 数据处理协议/data_processing_agreement | SLA 协议/sla_agreement")
    company_name: str
    contact_email: str
    plan_name: str
    amount: float = Field(..., ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    extra_vars: Optional[dict] = None


class SignRequest(BaseModel):
    signer: str = Field(..., min_length=1, max_length=120, description="签名人 (公司名或个人)")


@router.get("/templates")
def list_templates():
    return {"templates": [{"key": k, "title": v["title"]} for k, v in TEMPLATES.items()]}


@router.post("")
def create_contract(req: ContractCreate):
    try:
        c = generate_contract(
            template=req.template,
            company_name=req.company_name,
            contact_email=req.contact_email,
            plan_name=req.plan_name,
            amount=req.amount,
            start_date=req.start_date,
            end_date=req.end_date,
            extra_vars=req.extra_vars,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 同步保存 PDF
    try:
        save_contract_pdf(c)
    except Exception:
        pass
    return c.to_dict()


@router.get("")
def list_all(company: Optional[str] = Query(None), status: Optional[str] = Query(None)):
    items = list_contracts(company=company, status=status)
    return {"items": [c.to_dict() for c in items], "total": len(items)}


@router.get("/{contract_id}")
def get_one(contract_id: str):
    c = get_contract(contract_id)
    if not c:
        raise HTTPException(status_code=404, detail="contract not found")
    return c.to_dict()


@router.get("/{contract_id}/pdf")
def download_pdf(contract_id: str):
    c = get_contract(contract_id)
    if not c:
        raise HTTPException(status_code=404, detail="contract not found")
    path = save_contract_pdf(c)
    return FileResponse(str(path), media_type="application/pdf", filename=f"{contract_id}.pdf")


@router.post("/{contract_id}/sign")
def sign(contract_id: str, req: SignRequest):
    try:
        c = sign_contract(contract_id, req.signer)
    except KeyError:
        raise HTTPException(status_code=404, detail="contract not found")
    # 签名后重新保存 PDF
    save_contract_pdf(c)
    return c.to_dict()


@router.post("/_hook/on_order_paid")
def hook_on_order_paid(order_id: str, plan_name: str, amount: float, company: str, email: str):
    """W1 Order paid 钩子."""
    c = on_order_paid(order_id, plan_name, amount, company, email)
    return c.to_dict()


# ============================================================================
# P1-4: 合同到期提醒 API
# ============================================================================
class RenewContractRequest(BaseModel):
    new_end_date: str = Field(..., min_length=8, max_length=32,
                              description="新合同结束日期 YYYY-MM-DD")


@expiration_router.get("/check")
def exp_check(window_days: int = Query(EXPIRATION_DEFAULT_WINDOW_DAYS, ge=1, le=180)):
    """扫描到期合同 (≤ window_days 天)."""
    report = check_expiring(window_days=window_days)
    return report.to_dict()


@expiration_router.post("/send")
def exp_send(window_days: int = Query(EXPIRATION_DEFAULT_WINDOW_DAYS, ge=1, le=180)):
    """扫描 + 实际发送提醒 (webhook/email/log)."""
    report = check_expiring(window_days=window_days)
    counters = send_expiration_notices(report)
    return {"report": report.to_dict(), "counters": counters}


@expiration_router.post("/expire-overdue")
def exp_expire_overdue():
    """强制过期已过截止日但状态仍为 active/signed 的合同."""
    n = expire_overdue()
    return {"expired_count": n}


@expiration_router.post("/{contract_id}/renew")
def exp_renew(contract_id: str, req: RenewContractRequest):
    try:
        new = renew_contract(contract_id, req.new_end_date)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return new.to_dict()


@expiration_router.get("/stats")
def exp_stats():
    return get_expiration_stats()
