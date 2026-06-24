"""Business API router (R10.5-Worker-2) — mount at /api/v1/business

4 sub-routers:
- /billing      usage metering + invoice generation + usage query
- /export       JSON / CSV export (data export)
- /audit        tamper-evident audit log (append + verify + query)
- /tenant       multi-tenant CRUD + quota management

设计:
- 所有租户操作走 /tenant/* 端点, 内部强制 tenant_id 校验
- 所有可写操作落 audit log (actor + action + target + payload)
- 配额检查走 TenantRegistry.check_quota
- 测试时所有 store 用内存实现, 不连文件

要求: 4 个 sub-router 都用同一个 in-memory backend (单进程, 单测稳定)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from business.billing import (
    InvoiceEngine, InMemoryUsageStore, JsonlUsageStore, TieredPricing,
    UsageMeter, utc_now_period,
)
from business.data_exporter import (
    CSVExporter, ExportFormat, JSONExporter, export_data,
)
from business.audit_log import (
    AuditEntry, AuditLog, GENESIS_HASH, InMemoryAuditStore, JsonlAuditStore,
)
from business.tenant import (
    Quota, QuotaDecision, Tenant, TenantRegistry, assert_tenant_isolation,
)


# ============================================================================
# 单进程共享 backend — 单测用 InMemory, 生产可换 JSONL
# ============================================================================

# 默认: in-memory (测试安全), 生产可通过环境变量切换
import os as _os

def _make_usage_store():
    p = _os.environ.get("IMDF_BUSINESS_USAGE_PATH")
    if p:
        return JsonlUsageStore(p)
    return InMemoryUsageStore()

def _make_audit_store():
    p = _os.environ.get("IMDF_BUSINESS_AUDIT_PATH")
    if p:
        return JsonlAuditStore(p)
    return InMemoryAuditStore()


# 模块级 backend — 同一进程所有路由共享
_STATE: Dict[str, Any] = {
    "usage_store": _make_usage_store(),
    "audit_store": _make_audit_store(),
    "registry": TenantRegistry(
        storage_path=_os.environ.get("IMDF_BUSINESS_TENANT_PATH") or None,
    ),
    "pricing": TieredPricing.default(),
    "tax_rate": Decimal(str(_os.environ.get("IMDF_BUSINESS_TAX_RATE", "0"))),
}

_meter = UsageMeter(_STATE["usage_store"])
_audit = AuditLog(_STATE["audit_store"])
_invoice_eng = InvoiceEngine(_STATE["pricing"], tax_rate=_STATE["tax_rate"])
_registry: TenantRegistry = _STATE["registry"]


# ============================================================================
# Pydantic schemas
# ============================================================================

class UsageRecordRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    metric: str = Field(..., min_length=1, max_length=64)
    qty: float = Field(..., ge=0)
    unit: str = Field("count", min_length=1, max_length=32)
    ts: Optional[float] = Field(None, description="unix timestamp; default now")
    metadata: Dict[str, str] = Field(default_factory=dict)


class InvoiceRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    tier: str = Field("free", min_length=1, max_length=32)


class TenantCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64,
                            pattern=r"^[a-zA-Z0-9_\-]{1,64}$")
    name: str = Field(..., min_length=1, max_length=128)
    tier: str = Field("free", min_length=1, max_length=32)
    metadata: Dict[str, str] = Field(default_factory=dict)


class TenantQuotasRequest(BaseModel):
    quotas: Dict[str, Dict[str, Any]] = Field(..., description="metric -> {hard, soft, audit, unit}")


class TenantUpdateQuotaItem(BaseModel):
    metric: str = Field(..., min_length=1, max_length=64)
    hard: Optional[int] = Field(None, ge=0)
    soft: Optional[int] = Field(None, ge=0)
    audit: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=32)


class TenantQuotaCheckRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    metric: str = Field(..., min_length=1, max_length=64)
    current: int = Field(..., ge=0)


class AuditAppendRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., min_length=1, max_length=128)
    target: str = Field(..., min_length=1, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    fmt: str = Field("json", pattern=r"^(json|csv)$")
    records: List[Dict[str, Any]] = Field(default_factory=list)
    columns: Optional[List[str]] = Field(None)
    meta: Optional[Dict[str, Any]] = Field(None)


# ============================================================================
# 顶层 router
# ============================================================================

router = APIRouter(prefix="/api/v1/business", tags=["business"])


# ── Billing ──────────────────────────────────────────────────────────────
billing_router = APIRouter(prefix="/billing", tags=["billing"])


@billing_router.post("/usage")
async def record_usage(req: UsageRecordRequest):
    """记录一条用量."""
    # 1) 校验 tenant 存在
    t = _registry.get(req.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"tenant {req.tenant_id!r} not found")
    if not t.enabled:
        raise HTTPException(status_code=403, detail=f"tenant {req.tenant_id!r} is disabled")
    # 2) 记录
    evt = _meter.record(
        tenant_id=req.tenant_id, metric=req.metric, qty=req.qty,
        unit=req.unit, ts=req.ts, metadata=req.metadata,
    )
    # 3) 配额检查 — 累计当月用量
    period = utc_now_period()
    all_events = _meter.events_for(req.tenant_id, period)
    cumulative = sum(int(e.qty) for e in all_events if e.metric == req.metric)
    qd = _registry.check_quota(req.tenant_id, req.metric, cumulative)
    # 4) audit
    _audit.append(
        actor=req.tenant_id,
        action="billing.usage.record",
        target=evt.event_id,
        payload={"metric": req.metric, "qty": str(evt.qty),
                 "quota_level": qd.level, "allowed": qd.allowed},
    )
    return {
        "event_id": evt.event_id,
        "ts": evt.ts,
        "qty": _decimal_str(evt.qty),
        "unit": evt.unit,
        "quota": {
            "level": qd.level,
            "allowed": qd.allowed,
            "reason": qd.reason,
            "current": qd.current,
            "limit": qd.limit,
        },
    }


@billing_router.get("/usage/{tenant_id}")
async def query_usage(tenant_id: str, period: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    """查询某租户某月用量事件."""
    t = _registry.get(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id!r} not found")
    period = period or utc_now_period()
    events = _meter.events_for(tenant_id, period)
    return {
        "tenant_id": tenant_id,
        "period": period,
        "count": len(events),
        "events": [
            {
                "event_id": e.event_id,
                "metric": e.metric,
                "qty": _decimal_str(e.qty),
                "unit": e.unit,
                "ts": e.ts,
                "metadata": dict(e.metadata),
            }
            for e in events
        ],
    }


@billing_router.post("/invoice")
async def build_invoice(req: InvoiceRequest):
    """生成月度发票."""
    t = _registry.get(req.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"tenant {req.tenant_id!r} not found")
    events = _meter.events_for(req.tenant_id, req.period)
    invoice = _invoice_eng.build(
        tenant_id=req.tenant_id, period=req.period,
        tier=req.tier, events=events,
    )
    _audit.append(
        actor=req.tenant_id,
        action="billing.invoice.create",
        target=invoice.invoice_id,
        payload={"period": req.period, "tier": req.tier,
                 "total_cents": invoice.total_cents},
    )
    return invoice.to_dict()


# ── Export ───────────────────────────────────────────────────────────────
export_router = APIRouter(prefix="/export", tags=["export"])


@export_router.post("/data")
async def export_data_endpoint(req: ExportRequest):
    """JSON / CSV 标准化导出."""
    fmt = ExportFormat(req.fmt)
    blob = export_data(req.records, fmt=fmt, meta=req.meta, columns=req.columns)
    _audit.append(
        actor="system",
        action="export.data",
        target=f"{fmt.value}:{len(req.records)}",
        payload={"fmt": fmt.value, "count": len(req.records)},
    )
    # 返回 hex 摘要 + base64 字节 + 预览
    import base64
    import hashlib
    return {
        "fmt": fmt.value,
        "count": len(req.records),
        "size_bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "b64": base64.b64encode(blob).decode("ascii"),
        "preview": blob[:512].decode("utf-8", errors="replace"),
    }


@export_router.get("/formats")
async def list_export_formats():
    return {"formats": [f.value for f in ExportFormat], "schema_version": "1.0.0"}


# ── Audit ────────────────────────────────────────────────────────────────
audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.post("/append")
async def audit_append(req: AuditAppendRequest):
    """追加审计事件."""
    e = _audit.append(
        actor=req.actor, action=req.action,
        target=req.target, payload=req.payload,
    )
    return e.to_dict()


@audit_router.get("/verify")
async def audit_verify():
    """校验 hash chain."""
    ok, bad_seq = _audit.verify_chain()
    return {"ok": ok, "first_bad_seq": bad_seq}


@audit_router.get("/entries")
async def audit_query(
    actor: Optional[str] = Query(None, max_length=128),
    action: Optional[str] = Query(None, max_length=128),
    target: Optional[str] = Query(None, max_length=128),
    limit: int = Query(100, ge=1, le=1000),
):
    """查询审计日志 (filter + limit)."""
    entries = _audit.query(actor=actor, action=action, target=target, limit=limit)
    return {"count": len(entries), "entries": [e.to_dict() for e in entries]}


# ── Tenant ───────────────────────────────────────────────────────────────
tenant_router = APIRouter(prefix="/tenant", tags=["tenant"])


@tenant_router.post("")
async def tenant_create(req: TenantCreate):
    """创建租户."""
    try:
        t = _registry.create(
            tenant_id=req.tenant_id, name=req.name,
            tier=req.tier, metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit.append(
        actor=req.tenant_id, action="tenant.create",
        target=req.tenant_id,
        payload={"name": req.name, "tier": req.tier},
    )
    return t.to_dict()


@tenant_router.get("")
async def tenant_list():
    """列出租户."""
    tenants = _registry.list()
    return {"count": len(tenants), "tenants": [t.to_dict() for t in tenants]}


@tenant_router.get("/{tenant_id}")
async def tenant_get(tenant_id: str):
    """获取单个租户."""
    t = _registry.get(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id!r} not found")
    return t.to_dict()


@tenant_router.delete("/{tenant_id}")
async def tenant_delete(tenant_id: str):
    """删除租户."""
    ok = _registry.delete(tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id!r} not found")
    _audit.append(actor=tenant_id, action="tenant.delete", target=tenant_id, payload={})
    return {"deleted": tenant_id}


@tenant_router.post("/{tenant_id}/disable")
async def tenant_disable(tenant_id: str):
    """禁用租户."""
    try:
        _registry.disable(tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _audit.append(actor=tenant_id, action="tenant.disable", target=tenant_id, payload={})
    return {"tenant_id": tenant_id, "enabled": False}


@tenant_router.post("/{tenant_id}/enable")
async def tenant_enable(tenant_id: str):
    """启用租户."""
    try:
        _registry.enable(tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _audit.append(actor=tenant_id, action="tenant.enable", target=tenant_id, payload={})
    return {"tenant_id": tenant_id, "enabled": True}


@tenant_router.put("/{tenant_id}/quotas")
async def tenant_set_quotas(tenant_id: str, req: TenantQuotasRequest):
    """批量设置配额."""
    t = _registry.get(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id!r} not found")
    for metric, q in req.quotas.items():
        if not metric or len(metric) > 64:
            raise HTTPException(status_code=400, detail=f"invalid metric: {metric!r}")
        try:
            _registry.update_quota(
                tenant_id, metric,
                hard=q.get("hard"),
                soft=q.get("soft"),
                audit=q.get("audit"),
                unit=q.get("unit"),
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
    _audit.append(actor=tenant_id, action="tenant.quotas.set",
                  target=tenant_id, payload={"metrics": list(req.quotas.keys())})
    return _registry.get(tenant_id).to_dict()


@tenant_router.post("/{tenant_id}/quota/check")
async def tenant_quota_check(tenant_id: str, req: TenantQuotaCheckRequest):
    """检查配额."""
    try:
        assert_tenant_isolation(actor_tenant(tenant_id, req.tenant_id), req.tenant_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    qd = _registry.check_quota(req.tenant_id, req.metric, req.current)
    return {
        "allowed": qd.allowed, "reason": qd.reason, "level": qd.level,
        "current": qd.current, "limit": qd.limit,
    }


# Helper for isolation — 防 tenant_id 在 path vs body 不一致
def actor_tenant(path_tenant: str, body_tenant: str) -> str:
    return path_tenant if path_tenant else body_tenant


def _decimal_str(d: Decimal) -> str:
    """规范化 Decimal 字符串: 去掉无效尾零 (避免 '100.0' vs '100' 漂移)."""
    try:
        # normalize() 移除 trailing zeros
        return format(d.normalize(), "f")
    except Exception:
        return str(d)


# ── Mount 4 sub-routers ──────────────────────────────────────────────────
router.include_router(billing_router)
router.include_router(export_router)
router.include_router(audit_router)
router.include_router(tenant_router)


__all__ = ["router"]