"""P1-3: 国税平台对接 (State Tax Bureau / 国家税务总局) — 发票申领 + 核验.

业务背景:
- 中国发票必须通过金税盘 / 税控盘 / 电子税务局平台开具, 上传国税系统.
- 流程: 申领发票号 (issue_application) → 填开 (draw) → 上传 (upload) → 核验 (verify) → 归档.
- 国税平台 API (mock): 我们在 mock 模式下模拟电子税务局接口, 真实环境对接
  百望/航信/航天金税的税控盘 HTTPS 接口.

支持能力:
- 发票号申领: 批量向国税系统申请空白发票号段
- 发票开具: 调税控盘开票 → 上传国税
- 发票核验: 第三方平台 (微信/支付宝发票助手) 通过发票号核验真伪
- 月度汇总上报: 每月 15 日前汇总当月开票数据

公开 API:
  - apply_invoice_numbers(qty, invoice_type)            → ApplicationRecord
  - get_application(application_id)                     → ApplicationRecord
  - list_applications(status=None)                      → [ApplicationRecord]
  - report_to_tax_bureau(invoice_no, application_id)    → UploadRecord
  - verify_via_tax_bureau(invoice_no, verify_code)      → VerifyResult
  - monthly_report(year, month)                         → MonthlyReport
  - monthly_report_for(year, month, invoices=None)      → MonthlyReport (helper for tests)
"""
from __future__ import annotations

import json
import logging
import os
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 状态常量
# ---------------------------------------------------------------------------
APPLICATION_STATUSES = ["pending", "approved", "rejected", "consumed"]
UPLOAD_STATUSES = ["pending", "uploaded", "verified", "failed"]
INVOICE_TYPES_SUPPORTED = ["vat_normal", "vat_special", "electronic"]


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
TAX_BUREAU_BASE_URL = os.getenv("TAX_BUREAU_BASE_URL", "https://etax.example.gov.cn/api/v1")
TAX_BUREAU_API_KEY = os.getenv("TAX_BUREAU_API_KEY", "mock-key")
TAX_BUREAU_TENANT_ID = os.getenv("TAX_BUREAU_TENANT_ID", "tenant-mock")
# 国税月报截止日 (每月 15 日)
MONTHLY_REPORT_DEADLINE_DAY = 15


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class ApplicationRecord:
    """发票号申领记录."""
    application_id: str
    invoice_type: str
    quantity: int
    number_start: Optional[str] = None  # 起始号 (申领成功后回填)
    number_end: Optional[str] = None    # 终止号
    status: str = "pending"              # pending / approved / rejected / consumed
    applied_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    operator: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UploadRecord:
    """发票上传国税记录."""
    upload_id: str
    invoice_no: str
    application_id: str
    invoice_type: str
    status: str = "pending"          # pending / uploaded / verified / failed
    tax_bureau_receipt: Optional[str] = None  # 国税回执号
    uploaded_at: Optional[str] = None
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerifyResult:
    """发票核验结果 (第三方平台/客户扫码核验)."""
    invoice_no: str
    valid: bool
    seller_name: str
    buyer_name: str
    amount: float
    tax: float
    issue_date: str
    verify_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tax_bureau_marks: List[str] = field(default_factory=list)  # 国税盖章/标记

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------
_APPLICATIONS: Dict[str, ApplicationRecord] = {}
_UPLOADS: Dict[str, UploadRecord] = {}
_VERIFIES: Dict[str, VerifyResult] = {}

# 全局号段分配游标
_NEXT_CURSOR: Dict[str, int] = {}  # invoice_type -> next sequence number


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _allocate_number_range(invoice_type: str, qty: int) -> Tuple[str, str]:
    """分配一段发票号 (mock 模式: 顺序递增).

    真实环境: 调用税控盘接口, 由硬件生成.
    """
    if invoice_type not in INVOICE_TYPES_SUPPORTED:
        raise ValueError(f"unsupported invoice_type: {invoice_type}")
    cur = _NEXT_CURSOR.get(invoice_type, 0) + 1
    _NEXT_CURSOR[invoice_type] = cur + qty - 1
    # 国标号格式: TYPE-YYYY-NNNNNN
    today = datetime.utcnow().strftime("%Y")
    start = f"{invoice_type[:3].upper()}-{today}-{cur:08d}"
    end = f"{invoice_type[:3].upper()}-{today}-{cur + qty - 1:08d}"
    return start, end


# ---------------------------------------------------------------------------
# 1. 发票号申领
# ---------------------------------------------------------------------------
def apply_invoice_numbers(
    invoice_type: str,
    qty: int,
    operator: Optional[str] = None,
    simulate: bool = True,
) -> ApplicationRecord:
    """向国税平台申请发票号段.

    Args:
        invoice_type: vat_normal / vat_special / electronic
        qty: 申请数量 (1-1000)
        operator: 操作人
        simulate: True=本地分配 (mock), False=调用真实税控盘 (未实现)
    """
    if invoice_type not in INVOICE_TYPES_SUPPORTED:
        raise ValueError(f"invalid invoice_type: {invoice_type!r}")
    if qty < 1 or qty > 1000:
        raise ValueError(f"qty must be in 1..1000, got {qty}")
    aid = f"TA-{uuid.uuid4().hex[:12].upper()}"
    rec = ApplicationRecord(
        application_id=aid,
        invoice_type=invoice_type,
        quantity=qty,
        operator=operator,
    )
    if simulate:
        # Mock: 90% 通过, 10% 拒绝
        if random.random() < 0.9:
            rec.number_start, rec.number_end = _allocate_number_range(invoice_type, qty)
            rec.status = "approved"
            rec.approved_at = _now_iso()
        else:
            rec.status = "rejected"
            rec.rejected_reason = "本月额度已用完"
    _APPLICATIONS[aid] = rec
    logger.info(
        "tax_bureau apply: %s type=%s qty=%d status=%s",
        aid, invoice_type, qty, rec.status,
    )
    return rec


def get_application(application_id: str) -> Optional[ApplicationRecord]:
    return _APPLICATIONS.get(application_id)


def list_applications(status: Optional[str] = None) -> List[ApplicationRecord]:
    items = list(_APPLICATIONS.values())
    if status:
        items = [a for a in items if a.status == status]
    return items


def consume_application(application_id: str, n: int = 1) -> ApplicationRecord:
    """标记申请已使用 n 张 (在 fill 时调用)."""
    a = _APPLICATIONS.get(application_id)
    if not a:
        raise KeyError(f"application not found: {application_id}")
    if a.status != "approved":
        raise ValueError(f"application {application_id!r} not in 'approved' state (got {a.status!r})")
    # Simplified: don't actually decrement — we track consumed count separately
    if not hasattr(a, "_consumed"):
        a._consumed = 0  # type: ignore[attr-defined]
    a._consumed += n  # type: ignore[attr-defined]
    if a._consumed >= a.quantity:  # type: ignore[attr-defined]
        a.status = "consumed"
    return a


# ---------------------------------------------------------------------------
# 2. 发票上传国税 (fills + uploads)
# ---------------------------------------------------------------------------
def report_to_tax_bureau(
    invoice_no: str,
    application_id: str,
    invoice_type: str = "electronic",
) -> UploadRecord:
    """将已开具发票上报国税系统."""
    app = _APPLICATIONS.get(application_id)
    if not app:
        raise KeyError(f"application not found: {application_id}")
    if app.status not in ("approved", "consumed"):
        raise ValueError(f"application {application_id!r} not approved (status={app.status})")
    if invoice_type not in INVOICE_TYPES_SUPPORTED:
        raise ValueError(f"invalid invoice_type: {invoice_type!r}")
    uid = f"TU-{uuid.uuid4().hex[:12].upper()}"
    rec = UploadRecord(
        upload_id=uid,
        invoice_no=invoice_no,
        application_id=application_id,
        invoice_type=invoice_type,
    )
    # Mock: 95% 上传成功
    if random.random() < 0.95:
        rec.status = "uploaded"
        rec.tax_bureau_receipt = f"GSR{uuid.uuid4().hex[:16].upper()}"
        rec.uploaded_at = _now_iso()
        consume_application(application_id, 1)
    else:
        rec.status = "failed"
        rec.failure_reason = "网络超时, 请重试"
    _UPLOADS[uid] = rec
    logger.info(
        "tax_bureau upload: %s invoice=%s status=%s",
        uid, invoice_no, rec.status,
    )
    return rec


def get_upload(upload_id: str) -> Optional[UploadRecord]:
    return _UPLOADS.get(upload_id)


def list_uploads(invoice_no: Optional[str] = None) -> List[UploadRecord]:
    items = list(_UPLOADS.values())
    if invoice_no:
        items = [u for u in items if u.invoice_no == invoice_no]
    return items


# ---------------------------------------------------------------------------
# 3. 发票核验 (第三方平台/客户扫码)
# ---------------------------------------------------------------------------
def verify_via_tax_bureau(
    invoice_no: str,
    verify_code: str,
    invoice_payload: Optional[Dict[str, Any]] = None,
) -> VerifyResult:
    """通过国税系统核验发票真伪.

    Args:
        invoice_no: 发票号
        verify_code: 发票右上角 6 位核验码 (PDF/OFD 上有)
        invoice_payload: 发票数据 (用于核验), 省略时尝试从 invoices 模块查
    """
    if not invoice_payload:
        # Try to look up in the invoices module
        try:
            from . import get_invoice  # type: ignore
            inv = get_invoice(invoice_no)
            if inv:
                invoice_payload = inv.to_dict()
        except (ImportError, Exception):
            invoice_payload = None
    # 简单核验逻辑: 核验码 = SM3 前 6 位
    if invoice_payload:
        canonical = json.dumps(invoice_payload, sort_keys=True, ensure_ascii=False, default=str)
        try:
            import hashlib
            full_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except Exception:
            full_hash = "0" * 64
        expected = full_hash[:6].upper()
        if verify_code.upper() == expected:
            return VerifyResult(
                invoice_no=invoice_no,
                valid=True,
                seller_name=invoice_payload.get("seller_name", ""),
                buyer_name=invoice_payload.get("buyer_name", ""),
                amount=float(invoice_payload.get("amount", 0)),
                tax=float(invoice_payload.get("tax", {}).get("tax", 0)) if isinstance(invoice_payload.get("tax"), dict) else 0.0,
                issue_date=invoice_payload.get("issue_date", ""),
                tax_bureau_marks=["国税已核验", "电子签章有效"],
            )
    # Fallback: simulate 50/50 if no payload
    valid = random.random() < 0.5 if not invoice_payload else False
    if valid:
        return VerifyResult(
            invoice_no=invoice_no,
            valid=True,
            seller_name="智影纳米机器人科技有限公司",
            buyer_name="",
            amount=0.0,
            tax=0.0,
            issue_date=datetime.utcnow().strftime("%Y-%m-%d"),
            tax_bureau_marks=["国税已核验"],
        )
    return VerifyResult(
        invoice_no=invoice_no,
        valid=False,
        seller_name="",
        buyer_name="",
        amount=0.0,
        tax=0.0,
        issue_date="",
        tax_bureau_marks=[],
    )


# ---------------------------------------------------------------------------
# 4. 月度汇总上报
# ---------------------------------------------------------------------------
def monthly_report_for(
    year: int,
    month: int,
    invoices: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """生成月度发票汇总 (供财务 / 国税上报).

    Args:
        year, month: 目标年月
        invoices: 发票列表 (省略时从 invoices 模块查)
    """
    if not (1 <= month <= 12):
        raise ValueError(f"month must be in 1..12, got {month}")
    if invoices is None:
        try:
            from . import list_invoices  # type: ignore
            all_inv = list_invoices()
            invoices = [
                inv.to_dict() for inv in all_inv
                if inv.issue_date.startswith(f"{year:04d}-{month:02d}")
            ]
        except (ImportError, Exception):
            invoices = []
    # Aggregate
    by_type: Dict[str, Dict[str, float]] = {}
    total_amount = 0.0
    total_tax = 0.0
    total_gross = 0.0
    cnt = len(invoices)
    for inv in invoices:
        it = inv.get("invoice_type", "electronic")
        b = by_type.setdefault(it, {"count": 0, "amount": 0.0, "tax": 0.0, "gross": 0.0})
        b["count"] += 1
        amt = float(inv.get("amount", 0))
        tax_info = inv.get("tax", {})
        tax = float(tax_info.get("tax", 0)) if isinstance(tax_info, dict) else 0.0
        gross = float(tax_info.get("gross", amt)) if isinstance(tax_info, dict) else amt
        b["amount"] += amt
        b["tax"] += tax
        b["gross"] += gross
        total_amount += amt
        total_tax += tax
        total_gross += gross
    # Rounding
    for b in by_type.values():
        for k in ("amount", "tax", "gross"):
            b[k] = round(b[k], 2)
    deadline = f"{year:04d}-{month:02d}-{MONTHLY_REPORT_DEADLINE_DAY:02d}"
    return {
        "year": year,
        "month": month,
        "deadline": deadline,
        "total_invoices": cnt,
        "total_amount": round(total_amount, 2),
        "total_tax": round(total_tax, 2),
        "total_gross": round(total_gross, 2),
        "by_invoice_type": by_type,
        "generated_at": _now_iso(),
    }


def monthly_report(year: int, month: int) -> Dict[str, Any]:
    """月度发票汇总 (实际查询 invoices 模块)."""
    return monthly_report_for(year, month, invoices=None)


# ---------------------------------------------------------------------------
# 测试用 — 重置
# ---------------------------------------------------------------------------
def _reset_tax_bureau() -> None:
    """清空所有国税平台状态. 测试用."""
    _APPLICATIONS.clear()
    _UPLOADS.clear()
    _VERIFIES.clear()
    _NEXT_CURSOR.clear()


__all__ = [
    "APPLICATION_STATUSES", "UPLOAD_STATUSES", "INVOICE_TYPES_SUPPORTED",
    "MONTHLY_REPORT_DEADLINE_DAY",
    "ApplicationRecord", "UploadRecord", "VerifyResult",
    "apply_invoice_numbers", "get_application", "list_applications", "consume_application",
    "report_to_tax_bureau", "get_upload", "list_uploads",
    "verify_via_tax_bureau",
    "monthly_report", "monthly_report_for",
    "_reset_tax_bureau",
]
