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
from .quotas import (
    QuotaService, InMemoryQuotaTracker,
    build_default_tracker, should_log_decisions,
)
from .admin import BillingAdminService
from .payments import (
    get_provider, get_providers, register_provider, reset_providers,
)
from .payments.base import (
    PaymentResult, WebhookEvent, WebhookVerificationError,
    ProviderNotConfiguredError,
)
from .payments.idempotency import (
    get_store as get_idem_store, hash_request, derive_key_from_order,
)
from .payments.webhook_dedup import (
    get_store as get_dedup_store, extract_event_id,
)
from .payments.dispute import (
    register_dispute, get_dispute, get_disputes_by_order,
    upload_evidence, resolve_dispute, list_open_disputes, dispute_stats,
    DISPUTE_REASONS, Dispute,
)
from .customers import (
    PM_TYPES, PM_TYPE_LABELS, Customer, PaymentMethod,
    register_customer, get_customer, get_customer_by_user, list_customers,
    attach_payment_method, detach_payment_method, list_payment_methods,
    get_payment_method, get_default_payment_method, set_default_payment_method,
    customer_stats,
)


# ============================================================================
# 1. Module-level state (singleton per process; test can reset via fixtures)
# ============================================================================

def _build_state() -> Dict[str, Any]:
    """Build default state (in-memory; can be replaced via env or fixture).

    P15-B: ``quota_tracker`` is now built via :func:`quotas.build_default_tracker`,
    which honors the ``QUOTA_TRACKER_BACKEND`` env var (``db`` is the production-safe
    default; ``memory`` for tests / ephemeral usage). When ``db`` is selected,
    ``ensure_quota_schema()`` is called once so the 4 quota tables exist before
    any traffic — startup is idempotent.

    To force a tracker choice without touching code::

        export QUOTA_TRACKER_BACKEND=memory    # use InMemoryQuotaTracker
        export QUOTA_TRACKER_BACKEND=db        # use DBQuotaTracker (default)
        export BILLING_DB_URL=sqlite:///path/to/billing.db   # optional
    """
    order_store = InMemoryOrderStore()
    sub_store = InMemorySubscriptionStore()
    # P15-B: honor QUOTA_TRACKER_BACKEND env. Default is "db" (production-safe).
    quota_tracker = build_default_tracker()
    # Make sure the 4 quota tables exist when we boot in db mode (idempotent).
    try:
        from .db_init import ensure_quota_schema
        ensure_quota_schema()
    except Exception as _exc:
        # Schema bootstrap failures shouldn't crash module import — the tracker
        # itself raises later if writes fail.
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "ensure_quota_schema at startup skipped: %s", _exc,
        )
    notification_hook = LoggingNotificationHook()
    order_service = OrderService(order_store)
    sub_service = SubscriptionService(sub_store, order_service, notification_hook)
    quota_service = QuotaService(quota_tracker)
    # P15-B: optional decision-logger wiring (opt-in via QUOTA_LOG_DECISIONS=1).
    if should_log_decisions() and hasattr(quota_tracker, "log_decision"):
        quota_service.attach_decision_logger(quota_tracker.log_decision)
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


def reset_state(*, reset_db: bool = True) -> Dict[str, Any]:
    """Reset all in-memory state. Test helper.

    Args:
        reset_db: if True (default), also wipe the persisted quota tables so
            that each test starts from a clean slate (mimics the original
            InMemoryQuotaTracker semantics where each process saw fresh
            counts). Pass ``False`` to keep DB state — useful when a test
            deliberately wants to read prior writes (e.g. cross-restart
            scenarios in ``test_quota_persistence.py``).
    """
    global _STATE
    if reset_db:
        try:
            from .db_init import reset_quota_schema
            reset_quota_schema()
        except Exception as _exc:
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "reset_state: quota schema reset skipped: %s", _exc,
            )
    _STATE = _build_state()
    return _STATE


def get_state() -> Dict[str, Any]:
    return _STATE


def set_quota_tracker_backend(backend: str, url: Optional[str] = None) -> None:
    """P15-B: runtime swap of the quota tracker backend.

    Replaces ``_STATE['quota_tracker']`` with a freshly-built tracker of the
    requested backend (``"memory"`` or ``"db"``) and re-attaches the decision
    logger if ``QUOTA_LOG_DECISIONS=1`` is set.

    Args:
        backend: ``"memory"`` or ``"db"`` (matches :data:`quotas.VALID_TRACKER_BACKENDS`).
        url: optional SQLAlchemy URL for the ``"db"`` backend.

    Raises:
        ValueError: If ``backend`` is unknown.
    """
    new_tracker = build_default_tracker(backend=backend, url=url)
    if should_log_decisions() and hasattr(new_tracker, "log_decision"):
        _STATE["quota_service"].attach_decision_logger(new_tracker.log_decision)
    else:
        _STATE["quota_service"].attach_decision_logger(None)
    _STATE["quota_service"].set_tracker(new_tracker)
    _STATE["quota_tracker"] = new_tracker
    # Re-wire admin service so global_usage() sees the fresh tracker.
    _STATE["admin_service"] = BillingAdminService(
        _STATE["order_service"], _STATE["sub_service"], _STATE["quota_service"],
    )


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
    # Optional: None/omitted -> full refund; numeric -> partial refund amount
    # in major units (e.g. 9.99 == 999 cents). Accepts int|float|str|Decimal.
    amount: Optional[Any] = Field(
        None,
        description="Partial refund amount in major units (e.g. 9.99). "
                    "Omit for full refund.",
    )


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
async def create_payment(order_id: str, req: CreatePaymentRequest,
                         request: Request = None):  # type: ignore[assignment]
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
    # ── Idempotency: honor ``Idempotency-Key`` header from client.
    # If absent, derive one from order_id + payment_method.
    idem_key = None
    if request is not None:
        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
    if not idem_key:
        idem_key = derive_key_from_order(order_id, method)
    request_hash = hash_request({
        "order_id": order_id,
        "payment_method": method,
        "amount_cents": order.amount_cents,
        "currency": order.currency,
        "return_url": req.return_url,
    })
    idem_store = get_idem_store()
    hit, reserved = idem_store.lookup_or_reserve(idem_key, request_hash)
    if hit is not None:
        # Replay — return the cached result verbatim
        return {
            **hit.parsed(),
            "_idempotent_replay": True,
            "_replay_count": hit.replay_count,
            "_idempotency_key": idem_key,
        }
    if not reserved:
        # In-progress placeholder — caller should retry
        raise HTTPException(
            status_code=409,
            detail="a request with this Idempotency-Key is already in progress",
        )
    try:
        result = provider.create_payment(order)
    except ProviderNotConfiguredError as e:
        idem_store.release(idem_key)
        raise HTTPException(status_code=503, detail=f"provider not configured: {e}")
    except Exception:
        # Don't cache failures — let the client retry.
        idem_store.release(idem_key)
        raise
    payload = result.to_dict()
    idem_store.commit(idem_key, request_hash, payload)
    return {
        **payload,
        "_idempotent_replay": False,
        "_idempotency_key": idem_key,
    }


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
    # ── Replay protection (event-id dedup) — run BEFORE signature verify
    # so a malicious actor can't burn the dedup slot for legit events.
    # (Event id is provider-supplied but it's just a Redis key; signature
    # verify still gates whether we act on the event.)
    event_id = extract_event_id(provider, body)
    dedup = get_dedup_store()
    if event_id:
        result = dedup.register(event_id, provider)
        if result.is_duplicate:
            # 200 OK so the provider stops retrying, but no business action.
            return {
                "received": True,
                "duplicate": True,
                "event_id": event_id,
                "provider": provider,
            }
    try:
        event = prov.verify_webhook(body, sig)
    except WebhookVerificationError as e:
        # Signature failed — release the dedup slot so the legit retry
        # can be processed.
        if event_id:
            dedup.release(event_id, provider)
        raise HTTPException(status_code=400, detail=f"webhook verify failed: {e}")
    # Mark order paid (or refunded) based on event
    order = _STATE["order_service"].get(event.order_id)
    business_applied = False
    dispute_registered: Optional[Dict[str, Any]] = None
    if order is not None:
        if event.status == "success":
            try:
                _STATE["order_service"].mark_paid(
                    event.order_id, external_ref=event.payment_id,
                )
                business_applied = True
            except (ValueError, KeyError):
                # already in non-pending state — ignore
                pass
        elif event.status == "refunded":
            try:
                _STATE["order_service"].refund(event.order_id, reason="webhook")
                business_applied = True
            except (ValueError, KeyError):
                pass
        elif event.status == "disputed":
            # P1-2: dispute.created / dispute.closed 业务处理
            dispute_event_type = event.event_type
            if dispute_event_type == "charge.dispute.created":
                try:
                    # 尝试从 raw 提取 reason
                    obj = (event.raw or {}).get("data", {}).get("object", {}) or {}
                    reason = obj.get("reason", "general")
                    if reason not in DISPUTE_REASONS:
                        reason = "general"
                    d = register_dispute(
                        order_id=event.order_id,
                        payment_id=event.payment_id,
                        amount_cents=event.amount_cents,
                        currency=event.currency,
                        reason=reason,
                    )
                    business_applied = True
                    dispute_registered = d.to_dict()
                except Exception as e:
                    logger.warning("dispute register failed: %s", e)
            elif dispute_event_type == "charge.dispute.closed":
                # 标记已有 dispute 为 closed
                try:
                    disputes = get_disputes_by_order(event.order_id)
                    # 找最新一笔未结的
                    for d in reversed(disputes):
                        if d.status in ("needs_response", "under_review"):
                            obj = (event.raw or {}).get("data", {}).get("object", {}) or {}
                            final_status = obj.get("status", "closed")
                            if final_status == "won":
                                resolve_dispute(d.dispute_id, "won", resolution_note="stripe webhook: won")
                            elif final_status == "lost":
                                resolve_dispute(d.dispute_id, "lost", resolution_note="stripe webhook: lost")
                            else:
                                resolve_dispute(d.dispute_id, "closed", resolution_note="stripe webhook: closed")
                            business_applied = True
                            break
                except Exception as e:
                    logger.warning("dispute close failed: %s", e)
    return {
        "received": True,
        "duplicate": False,
        "event_id": event.event_id,
        "provider": provider,
        "business_applied": business_applied,
        "event": event.to_dict(),
        "dispute_registered": dispute_registered,
    }


# ── Refund ───────────────────────────────────────────────────────────────
refund_router = APIRouter(prefix="/refund", tags=["billing-refund"])


@refund_router.post("/{order_id}")
async def refund_order(order_id: str, req: RefundRequest):
    order = _STATE["order_service"].get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id!r} not found")
    # Convert req.amount to cents (None stays None)
    from .payments.base import to_refund_cents, RefundValidationError
    already_refunded = int(getattr(order, "refunded_amount_cents", 0) or 0)
    try:
        amount_cents = to_refund_cents(
            req.amount,
            order_amount_cents=int(order.amount_cents),
            already_refunded_cents=already_refunded,
        ) if req.amount is not None else None
    except RefundValidationError as e:
        raise HTTPException(status_code=400, detail=f"invalid refund amount: {e}")
    try:
        # Provider-side refund (only if order has external_ref — i.e. payment was
        # already initiated at the provider). Without external_ref, there's no
        # provider-side refund to perform; we still update internal state.
        method = order.payment_method
        if method != "mock" and order.external_ref:
            try:
                prov = get_provider(method)
                # Pass amount through; provider validates + initiates refund
                prov.refund(order, amount=req.amount)
            except (KeyError, ProviderNotConfiguredError):
                pass  # proceed with internal refund regardless
            except RefundValidationError as e:
                # Distinguish "amount invalid" (reject) from "can't refund" (skip).
                msg = str(e)
                if "no external_ref" in msg or "cannot refund" in msg:
                    pass  # proceed with internal refund only
                else:
                    raise HTTPException(
                        status_code=400, detail=f"provider rejected: {e}"
                    )
        refunded = _STATE["order_service"].refund(
            order_id, reason=req.reason, amount_cents=amount_cents,
        )
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


# ============================================================================
# P1-2: Disputes API
# ============================================================================
disputes_router = APIRouter(prefix="/disputes", tags=["billing-disputes"])


class RegisterDisputeRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    payment_id: str = Field(..., min_length=1, max_length=128)
    amount_cents: int = Field(..., gt=0)
    currency: str = Field("USD", pattern=r"^(USD|CNY|EUR|GBP)$")
    reason: str = Field("general", max_length=64)
    evidence_due_days: int = Field(14, ge=1, le=60)
    alert: bool = True


class EvidenceUpload(BaseModel):
    customer_communication: Optional[str] = None
    receipt: Optional[Dict[str, Any]] = None
    shipping_documentation: Optional[Dict[str, Any]] = None
    service_documentation: Optional[Dict[str, Any]] = None
    cancellation_policy: Optional[str] = None
    uncategorized_text: Optional[str] = None


class ResolveDisputeRequest(BaseModel):
    status: str = Field(..., pattern="^(won|lost|closed)$")
    resolution_note: Optional[str] = Field(None, max_length=512)


@disputes_router.post("")
async def disputes_register(req: RegisterDisputeRequest):
    try:
        d = register_dispute(
            order_id=req.order_id,
            payment_id=req.payment_id,
            amount_cents=req.amount_cents,
            currency=req.currency,
            reason=req.reason,
            evidence_due_days=req.evidence_due_days,
            alert=req.alert,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return d.to_dict()


@disputes_router.get("")
async def disputes_list(
    order_id: Optional[str] = Query(None, max_length=64),
    open_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
):
    if open_only:
        items = list_open_disputes()
        return {"count": len(items), "items": [d.to_dict() for d in items[:limit]]}
    if order_id:
        items = get_disputes_by_order(order_id)
    else:
        items = list(_all_disputes())
    return {"count": len(items), "items": [d.to_dict() for d in items[:limit]]}


def _all_disputes():
    """测试用 — 列出所有 dispute (直接遍历内部 store)."""
    from .payments.dispute import _DISPUTES  # noqa: PLC0415
    return list(_DISPUTES.values())


@disputes_router.get("/stats")
async def disputes_stats():
    return dispute_stats()


@disputes_router.get("/{dispute_id}")
async def disputes_get(dispute_id: str):
    d = get_dispute(dispute_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"dispute {dispute_id!r} not found")
    return d.to_dict()


@disputes_router.post("/{dispute_id}/evidence")
async def disputes_upload_evidence(dispute_id: str, req: EvidenceUpload):
    try:
        d = upload_evidence(dispute_id, req.model_dump(exclude_none=True))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return d.to_dict()


@disputes_router.post("/{dispute_id}/resolve")
async def disputes_resolve(dispute_id: str, req: ResolveDisputeRequest):
    try:
        d = resolve_dispute(dispute_id, req.status, req.resolution_note)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return d.to_dict()


router.include_router(disputes_router)


# ============================================================================
# P1-5: Customer + PaymentMethod API
# ============================================================================
customers_router = APIRouter(prefix="/customers", tags=["billing-customers"])


class RegisterCustomerRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=3, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    currency: str = Field("USD", pattern=r"^(USD|CNY|EUR|GBP|JPY|HKD)$")
    provider: str = Field("stripe", max_length=32)
    external_id: Optional[str] = Field(None, max_length=128)
    metadata: Optional[Dict[str, Any]] = None


class AttachPaymentMethodRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64)
    pm_type: str = Field(..., pattern=r"^(card|alipay|wechat|bank_account|mock)$")
    token: str = Field(..., min_length=1, max_length=256)
    brand: Optional[str] = Field(None, max_length=32)
    last4: Optional[str] = Field(None, max_length=4)
    exp_month: Optional[int] = Field(None, ge=1, le=12)
    exp_year: Optional[int] = Field(None, ge=2024, le=2099)
    is_default: bool = False
    metadata: Optional[Dict[str, Any]] = None


@customers_router.post("")
async def customers_register(req: RegisterCustomerRequest):
    try:
        c = register_customer(
            user_id=req.user_id, email=req.email, name=req.name,
            currency=req.currency, provider=req.provider,
            external_id=req.external_id, metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return c.to_dict()


@customers_router.get("")
async def customers_list(limit: int = Query(100, ge=1, le=500)):
    items = list_customers(limit=limit)
    return {"count": len(items), "customers": [c.to_dict() for c in items]}


@customers_router.get("/stats")
async def customers_stats():
    return customer_stats()


@customers_router.get("/{customer_id}")
async def customers_get(customer_id: str):
    c = get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"customer {customer_id!r} not found")
    return c.to_dict()


@customers_router.get("/by-user/{user_id}")
async def customers_get_by_user(user_id: str):
    c = get_customer_by_user(user_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"customer for user {user_id!r} not found")
    return c.to_dict()


@customers_router.post("/payment-methods")
async def customers_attach_pm(req: AttachPaymentMethodRequest):
    try:
        pm = attach_payment_method(
            customer_id=req.customer_id, pm_type=req.pm_type, token=req.token,
            brand=req.brand, last4=req.last4, exp_month=req.exp_month,
            exp_year=req.exp_year, is_default=req.is_default,
            metadata=req.metadata,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return pm.to_dict()


@customers_router.get("/{customer_id}/payment-methods")
async def customers_list_pms(
    customer_id: str,
    pm_type: Optional[str] = Query(None, pattern=r"^(card|alipay|wechat|bank_account|mock)$"),
):
    c = get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"customer {customer_id!r} not found")
    items = list_payment_methods(customer_id, pm_type=pm_type)
    return {"count": len(items), "items": [pm.to_dict() for pm in items]}


@customers_router.get("/{customer_id}/payment-methods/default")
async def customers_default_pm(
    customer_id: str,
    pm_type: Optional[str] = Query(None, pattern=r"^(card|alipay|wechat|bank_account|mock)$"),
):
    c = get_customer(customer_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"customer {customer_id!r} not found")
    pm = get_default_payment_method(customer_id, pm_type=pm_type)
    if not pm:
        raise HTTPException(status_code=404, detail="no payment method")
    return pm.to_dict()


@customers_router.post("/payment-methods/{pm_id}/set-default")
async def customers_set_default_pm(pm_id: str):
    try:
        pm = set_default_payment_method(pm_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))
    return pm.to_dict()


@customers_router.delete("/payment-methods/{pm_id}")
async def customers_detach_pm(pm_id: str):
    ok = detach_payment_method(pm_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"payment_method {pm_id!r} not found")
    return {"deleted": True, "pm_id": pm_id}


router.include_router(customers_router)


__all__ = [
    "router", "reset_state", "get_state",
    "build_billing_router",  # alias
]


def build_billing_router() -> APIRouter:
    """Returns the billing router (alias for `router`)."""
    return router
