"""FastAPI router for CDP Advanced Billing (V5 Chapter 22 / §13.4).

Endpoints:
    POST /api/v1/billing/cdp/usage            — record usage
    POST /api/v1/billing/cdp/invoice          — calculate + (optionally) generate invoice
    GET  /api/v1/billing/cdp/invoices         — list invoices for a tenant
    GET  /api/v1/billing/cdp/invoice/{id}/pdf — download invoice as PDF / HTML

Notes:
    * The router does NOT spin up a database; a single CDPBillingService instance
      is module-level and shared across requests. In production, swap in a real
      SQL/Postgres-backed store (the `CdpBillingStore` protocol already supports
      this — see cdp_billing.py).
    * Pydantic v2 schemas live in cdp_billing_schemas.py.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import Response

from .cdp_billing import CDPBillingService
from .cdp_billing_schemas import Invoice, UsageRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing/cdp", tags=["CDP Billing"])

# Module-level singleton — in-memory store; recreate per-test via get_service().
_service = CDPBillingService()


def get_service() -> CDPBillingService:
    """Get or rebuild the module-level CDPBillingService."""
    return _service


def reset_service() -> None:
    """Reset to a fresh in-memory service (used by tests)."""
    global _service
    _service = CDPBillingService()


# ────────────────────────────────────────────────────────────────────────────
# Request bodies (lightweight — Pydantic models live elsewhere)
# ────────────────────────────────────────────────────────────────────────────


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ────────────────────────────────────────────────────────────────────────────
# POST /api/v1/billing/cdp/usage
# ────────────────────────────────────────────────────────────────────────────


@router.post("/usage", summary="Track tenant usage (CDP Billing)")
async def track_usage(
    payload: Dict[str, Any] = Body(
        ...,
        example={
            "tenant_id": "tenant-1",
            "metric": "api_calls",
            "value": 2500,
            "unit": "call",
        },
    ),
) -> Dict[str, Any]:
    """Record a metered usage event.

    Body:
        tenant_id: str
        metric:    str (must match a configured PricingRule, else still recorded)
        value:     float (>= 0)
        unit:      optional str
        metadata:  optional dict
    """
    svc = get_service()
    tenant_id = payload.get("tenant_id")
    metric = payload.get("metric")
    value = payload.get("value", 0)
    unit = payload.get("unit")
    metadata = payload.get("metadata")
    ts_raw = payload.get("timestamp")
    if not tenant_id or not isinstance(tenant_id, str):
        raise HTTPException(status_code=422, detail="tenant_id required (non-empty str)")
    if not metric or not isinstance(metric, str):
        raise HTTPException(status_code=422, detail="metric required (non-empty str)")
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="value must be numeric") from None
    if fvalue < 0:
        raise HTTPException(status_code=422, detail="value must be >= 0")
    ts_obj = None
    if ts_raw is not None:
        try:
            ts_obj = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else ts_raw
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"timestamp: {exc}") from None
    try:
        rec = _run(
            svc.track_usage(
                tenant_id=tenant_id,
                metric=metric,
                value=fvalue,
                unit=unit,
                timestamp=ts_obj,
                metadata=metadata,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return rec.model_dump(mode="json")


# ────────────────────────────────────────────────────────────────────────────
# POST /api/v1/billing/cdp/invoice
# ────────────────────────────────────────────────────────────────────────────


@router.post("/invoice", summary="Calculate invoice for a tenant over a period")
async def calculate_invoice(
    payload: Dict[str, Any] = Body(
        ...,
        example={
            "tenant_id": "tenant-1",
            "period_start": "2026-03-01",
            "period_end": "2026-04-01",
        },
    ),
) -> Dict[str, Any]:
    """Calculate + persist an invoice covering `[period_start, period_end)`.

    Body:
        tenant_id: str
        period_start: ISO date str
        period_end:   ISO date str (exclusive)
    """
    svc = get_service()
    tenant_id = payload.get("tenant_id")
    ps_raw = payload.get("period_start")
    pe_raw = payload.get("period_end")
    if not tenant_id or not isinstance(tenant_id, str):
        raise HTTPException(status_code=422, detail="tenant_id required")
    try:
        period_start = _parse_date(ps_raw)
        period_end = _parse_date(pe_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"date parse: {exc}") from None
    if period_end <= period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")
    try:
        invoice = _run(svc.calculate_invoice(tenant_id, period_start, period_end))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return invoice.model_dump(mode="json")


# ────────────────────────────────────────────────────────────────────────────
# GET /api/v1/billing/cdp/invoices
# ────────────────────────────────────────────────────────────────────────────


@router.get("/invoices", summary="List invoices for a tenant")
async def list_invoices(
    tenant_id: str = Query(..., min_length=1, description="Tenant identifier"),
    limit: int = Query(20, ge=1, le=200, description="Max number of invoices to return"),
) -> Dict[str, Any]:
    svc = get_service()
    rows: List[Invoice] = _run(svc.list_invoices(tenant_id, limit=limit))
    return {
        "tenant_id": tenant_id,
        "count": len(rows),
        "invoices": [inv.model_dump(mode="json") for inv in rows],
    }


# ────────────────────────────────────────────────────────────────────────────
# GET /api/v1/billing/cdp/invoice/{id}/pdf
# ────────────────────────────────────────────────────────────────────────────


@router.get("/invoice/{invoice_id}/pdf", summary="Download invoice as PDF (or HTML fallback)")
async def download_invoice_pdf(
    invoice_id: str,
    tenant_id: str = Query(..., min_length=1, description="Tenant identifier"),
) -> Response:
    svc = get_service()
    rows: List[Invoice] = _run(svc.list_invoices(tenant_id, limit=1000))
    invoice = next((inv for inv in rows if inv.id == invoice_id), None)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f"invoice not found: {invoice_id}")
    pdf_bytes = _run(svc.generate_invoice_pdf(invoice))
    # Decide content-type — if real PDF, use application/pdf; else text/html
    if pdf_bytes.startswith(b"%PDF-"):
        media_type = "application/pdf"
        filename = f"{invoice.id}.pdf"
    else:
        media_type = "text/html; charset=utf-8"
        filename = f"{invoice.id}.html"
    return Response(
        content=pdf_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _parse_date(raw: Any) -> _date:
    if isinstance(raw, _date) and not isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        raise ValueError(f"expected ISO date string, got {type(raw).__name__}")
    return datetime.fromisoformat(raw).date()


__all__ = [
    "router",
    "get_service",
    "reset_service",
]
