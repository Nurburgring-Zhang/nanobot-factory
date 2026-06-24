"""Admin endpoints for billing — full visibility for ops/CSM.

Endpoints (all admin-gated):
- GET /admin/orders            — list all orders (filter by user/status/date)
- POST /admin/refunds          — approve / reject refund
- GET /admin/usage             — global usage stats per dimension
- GET /admin/revenue           — revenue dashboard (MRR, ARR, churn, LTV)
- GET /admin/subscriptions     — list all subscriptions
- GET /admin/customers         — list all paying customers + their plan
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .orders import Order, OrderService, OrderStatus
from .subscriptions import (
    Subscription, SubscriptionService, SubscriptionStatus,
)
from .quotas import QuotaService
from .plans import (
    FEATURE_DIMENSIONS, PLAN_CATALOG, get_plan, price_for, tier_rank,
)


class BillingAdminService:
    """Admin service — aggregates data from order/subscription/quotas services."""
    def __init__(self, order_service: OrderService,
                 subscription_service: SubscriptionService,
                 quota_service: QuotaService) -> None:
        self.order_service = order_service
        self.subscription_service = subscription_service
        self.quota_service = quota_service

    # ── Orders ────────────────────────────────────────────────────────
    def list_orders(self, user_id: Optional[str] = None,
                    status: Optional[OrderStatus] = None,
                    plan_id: Optional[str] = None,
                    since: Optional[str] = None,  # ISO date
                    until: Optional[str] = None,
                    limit: int = 100) -> List[Dict[str, Any]]:
        orders = self.order_service.store.list(user_id=user_id, status=status, limit=limit * 4)
        # Filter further
        if plan_id is not None:
            orders = [o for o in orders if o.plan_id == plan_id]
        if since:
            orders = [o for o in orders if o.created_at >= since]
        if until:
            orders = [o for o in orders if o.created_at <= until]
        return [o.to_dict() for o in orders[:limit]]

    # ── Refund approvals ─────────────────────────────────────────────
    def list_pending_refunds(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List orders that have a refund request (metadata flag) but not yet refunded."""
        out: List[Dict[str, Any]] = []
        for o in self.order_service.store.list(limit=limit * 4):
            if o.metadata.get("refund_requested") and o.status != OrderStatus.REFUNDED:
                out.append(o.to_dict())
        return out[:limit]

    def approve_refund(self, order_id: str, reason: Optional[str] = None) -> Order:
        return self.order_service.refund(order_id, reason=reason or "admin_approved")

    def reject_refund(self, order_id: str, reason: str) -> Order:
        order = self.order_service.store.get(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id!r}")
        order.metadata["refund_rejected"] = True
        order.metadata["refund_rejection_reason"] = reason
        self.order_service.store.save(order)
        return order

    def request_refund(self, order_id: str, reason: str) -> Order:
        """Mark an order as having a refund request pending admin approval."""
        order = self.order_service.store.get(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id!r}")
        if order.status not in (OrderStatus.PAID, OrderStatus.FULFILLED):
            raise ValueError(
                f"cannot request refund for order in status {order.status.value!r}"
            )
        order.metadata["refund_requested"] = True
        order.metadata["refund_request_reason"] = reason
        self.order_service.store.save(order)
        return order

    # ── Subscriptions ────────────────────────────────────────────────
    def list_subscriptions(self, status: Optional[SubscriptionStatus] = None,
                           plan_id: Optional[str] = None,
                           limit: int = 100) -> List[Dict[str, Any]]:
        subs = self.subscription_service.list_all(status=status, limit=limit * 4)
        if plan_id is not None:
            subs = [s for s in subs if s.plan_id == plan_id]
        return [s.to_dict() for s in subs[:limit]]

    # ── Usage / revenue dashboard ────────────────────────────────────
    def revenue_summary(self) -> Dict[str, Any]:
        """Compute revenue stats: MRR, ARR, paid count, refunded count, etc."""
        all_orders = self.order_service.store.list(limit=10_000)
        paid = [o for o in all_orders if o.status in (OrderStatus.PAID, OrderStatus.FULFILLED)]
        refunded = [o for o in all_orders if o.status == OrderStatus.REFUNDED]
        failed = [o for o in all_orders if o.status == OrderStatus.FAILED]
        # Group by currency
        revenue_by_currency: Dict[str, int] = defaultdict(int)
        for o in paid:
            revenue_by_currency[o.currency] += o.amount_cents
        refunded_by_currency: Dict[str, int] = defaultdict(int)
        for o in refunded:
            refunded_by_currency[o.currency] += o.amount_cents
        # Plan breakdown
        plan_revenue: Dict[str, int] = defaultdict(int)
        for o in paid:
            plan_revenue[o.plan_id] += o.amount_cents
        # Subscriptions: count active per plan
        active_subs = self.subscription_service.list_all(status=SubscriptionStatus.ACTIVE, limit=10_000)
        mrr_by_currency: Dict[str, int] = defaultdict(int)
        for s in active_subs:
            price = price_for(s.plan_id, "monthly", "usd")
            mrr_by_currency["USD"] += price
        # Approximate ARR = MRR * 12
        arr_by_currency: Dict[str, int] = {
            c: v * 12 for c, v in mrr_by_currency.items()
        }
        return {
            "total_orders": len(all_orders),
            "paid_orders": len(paid),
            "refunded_orders": len(refunded),
            "failed_orders": len(failed),
            "revenue_cents_by_currency": dict(revenue_by_currency),
            "refunded_cents_by_currency": dict(refunded_by_currency),
            "revenue_cents_by_plan": dict(plan_revenue),
            "active_subscriptions": len(active_subs),
            "mrr_cents_by_currency": dict(mrr_by_currency),
            "arr_cents_by_currency": dict(arr_by_currency),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def customer_breakdown(self) -> List[Dict[str, Any]]:
        """List each paying user with their plan + revenue."""
        all_orders = self.order_service.store.list(limit=10_000)
        paid = [o for o in all_orders if o.status in (OrderStatus.PAID, OrderStatus.FULFILLED)]
        # Aggregate per user
        by_user: Dict[str, Dict[str, Any]] = {}
        for o in paid:
            u = by_user.setdefault(o.user_id, {
                "user_id": o.user_id,
                "orders": 0,
                "total_cents_usd": 0,
                "total_cents_cny": 0,
                "plan_ids": set(),
                "first_paid_at": None,
                "last_paid_at": None,
            })
            u["orders"] += 1
            if o.currency == "USD":
                u["total_cents_usd"] += o.amount_cents
            elif o.currency == "CNY":
                u["total_cents_cny"] += o.amount_cents
            u["plan_ids"].add(o.plan_id)
            if o.paid_at:
                if u["first_paid_at"] is None or o.paid_at < u["first_paid_at"]:
                    u["first_paid_at"] = o.paid_at
                if u["last_paid_at"] is None or o.paid_at > u["last_paid_at"]:
                    u["last_paid_at"] = o.paid_at
        out = []
        for u in by_user.values():
            u["plan_ids"] = sorted(u["plan_ids"])
            out.append(u)
        out.sort(key=lambda x: -(x["total_cents_usd"] + x["total_cents_cny"]))
        return out

    def global_usage(self) -> Dict[str, Any]:
        """Global usage stats. For in-memory tracker, returns aggregate of snapshots."""
        out: Dict[str, Any] = {
            "by_dimension": {dim: 0 for dim in FEATURE_DIMENSIONS},
            "users": 0,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        # Try to enumerate users (best-effort)
        users = set()
        for s in self.subscription_service.list_all(limit=10_000):
            users.add(s.user_id)
        for o in self.order_service.store.list(limit=10_000):
            users.add(o.user_id)
        out["users"] = len(users)
        for u in users:
            snap = self.quota_service.tracker.snapshot(u)
            for dim, qty in snap.items():
                if dim in out["by_dimension"]:
                    out["by_dimension"][dim] += int(qty)
        return out


__all__ = ["BillingAdminService"]
