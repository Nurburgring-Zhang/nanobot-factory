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
    sign_contract_real,
    verify_contract_signature,
    generate_admin_cert_pair,
)
from .expiration import (
    check_expiring, send_expiration_notices,
    expire_overdue, renew_contract, get_expiration_stats,
    EXPIRATION_DEFAULT_WINDOW_DAYS,
)
from .signing import (
    ensure_dev_ca,
    issue_leaf_for_subject,
    SignMode,
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
# F-6.7: 第三方电子签名 (PKI + 真实 SM2 / ECDSA / RSA + 时间戳)
# ============================================================================
class SignRealRequest(BaseModel):
    signer: str = Field(..., min_length=1, max_length=200,
                        description="签名人 / 公司名 (用于查 / 颁发叶子证书)")


class GenerateCertRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200,
                        description="Subject CN (公司 / 个人 / 服务)")
    email: Optional[str] = Field(None, max_length=120,
                        description="可选 Email, 写入 SAN")
    validity_days: int = Field(1095, ge=1, le=3650,
                        description="证书有效期 (默认 3 年 = 1095 天)")


@router.post("/{contract_id}/sign-pki", summary="F-6.7 PKI 签名 (真实证书链 + 时间戳)")
def sign_pki(contract_id: str, req: SignRealRequest):
    """对合同进行真实 PKI 签名 — 替代旧的 /sign 占位 SM2.

    流程: 颁发叶子证书 → 选 alg (env SIGN_MODE) → 签 doc_bytes → 时间戳.
    """
    try:
        result = sign_contract_real(contract_id, req.signer)
    except KeyError:
        raise HTTPException(status_code=404, detail="contract not found")
    # 同步重新保存 PDF 含签名信息
    c = get_contract(contract_id)
    if c:
        save_contract_pdf(c)
    return result


@router.post("/{contract_id}/verify-pki", summary="F-6.7 PKI 验签")
def verify_pki(contract_id: str):
    """验证合同签名 — 含证书链 + 时间戳 + 篡改检测."""
    try:
        result = verify_contract_signature(contract_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="contract not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/certs/generate", summary="F-6.7 管理员: 颁发叶子证书")
def admin_generate_cert(req: GenerateCertRequest):
    """管理员 API: 给指定 subject 颁发叶子证书 (默认 3 年有效期)."""
    try:
        return generate_admin_cert_pair(
            subject=req.subject,
            validity_days=req.validity_days,
            email=req.email,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cert_generation_failed: {e}")


@router.get("/certs/ca", summary="F-6.7 读取当前 CA 信息 (供客户端离线验签)")
def get_ca_info():
    """返回当前 CA 证书 + 指纹 (供外部系统嵌入验签逻辑)."""
    ca = ensure_dev_ca()
    return {
        "subject_cn": ca.subject_cn,
        "issuer_cn": ca.issuer_cn,
        "serial": ca.serial,
        "not_before": ca.not_before,
        "not_after": ca.not_after,
        "fingerprint": ca.fingerprint,
        "public_key_alg": ca.public_key_alg,
        "cert_pem": ca.cert_pem.decode("ascii"),
        "sign_mode": SignMode.from_env().value,
    }


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
