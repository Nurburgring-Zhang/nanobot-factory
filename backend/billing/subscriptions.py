"""Subscription management — recurring billing, upgrade/downgrade, cron renewal.

数据模型:
- Subscription: user_id / plan_id / current_period_start / current_period_end
  / status (active / past_due / cancelled / expired) / cancel_at_period_end
- 续费规则: 到期前 24h 自动续费, 失败重试 3 次 (1h / 6h / 24h)
- 升降级: 按比例计费 (剩余时间 × (新套餐价格 - 旧套餐价格))
- 提醒: 到期前 7/3/1 天发邮件 (P2-2 webhook 集成, mock 模式写 log)
"""
from __future__ import annotations

import enum
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from .plans import (
    PLAN_CATALOG, Plan, get_plan, is_upgrade, is_downgrade, price_for,
)
from .orders import Order, OrderService, OrderStatus


# ============================================================================
# 1. Subscription model
# ============================================================================

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"      # 续费失败, 宽限期内
    CANCELLED = "cancelled"    # 用户主动取消, 当前周期末失效
    EXPIRED = "expired"        # 周期结束, 未续费


@dataclass
class Subscription:
    subscription_id: str
    user_id: str
    plan_id: str
    status: SubscriptionStatus
    current_period_start: str   # ISO8601
    current_period_end: str     # ISO8601
    cancel_at_period_end: bool
    created_at: str
    updated_at: str
    # 可选字段
    last_renewal_attempt_at: Optional[str] = None
    last_renewal_order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Subscription":
        d = dict(d)
        if "status" in d and isinstance(d["status"], str):
            d["status"] = SubscriptionStatus(d["status"])
        return cls(**d)

    def is_active(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE)

    def days_until_renewal(self) -> int:
        end = datetime.fromisoformat(self.current_period_end)
        now = datetime.now(timezone.utc)
        delta = end - now
        return max(0, delta.days)


# ============================================================================
# 2. Subscription store
# ============================================================================

class SubscriptionStore(Protocol):
    def save(self, sub: Subscription) -> None: ...
    def get(self, subscription_id: str) -> Optional[Subscription]: ...
    def get_by_user(self, user_id: str) -> Optional[Subscription]: ...
    def list(self, status: Optional[SubscriptionStatus] = None,
             limit: int = 100) -> List[Subscription]: ...
    def list_due_renewal(self, days: int = 7) -> List[Subscription]: ...


class InMemorySubscriptionStore:
    """Thread-safe in-memory store."""
    def __init__(self) -> None:
        self._subs: Dict[str, Subscription] = {}
        self._by_user: Dict[str, str] = {}  # user_id -> subscription_id
        self._lock = threading.Lock()

    def save(self, sub: Subscription) -> None:
        with self._lock:
            self._subs[sub.subscription_id] = sub
            self._by_user[sub.user_id] = sub.subscription_id

    def get(self, subscription_id: str) -> Optional[Subscription]:
        with self._lock:
            return self._subs.get(subscription_id)

    def get_by_user(self, user_id: str) -> Optional[Subscription]:
        with self._lock:
            sid = self._by_user.get(user_id)
            if sid is None:
                return None
            return self._subs.get(sid)

    def list(self, status: Optional[SubscriptionStatus] = None,
             limit: int = 100) -> List[Subscription]:
        with self._lock:
            subs = list(self._subs.values())
        if status is not None:
            subs = [s for s in subs if s.status == status]
        subs.sort(key=lambda s: s.created_at, reverse=True)
        return subs[:limit]

    def list_due_renewal(self, days: int = 7) -> List[Subscription]:
        """Subscriptions that will renew within ``days`` days (or are past_due)."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        with self._lock:
            subs = list(self._subs.values())
        out = []
        for s in subs:
            if s.status == SubscriptionStatus.PAST_DUE:
                out.append(s)
                continue
            if s.status != SubscriptionStatus.ACTIVE:
                continue
            end = datetime.fromisoformat(s.current_period_end)
            if end <= cutoff:
                out.append(s)
        return out


class JsonlSubscriptionStore:
    """JSONL-backed subscription store (per-process cache + file flush)."""
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()
        self._cache: Optional[Dict[str, Subscription]] = None

    def _load(self) -> Dict[str, Subscription]:
        if self._cache is not None:
            return self._cache
        out: Dict[str, Subscription] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        sub = Subscription.from_dict(rec)
                    except Exception:
                        continue
                    out[sub.subscription_id] = sub
        self._cache = out
        return out

    def _flush(self) -> None:
        if self._cache is None:
            return
        with self.path.open("w", encoding="utf-8") as f:
            for s in self._cache.values():
                f.write(json.dumps(s.to_dict(), ensure_ascii=False,
                                   separators=(",", ":")) + "\n")

    def save(self, sub: Subscription) -> None:
        with self._lock:
            cache = self._load()
            cache[sub.subscription_id] = sub
            self._flush()

    def get(self, subscription_id: str) -> Optional[Subscription]:
        with self._lock:
            return self._load().get(subscription_id)

    def get_by_user(self, user_id: str) -> Optional[Subscription]:
        with self._lock:
            for s in self._load().values():
                if s.user_id == user_id:
                    return s
        return None

    def list(self, status: Optional[SubscriptionStatus] = None,
             limit: int = 100) -> List[Subscription]:
        with self._lock:
            subs = list(self._load().values())
        if status is not None:
            subs = [s for s in subs if s.status == status]
        subs.sort(key=lambda s: s.created_at, reverse=True)
        return subs[:limit]

    def list_due_renewal(self, days: int = 7) -> List[Subscription]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        with self._lock:
            subs = list(self._load().values())
        out = []
        for s in subs:
            if s.status == SubscriptionStatus.PAST_DUE:
                out.append(s)
                continue
            if s.status != SubscriptionStatus.ACTIVE:
                continue
            end = datetime.fromisoformat(s.current_period_end)
            if end <= cutoff:
                out.append(s)
        return out


# ============================================================================
# 3. Notification hook (email/webhook — 7/3/1 day reminders)
# ============================================================================

class NotificationHook(Protocol):
    def send_renewal_reminder(self, sub: Subscription, days_left: int) -> None: ...
    def send_renewal_success(self, sub: Subscription) -> None: ...
    def send_renewal_failed(self, sub: Subscription, reason: str) -> None: ...


class LoggingNotificationHook:
    """Default — write JSON lines to a file (or stdout in tests)."""
    def __init__(self, log_path: Optional[str] = None) -> None:
        self.log_path = log_path

    def _log(self, event: str, **fields: Any) -> None:
        rec = {"event": event, "ts": _utcnow_iso(), **fields}
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        if self.log_path:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        # Also: print to stdout in test mode
        import sys
        print(f"[billing.notify] {line}", file=sys.stderr)

    def send_renewal_reminder(self, sub: Subscription, days_left: int) -> None:
        self._log("subscription.renewal_reminder",
                  subscription_id=sub.subscription_id,
                  user_id=sub.user_id, plan_id=sub.plan_id,
                  days_left=days_left)

    def send_renewal_success(self, sub: Subscription) -> None:
        self._log("subscription.renewal_success",
                  subscription_id=sub.subscription_id,
                  user_id=sub.user_id, plan_id=sub.plan_id)

    def send_renewal_failed(self, sub: Subscription, reason: str) -> None:
        self._log("subscription.renewal_failed",
                  subscription_id=sub.subscription_id,
                  user_id=sub.user_id, plan_id=sub.plan_id,
                  reason=reason)


# ============================================================================
# 4. Subscription service
# ============================================================================

class SubscriptionService:
    """High-level service — create / upgrade / cancel / renew.

    Pairs with OrderService to charge renewals.
    """
    def __init__(self, store: SubscriptionStore,
                 order_service: OrderService,
                 notification_hook: Optional[NotificationHook] = None,
                 renewal_window_days: int = 7) -> None:
        self.store = store
        self.order_service = order_service
        self.notification_hook = notification_hook or LoggingNotificationHook()
        self.renewal_window_days = renewal_window_days

    # ── create ────────────────────────────────────────────────────────
    def create(self, user_id: str, plan_id: str,
               period: str = "monthly", currency: str = "USD",
               payment_method: str = "mock",
               trial_days: int = 0) -> Subscription:
        """Create a new subscription (does NOT auto-charge — that's done by order service)."""
        # Check if user already has subscription
        existing = self.store.get_by_user(user_id)
        if existing and existing.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
            raise ValueError(
                f"user {user_id!r} already has active subscription "
                f"({existing.subscription_id}, plan={existing.plan_id})"
            )
        # Period setup
        now = datetime.now(timezone.utc)
        if trial_days > 0:
            start = now
            end = now + timedelta(days=trial_days)
        else:
            start = now
            end = now + (timedelta(days=365) if period == "yearly" else timedelta(days=30))
        sub = Subscription(
            subscription_id=f"sub_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=start.isoformat(),
            current_period_end=end.isoformat(),
            cancel_at_period_end=False,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        self.store.save(sub)
        return sub

    # ── upgrade / downgrade ──────────────────────────────────────────
    def change_plan(self, user_id: str, new_plan_id: str,
                    period: str = "monthly",
                    currency: str = "USD",
                    payment_method: str = "mock") -> Dict[str, Any]:
        """Upgrade or downgrade subscription. Pro-rates the price.

        Returns dict with: subscription, prorated_amount_cents, order_id.
        """
        sub = self.store.get_by_user(user_id)
        if sub is None:
            raise KeyError(f"no subscription for user {user_id!r}")
        if not sub.is_active():
            raise ValueError(
                f"subscription not active: status={sub.status.value!r}"
            )
        old_plan_id = sub.plan_id
        if old_plan_id == new_plan_id:
            raise ValueError("new plan is same as current")
        # Compute prorated amount
        period_end = datetime.fromisoformat(sub.current_period_end)
        now = datetime.now(timezone.utc)
        total_secs = (period_end - datetime.fromisoformat(sub.current_period_start)).total_seconds()
        remaining_secs = max(0.0, (period_end - now).total_seconds())
        ratio = remaining_secs / total_secs if total_secs > 0 else 0.0
        old_price = price_for(old_plan_id, period, currency)
        new_price = price_for(new_plan_id, period, currency)
        if is_upgrade(old_plan_id, new_plan_id):
            direction = "upgrade"
            # Charge the difference
            diff = new_price - old_price
            prorated = int(round(diff * ratio))
        elif is_downgrade(old_plan_id, new_plan_id):
            direction = "downgrade"
            # Credit the difference
            diff = old_price - new_price
            prorated = -int(round(diff * ratio))
        else:
            raise ValueError(f"unknown plan transition: {old_plan_id} -> {new_plan_id}")
        # Update subscription
        sub.plan_id = new_plan_id
        sub.updated_at = now.isoformat()
        self.store.save(sub)
        # Create order for the prorated charge (if any)
        order = None
        if prorated > 0:
            order = self.order_service.create_order(
                user_id=user_id, plan_id=new_plan_id,
                amount_cents=prorated, currency=currency,
                payment_method=payment_method,
                metadata={"kind": direction, "from_plan": old_plan_id,
                          "to_plan": new_plan_id, "subscription_id": sub.subscription_id},
            )
        return {
            "subscription": sub.to_dict(),
            "direction": direction,
            "old_plan_id": old_plan_id,
            "new_plan_id": new_plan_id,
            "prorated_amount_cents": prorated,
            "order_id": order.order_id if order else None,
        }

    # ── cancel ────────────────────────────────────────────────────────
    def cancel(self, user_id: str, at_period_end: bool = True) -> Subscription:
        sub = self.store.get_by_user(user_id)
        if sub is None:
            raise KeyError(f"no subscription for user {user_id!r}")
        if at_period_end:
            sub.cancel_at_period_end = True
            sub.updated_at = _utcnow_iso()
            self.store.save(sub)
        else:
            # Cancel immediately
            sub.status = SubscriptionStatus.CANCELLED
            sub.updated_at = _utcnow_iso()
            self.store.save(sub)
        return sub

    # ── renew ─────────────────────────────────────────────────────────
    def renew(self, subscription_id: str,
              payment_method: str = "mock",
              currency: str = "USD") -> Order:
        """Renew a subscription. Creates a new order (to be charged separately)."""
        sub = self.store.get(subscription_id)
        if sub is None:
            raise KeyError(f"subscription not found: {subscription_id!r}")
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
            raise ValueError(
                f"cannot renew subscription in status {sub.status.value!r}"
            )
        amount = price_for(sub.plan_id, "monthly", currency)
        order = self.order_service.create_order(
            user_id=sub.user_id, plan_id=sub.plan_id,
            amount_cents=amount, currency=currency,
            payment_method=payment_method,
            metadata={"kind": "renewal", "subscription_id": sub.subscription_id},
        )
        sub.last_renewal_attempt_at = _utcnow_iso()
        sub.last_renewal_order_id = order.order_id
        self.store.save(sub)
        return order

    def mark_renewal_succeeded(self, subscription_id: str) -> Subscription:
        """Called after a renewal order is paid — extend period."""
        sub = self.store.get(subscription_id)
        if sub is None:
            raise KeyError(f"subscription not found: {subscription_id!r}")
        now = datetime.now(timezone.utc)
        # If we're past the end, start from now; otherwise extend from end
        end = datetime.fromisoformat(sub.current_period_end)
        if now >= end:
            new_start = now
        else:
            new_start = end
        new_end = new_start + timedelta(days=30)
        sub.current_period_start = new_start.isoformat()
        sub.current_period_end = new_end.isoformat()
        sub.status = SubscriptionStatus.ACTIVE
        sub.updated_at = now.isoformat()
        self.store.save(sub)
        try:
            self.notification_hook.send_renewal_success(sub)
        except Exception:
            pass
        return sub

    def mark_renewal_failed(self, subscription_id: str, reason: str) -> Subscription:
        sub = self.store.get(subscription_id)
        if sub is None:
            raise KeyError(f"subscription not found: {subscription_id!r}")
        sub.status = SubscriptionStatus.PAST_DUE
        sub.updated_at = _utcnow_iso()
        self.store.save(sub)
        try:
            self.notification_hook.send_renewal_failed(sub, reason)
        except Exception:
            pass
        return sub

    # ── cron: daily renewal check + reminders ─────────────────────────
    def run_renewal_cron(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run daily renewal cron. Returns summary of actions.

        - Subscriptions with end <= now → auto-renew (create order)
        - Subscriptions with end in [now, now+7d] → send 7/3/1 day reminders
        - PAST_DUE subs → retry (record attempt)
        """
        now = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "ran_at": now.isoformat(),
            "reminders_sent": 0,
            "renewals_triggered": 0,
            "expired": 0,
            "errors": [],
            "dry_run": dry_run,
        }
        # 1) Process due-for-renewal subscriptions
        for sub in self.store.list_due_renewal(self.renewal_window_days):
            try:
                end = datetime.fromisoformat(sub.current_period_end)
                days_left = max(0, (end - now).days)
                # Send reminder at 7/3/1 day windows
                if days_left in (7, 3, 1) and sub.status == SubscriptionStatus.ACTIVE:
                    if not dry_run:
                        self.notification_hook.send_renewal_reminder(sub, days_left)
                    result["reminders_sent"] += 1
                # Past_due retry
                if sub.status == SubscriptionStatus.PAST_DUE:
                    if not dry_run:
                        self.renew(sub.subscription_id)
                    result["renewals_triggered"] += 1
                    continue
                # Auto-renew: end is now or past
                if end <= now and sub.status == SubscriptionStatus.ACTIVE:
                    if sub.cancel_at_period_end:
                        # User cancelled — expire
                        if not dry_run:
                            sub.status = SubscriptionStatus.EXPIRED
                            sub.updated_at = now.isoformat()
                            self.store.save(sub)
                        result["expired"] += 1
                    else:
                        if not dry_run:
                            self.renew(sub.subscription_id)
                        result["renewals_triggered"] += 1
            except Exception as e:
                result["errors"].append({
                    "subscription_id": sub.subscription_id,
                    "error": f"{type(e).__name__}: {str(e)[:200]}",
                })
        return result

    # ── queries ───────────────────────────────────────────────────────
    def get_by_user(self, user_id: str) -> Optional[Subscription]:
        return self.store.get_by_user(user_id)

    def get(self, subscription_id: str) -> Optional[Subscription]:
        return self.store.get(subscription_id)

    def list_all(self, status: Optional[SubscriptionStatus] = None,
                 limit: int = 100) -> List[Subscription]:
        return self.store.list(status=status, limit=limit)


# ============================================================================
# 5. SQL DDL for billing_subscriptions
# ============================================================================

BILLING_SUBSCRIPTIONS_DDL = """
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    subscription_id VARCHAR(40) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_renewal_attempt_at TIMESTAMP,
    last_renewal_order_id VARCHAR(40) DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

BILLING_SUBSCRIPTIONS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    subscription_id VARCHAR(40) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_renewal_attempt_at TIMESTAMP,
    last_renewal_order_id VARCHAR(40) DEFAULT '',
    metadata JSON NOT NULL DEFAULT '{}'
);
"""

BILLING_SUBSCRIPTIONS_INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_user_id ON billing_subscriptions(user_id);",
    "CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_plan_id ON billing_subscriptions(plan_id);",
    "CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_status ON billing_subscriptions(status);",
    "CREATE INDEX IF NOT EXISTS ix_billing_subscriptions_period_end ON billing_subscriptions(current_period_end);",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_billing_subscriptions_user ON billing_subscriptions(user_id);",
]


# ============================================================================
# Helpers
# ============================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_subscription_id() -> str:
    return f"sub_{uuid.uuid4().hex[:16]}"


__all__ = [
    "SubscriptionStatus", "Subscription",
    "SubscriptionStore", "InMemorySubscriptionStore", "JsonlSubscriptionStore",
    "NotificationHook", "LoggingNotificationHook",
    "SubscriptionService",
    "BILLING_SUBSCRIPTIONS_DDL", "BILLING_SUBSCRIPTIONS_DDL_SQLITE",
    "BILLING_SUBSCRIPTIONS_INDEXES_DDL",
    "new_subscription_id",
]
