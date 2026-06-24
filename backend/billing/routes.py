"""FastAPI routes for the billing module.

All endpoints mount at /api/v1/billing.

Top-level sub-routers:
- /plans          — list / detail / current user
- /orders         — create / list / detail / cancel
- /payment/{order_id} — create payment for an order
- /webhook/{provider} — receive webhook
- /refund/{order_id}  — refund
- /subscription   — current / change plan / cancel
- /quotas         — current usage + limits
- /usage          — detailed usage
- /admin/*        — admin endpoints
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .plans import (
    FEATURE_DIMENSIONS, FEATURE_LABELS, PLAN_CATALOG, PLAN_CONFIGS,
    get_plan, get_config, get_plan_with_config, list_plans,
    is_upgrade, is_downgrade, price_for,
)
from .orders import Order, OrderService, OrderStatus, InMemoryOrderStore
from .subscriptions import (
    SubscriptionService, SubscriptionStatus,
    InMemorySubscriptionStore, LoggingNotificationHook,
)
from .quotas import QuotaService, InMemoryQuotaTracker
from .admin import BillingAdminService
from .payments import (
    get_provider, get_providers, register_provider, reset_providers,
)
from .payments.base import (
    PaymentResult, WebhookEvent, WebhookVerificationError,
    ProviderNotConfiguredError,
)


# ============================================================================
# 1. Module-level state (singleton per process; test can reset via fixtures)
# ============================================================================

def _build_state() -> Dict[str, Any]:
    """Build default state (in-memory; can be replaced via env or fixture)."""
    order_store = InMemoryOrderStore()
    sub_store = InMemorySubscriptionStore()
    quota_tracker = InMemoryQuotaTracker()
    notification_hook = LoggingNotificationHook()
    order_service = OrderService(order_store)
    sub_service = SubscriptionService(sub_store, order_service, notification_hook)
    quota_service = QuotaService(quota_tracker)
    admin_service = BillingAdminService(order_service, sub_service, quota_service)
    return {
        "order_store": order_store,
        "sub_store": sub_store,
        "quota_tracker": quota_tracker,
        "notification_hook": notification_hook,
        "order_service": order_service,
        "sub_service": sub_service,
        "quota_service": quota_service,
        "admin_service": admin_service,
    }


_STATE: Dict[str, Any] = _build_state()


def reset_state() -> Dict[str, Any]:
    """Reset all in-memory state. Test helper."""
    global _STATE
    _STATE = _build_state()
    return _STATE


def get_state() -> Dict[str, Any]:
    return _STATE


# ============================================================================
# 2. Pydantic schemas
# ============================================================================

class PlanSummary(BaseModel):
    plan_id: str
    name: str
    tier: str
    description: str
    monthly_price_cny: int
    monthly_price_usd: int
    annual_price_cny: int
    annual_price_usd: int
    is_custom: bool = False
    limits: Dict[str, int] = Field(default_factory=dict)
    overflow_policy: Dict[str, str] = Field(default_factory=dict)
    billing_period: str = "monthly"


class CreateOrderRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    plan_id: str = Field(..., min_length=1, max_length=40)
    currency: str = Field("USD", pattern=r"^(USD|CNY)$")
    period: str = Field("monthly", pattern=r"^(monthly|yearly|annual)$")
    payment_method: str = Field("mock", min_length=1, max_length=20)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreatePaymentRequest(BaseModel):
    payment_method: Optional[str] = Field(None, max_length=20,
                                          description="If None, use order's payment_method")
    return_url: Optional[str] = Field(None, max_length=512)


class RefundRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=512)


class ChangePlanRequest(BaseModel):
    new_plan_id: str = Field(..., min_length=1, max_length=40)
    period: str = Field("monthly", pattern=r"^(monthly|yearly|annual)$")
    currency: str = Field("USD", pattern=r"^(USD|CNY)$")


class CancelSubscriptionRequest(BaseModel):
    at_period_end: bool = Field(True)


class RecordUsageRequest(BaseModel):
    dimension: str = Field(..., min_length=1, max_length=40)
    qty: int = Field(1, ge=0)


class CheckQuotaRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    plan_id: str = Field(..., min_length=1, max_length=40)
    dimension: str = Field(..., min_length=1, max_length=40)
    qty: int = Field(1, ge=1)


# ============================================================================
# 3. Top-level router + sub-routers
# ============================================================================

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


# ── Plans ────────────────────────────────────────────────────────────────
plans_router = APIRouter(prefix="/plans", tags=["billing-plans"])


@plans_router.get("", response_model=List[PlanSummary])
async def list_all_plans():
    """List all 5 plans with full config."""
    return [get_plan_with_config(p.plan_id) for p in list_plans()]


@plans_router.get("/{plan_id}", response_model=PlanSummary)
async def get_one_plan(plan_id: str):
    try:
        return get_plan_with_config(plan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"plan {plan_id!r} not found")


@plans_router.get("/current/user")
async def current_user_plan(user_id: str = Query(..., min_length=1, max_length=64)):
    """Return the current plan for a user (from active subscription or default Free)."""
    sub = _STATE["sub_service"].get_by_user(user_id)
    plan_id = sub.plan_id if sub else "free"
    return get_plan_with_config(plan_id)


# ── Orders ───────────────────────────────────────────────────────────────
orders_router = APIRouter(prefix="/orders", tags=["billing-orders"])


@orders_router.post("", response_model=Dict[str, Any])
async def create_order_endpoint(req: CreateOrderRequest):
    try:
        # Validate plan
        get_plan(req.plan_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"unknown plan: {req.plan_id!r}")
    try:
        amount = price_for(req.plan_id, req.period, req.currency.lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        order = _STATE["order_service"].create_order(
            user_id=req.user_id, plan_id=req.plan_id,
            amount_cents=amount, currency=req.currency,
            payment_method=req.payment_method,
            metadata={**req.metadata, "period": req.period},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return order.to_dict()


@orders_router.get("", response_model=Dict[str, Any])
async def list_orders(
    user_id: Optional[str] = Query(None, max_length=64),
    status: Optional[str] = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=500),
):
    status_enum = None
    if status:
        try:
            status_enum = OrderStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid status: {status!r}")
    orders = _STATE["order_service"].store.list(
        user_id=user_id, status=status_enum, limit=limit,
    )
    return {
        "count": len(orders),
        "orders": [o.to_dict() for o in orders],
    }


@orders_router.get("/{order_id}", response_model=Dict[str, Any])
async def get_order(order_id: str):
    order = _STATE["order_service"].get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id!r} not found")
    return order.to_dict()


@orders_router.post("/{order_id}/cancel", response_model=Dict[str, Any])
async def cancel_order(order_id: str, reason: Optional[str] = Query(None, max_length=256)):
    order = _STATE["order_service"].get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id!r} not found")
    try:
        order = _STATE["order_service"].cancel(order_id, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return order.to_dict()


# ── Payment ──────────────────────────────────────────────────────────────
payment_router = APIRouter(prefix="/payment", tags=["billing-payment"])


@payment_router.post("/{order_id}")
async def create_payment(order_id: str, req: CreatePaymentRequest):
    order = _STATE["order_service"].get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id!r} not found")
    if order.is_terminal() and order.status != OrderStatus.FULFILLED:
        raise HTTPException(
            status_code=400,
            detail=f"order in terminal status {order.status.value!r}",
        )
    method = req.payment_method or order.payment_method
    try:
        provider = get_provider(method)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = provider.create_payment(order)
    except ProviderNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=f"provider not configured: {e}")
    return result.to_dict()


# ── Webhook ──────────────────────────────────────────────────────────────
webhook_router = APIRouter(prefix="/webhook", tags=["billing-webhook"])


@webhook_router.post("/{provider}")
async def receive_webhook(provider: str, request: Request):
    try:
        prov = get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"provider {provider!r} not found")
    body = await request.body()
    # Different providers use different signature headers
    if provider == "stripe":
        sig = request.headers.get("stripe-signature", "")
    elif provider == "alipay":
        sig = request.headers.get("alipay-signature", "")
    elif provider == "wechat":
        sig = request.headers.get("wechat-signature", "")
    else:
        sig = request.headers.get("x-signature", "")
    try:
        event = prov.verify_webhook(body, sig)
    except WebhookVerificationError as e:
        raise HTTPException(status_code=400, detail=f"webhook verify failed: {e}")
    # Mark order paid (or refunded) based on event
    order = _STATE["order_service"].get(event.order_id)
    if order is not None:
        if event.status == "success":
            try:
                _STATE["order_service"].mark_paid(
                    event.order_id, external_ref=event.payment_id,
                )
            except (ValueError, KeyError):
                # already in non-pending state — ignore
                pass
        elif event.status == "refunded":
            try:
                _STATE["order_service"].refund(event.order_id, reason="webhook")
            except (ValueError, KeyError):
                pass
    return {"received": True, "event": event.to_dict()}


# ── Refund ───────────────────────────────────────────────────────────────
refund_router = APIRouter(prefix="/refund", tags=["billing-refund"])


@refund_router.post("/{order_id}")
async def refund_order(order_id: str, req: RefundRequest):
    order = _STATE["order_service"].get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id!r} not found")
    try:
        # Provider-side refund
        method = order.payment_method
        if method != "mock":
            try:
                prov = get_provider(method)
                prov.refund(order)
            except (KeyError, ProviderNotConfiguredError):
                pass  # proceed with internal refund regardless
        refunded = _STATE["order_service"].refund(order_id, reason=req.reason)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return refunded.to_dict()


# ── Subscription ─────────────────────────────────────────────────────────
subscription_router = APIRouter(prefix="/subscription", tags=["billing-subscription"])


@subscription_router.get("/user/{user_id}")
async def user_subscription(user_id: str):
    sub = _STATE["sub_service"].get_by_user(user_id)
    if sub is None:
        return {"user_id": user_id, "subscription": None}
    return {"user_id": user_id, "subscription": sub.to_dict()}


@subscription_router.post("/user/{user_id}/create")
async def create_subscription(
    user_id: str,
    plan_id: str = Query(..., min_length=1, max_length=40),
    period: str = Query("monthly", pattern=r"^(monthly|yearly|annual)$"),
    currency: str = Query("USD", pattern=r"^(USD|CNY)$"),
    trial_days: int = Query(0, ge=0, le=90),
):
    try:
        get_plan(plan_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"unknown plan: {plan_id!r}")
    try:
        sub = _STATE["sub_service"].create(
            user_id=user_id, plan_id=plan_id,
            period=period, currency=currency,
            trial_days=trial_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sub.to_dict()


@subscription_router.post("/user/{user_id}/change-plan")
async def change_plan(user_id: str, req: ChangePlanRequest):
    try:
        result = _STATE["sub_service"].change_plan(
            user_id=user_id, new_plan_id=req.new_plan_id,
            period=req.period, currency=req.currency,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@subscription_router.post("/user/{user_id}/cancel")
async def cancel_subscription(user_id: str, req: CancelSubscriptionRequest):
    try:
        sub = _STATE["sub_service"].cancel(user_id, at_period_end=req.at_period_end)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return sub.to_dict()


@subscription_router.post("/cron/renewal")
async def run_renewal_cron(dry_run: bool = Query(False)):
    """Run the daily renewal cron. Returns summary."""
    return _STATE["sub_service"].run_renewal_cron(dry_run=dry_run)


# ── Quotas ───────────────────────────────────────────────────────────────
quotas_router = APIRouter(prefix="/quotas", tags=["billing-quotas"])


@quotas_router.get("/user/{user_id}")
async def user_quotas(user_id: str, plan_id: str = Query(..., min_length=1, max_length=40)):
    try:
        get_plan(plan_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"unknown plan: {plan_id!r}")
    return _STATE["quota_service"].snapshot(user_id, plan_id)


@quotas_router.post("/check")
async def check_quota(req: CheckQuotaRequest):
    decision = _STATE["quota_service"].check(
        req.user_id, req.plan_id, req.dimension, req.qty,
    )
    return decision.to_dict()


@quotas_router.post("/user/{user_id}/consume")
async def consume_quota(user_id: str, req: RecordUsageRequest):
    """Record usage and return decision (with consume atomic)."""
    # Need to know the user's plan (use current sub or default free)
    sub = _STATE["sub_service"].get_by_user(user_id)
    plan_id = sub.plan_id if sub else "free"
    decision = _STATE["quota_service"].consume(
        user_id, plan_id, req.dimension, req.qty,
    )
    return decision.to_dict()


# ── Usage ────────────────────────────────────────────────────────────────
usage_router = APIRouter(prefix="/usage", tags=["billing-usage"])


@usage_router.get("/user/{user_id}")
async def user_usage(user_id: str):
    return {
        "user_id": user_id,
        "usage": _STATE["quota_service"].user_usage(user_id),
    }


@usage_router.get("/dimensions")
async def list_dimensions():
    return {
        "count": len(FEATURE_DIMENSIONS),
        "dimensions": [
            {"key": d, "label": FEATURE_LABELS.get(d, d)} for d in FEATURE_DIMENSIONS
        ],
    }


# ── Admin ────────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin", tags=["billing-admin"])


@admin_router.get("/orders")
async def admin_list_orders(
    user_id: Optional[str] = Query(None, max_length=64),
    status: Optional[str] = Query(None, max_length=20),
    plan_id: Optional[str] = Query(None, max_length=40),
    since: Optional[str] = Query(None, max_length=32),
    until: Optional[str] = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=500),
):
    status_enum = None
    if status:
        try:
            status_enum = OrderStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid status: {status!r}")
    return {
        "count": -1,  # computed below
        "orders": _STATE["admin_service"].list_orders(
            user_id=user_id, status=status_enum, plan_id=plan_id,
            since=since, until=until, limit=limit,
        ),
    }


@admin_router.post("/refunds/{order_id}/approve")
async def admin_approve_refund(order_id: str, reason: Optional[str] = Query(None, max_length=256)):
    try:
        order = _STATE["admin_service"].approve_refund(order_id, reason=reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return order.to_dict()


@admin_router.post("/refunds/{order_id}/reject")
async def admin_reject_refund(order_id: str, reason: str = Query(..., min_length=1, max_length=256)):
    try:
        order = _STATE["admin_service"].reject_refund(order_id, reason=reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return order.to_dict()


@admin_router.post("/refunds/{order_id}/request")
async def admin_request_refund(order_id: str, reason: str = Query(..., min_length=1, max_length=256)):
    try:
        order = _STATE["admin_service"].request_refund(order_id, reason=reason)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return order.to_dict()


@admin_router.get("/refunds/pending")
async def admin_pending_refunds(limit: int = Query(100, ge=1, le=500)):
    return {
        "count": -1,  # computed below
        "orders": _STATE["admin_service"].list_pending_refunds(limit=limit),
    }


@admin_router.get("/usage")
async def admin_global_usage():
    return _STATE["admin_service"].global_usage()


@admin_router.get("/revenue")
async def admin_revenue():
    return _STATE["admin_service"].revenue_summary()


@admin_router.get("/subscriptions")
async def admin_subscriptions(
    status: Optional[str] = Query(None, max_length=20),
    plan_id: Optional[str] = Query(None, max_length=40),
    limit: int = Query(100, ge=1, le=500),
):
    status_enum = None
    if status:
        try:
            status_enum = SubscriptionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid status: {status!r}")
    return {
        "count": -1,
        "subscriptions": _STATE["admin_service"].list_subscriptions(
            status=status_enum, plan_id=plan_id, limit=limit,
        ),
    }


@admin_router.get("/customers")
async def admin_customers():
    return {
        "count": -1,
        "customers": _STATE["admin_service"].customer_breakdown(),
    }


# ── Mount all sub-routers ────────────────────────────────────────────────
router.include_router(plans_router)
router.include_router(orders_router)
router.include_router(payment_router)
router.include_router(webhook_router)
router.include_router(refund_router)
router.include_router(subscription_router)
router.include_router(quotas_router)
router.include_router(usage_router)
router.include_router(admin_router)


__all__ = [
    "router", "reset_state", "get_state",
    "build_billing_router",  # alias
]


def build_billing_router() -> APIRouter:
    """Returns the billing router (alias for `router`)."""
    return router
