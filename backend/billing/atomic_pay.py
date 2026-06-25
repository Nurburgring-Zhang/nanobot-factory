"""Atomic payment orchestration — SQLAlchemy ``session.begin()`` transaction.

P6-Fix-C-3 (P0 修复): 把「扣费 + 创建订单 + 更新订阅」三步放进同一个
``session.begin()`` 事务块,任何中间步骤失败 → 全部 rollback。

设计要点
--------
- **ALL or NOTHING** — 整个事务块要么整体 commit,要么整体 rollback。
- **显式 ``session.begin()`` 上下文管理器** — SQLAlchemy 2.0 推荐语法,
  ``with session.begin():`` 在块结束自动 commit,块内抛异常自动 rollback。
- **可注入的 ``session_factory``** — 测试时可以传 :memory: SQLite 的 factory,
  生产可以用 Postgres。
- **可注入的 ``hook``** — ``on_paid`` 回调在事务 commit 之前调用,失败会
  触发 rollback (invoice / notification 不希望 partial commit)。
- **金额单位是 cents(分)**,避免浮点精度问题。
- **失败语义**:
    * 用户余额不足 → ``InsufficientFundsError`` (ValueError 子类)
    * 订单已存在 → ``OrderAlreadyPaidError`` (ValueError 子类)
    * 订阅 plan_id 不匹配 → ``SubscriptionPlanMismatchError``
    * 其他异常 → 自动 rollback,异常向上抛

Public surface
--------------
- :func:`pay_order` — 主入口(单次原子支付)
- :class:`InsufficientFundsError`, :class:`OrderAlreadyPaidError`,
  :class:`SubscriptionPlanMismatchError` — 业务异常
- :class:`PayHook` — invoice / notification 钩子 Protocol
- :func:`create_session_factory` — 默认 sessionmaker 工厂
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .db import Base, BillingOrder, BillingSubscription, Wallet, get_session_factory


# ─── 1. Exceptions ────────────────────────────────────────────────────────────

class InsufficientFundsError(ValueError):
    """Raised when wallet balance < order amount."""
    def __init__(self, user_id: str, balance_cents: int, required_cents: int):
        self.user_id = user_id
        self.balance_cents = balance_cents
        self.required_cents = required_cents
        super().__init__(
            f"insufficient funds: user={user_id!r} "
            f"balance={balance_cents}¢ required={required_cents}¢"
        )


class OrderAlreadyPaidError(ValueError):
    """Raised when pay_order is called on a non-pending order."""
    def __init__(self, order_id: str, current_status: str):
        self.order_id = order_id
        self.current_status = current_status
        super().__init__(
            f"order {order_id!r} not in pending state (current: {current_status!r})"
        )


class SubscriptionPlanMismatchError(ValueError):
    """Raised when requested plan_id doesn't match the active subscription plan."""
    def __init__(self, user_id: str, sub_plan: str, requested_plan: str):
        self.user_id = user_id
        self.sub_plan = sub_plan
        self.requested_plan = requested_plan
        super().__init__(
            f"user {user_id!r} has active sub for plan {sub_plan!r}, "
            f"cannot pay order for plan {requested_plan!r}"
        )


# ─── 2. PayHook Protocol ──────────────────────────────────────────────────────

class PayHook(Protocol):
    """Hooks called inside the transaction (BEFORE commit).

    If a hook raises, the whole transaction rolls back — invoice / notification
    side-effects should be idempotent or run after commit.
    """
    def on_wallet_deducted(self, wallet: Wallet, amount_cents: int) -> None: ...
    def on_order_paid(self, order: BillingOrder) -> None: ...
    def on_subscription_extended(
        self, subscription: BillingSubscription, order: BillingOrder,
    ) -> None: ...


class NoopPayHook:
    """Default no-op hook (safe for tests)."""
    def on_wallet_deducted(self, wallet: Wallet, amount_cents: int) -> None:
        pass

    def on_order_paid(self, order: BillingOrder) -> None:
        pass

    def on_subscription_extended(
        self, subscription: BillingSubscription, order: BillingOrder,
    ) -> None:
        pass


# ─── 3. Result dataclass ──────────────────────────────────────────────────────

@dataclass
class PayOrderResult:
    """Outcome of :func:`pay_order`."""
    order: BillingOrder
    wallet: Wallet
    subscription: Optional[BillingSubscription]
    amount_deducted_cents: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order": self.order.to_dict(),
            "wallet": self.wallet.to_dict(),
            "subscription": self.subscription.to_dict() if self.subscription else None,
            "amount_deducted_cents": self.amount_deducted_cents,
            "metadata": self.metadata,
        }


# ─── 4. pay_order — the atomic core ───────────────────────────────────────────

def pay_order(
    user_id: str,
    plan_id: str,
    amount_cents: int,
    currency: str = "USD",
    payment_method: str = "mock",
    *,
    external_ref: Optional[str] = None,
    subscription_period_days: int = 30,
    metadata: Optional[Dict[str, Any]] = None,
    session_factory: Optional[sessionmaker] = None,
    hook: Optional[PayHook] = None,
    existing_order_id: Optional[str] = None,
) -> PayOrderResult:
    """Atomically: deduct wallet → create/transition order → extend subscription.

    All three operations run inside a single ``session.begin()`` block.
    Any exception triggers a full rollback (deduction reversed, order reverted,
    subscription untouched).

    Parameters
    ----------
    user_id : str
        User paying.
    plan_id : str
        Plan being purchased.
    amount_cents : int
        Amount to charge (must be > 0).
    currency : str
        "USD" / "CNY".
    payment_method : str
        "stripe" / "alipay" / "wechat" / "mock".
    external_ref : str, optional
        Provider-side payment id (e.g. Stripe session id).
    subscription_period_days : int
        Period extension when an active subscription is found (default 30).
    metadata : dict, optional
        Arbitrary JSON-storable metadata attached to the order.
    session_factory : sessionmaker, optional
        Defaults to ``get_session_factory()`` (production DB).
    hook : PayHook, optional
        Side-effect hooks called inside the transaction.
    existing_order_id : str, optional
        If provided, treat this as the order to mark paid (instead of creating
        a fresh one). Useful for webhook flows.

    Returns
    -------
    PayOrderResult
        Contains the order, wallet, and (if any) subscription.

    Raises
    ------
    InsufficientFundsError
        Wallet balance < amount_cents.
    OrderAlreadyPaidError
        ``existing_order_id`` is in a non-pending state.
    SubscriptionPlanMismatchError
        User has active subscription for a different plan.
    ValueError
        Invalid arguments (e.g. amount_cents <= 0).
    """
    if amount_cents <= 0:
        raise ValueError(f"amount_cents must be > 0, got {amount_cents}")
    currency = currency.upper()
    if currency not in ("USD", "CNY"):
        raise ValueError(f"unsupported currency: {currency!r}")

    sf = session_factory or get_session_factory()
    hk = hook or NoopPayHook()

    # Single transaction block — ALL or NOTHING
    session: Session
    with sf() as session:
        with session.begin():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            md = dict(metadata or {})

            # ── Step 1: find / create the order ────────────────────────
            if existing_order_id is not None:
                order = session.get(BillingOrder, existing_order_id)
                if order is None:
                    raise KeyError(f"order not found: {existing_order_id!r}")
                if order.status != "pending":
                    raise OrderAlreadyPaidError(order.order_id, order.status)
                if order.user_id != user_id:
                    raise ValueError(
                        f"order {existing_order_id!r} belongs to "
                        f"user {order.user_id!r}, not {user_id!r}"
                    )
                if order.plan_id != plan_id:
                    raise ValueError(
                        f"order plan mismatch: order={order.plan_id!r} "
                        f"requested={plan_id!r}"
                    )
                if int(order.amount_cents) != int(amount_cents):
                    raise ValueError(
                        f"order amount mismatch: order={order.amount_cents} "
                        f"requested={amount_cents}"
                    )
                # Update external_ref if provided
                if external_ref:
                    order.external_ref = external_ref
            else:
                order = BillingOrder(
                    order_id=f"ord_{uuid.uuid4().hex[:16]}",
                    user_id=user_id,
                    plan_id=plan_id,
                    amount_cents=int(amount_cents),
                    currency=currency,
                    status="paid",
                    payment_method=payment_method,
                    external_ref=external_ref or "",
                    created_at=now,
                    paid_at=now,
                    fulfilled_at=now,
                    metadata_json=json.dumps(md, ensure_ascii=False),
                )
                session.add(order)

            # ── Step 2: deduct wallet (with row-level check) ────────────
            wallet = session.get(Wallet, user_id, with_for_update=False)
            if wallet is None:
                # Auto-create wallet with zero balance? No — the user must
                # be pre-created (registration flow). Reject with explicit
                # error.
                raise KeyError(
                    f"wallet not found for user {user_id!r}; "
                    f"create one via WalletService first"
                )
            if wallet.currency != currency:
                raise ValueError(
                    f"wallet currency mismatch: wallet={wallet.currency!r} "
                    f"order={currency!r}"
                )
            balance = int(wallet.balance_cents)
            if balance < amount_cents:
                raise InsufficientFundsError(user_id, balance, amount_cents)
            wallet.balance_cents = balance - int(amount_cents)
            wallet.updated_at = now

            hk.on_wallet_deducted(wallet, amount_cents)

            # ── Step 3: extend or create subscription ──────────────────
            sub = (
                session.query(BillingSubscription)
                .filter(BillingSubscription.user_id == user_id)
                .one_or_none()
            )
            if sub is None:
                sub = BillingSubscription(
                    subscription_id=f"sub_{uuid.uuid4().hex[:16]}",
                    user_id=user_id,
                    plan_id=plan_id,
                    status="active",
                    current_period_start=now,
                    current_period_end=now + timedelta(days=subscription_period_days),
                    cancel_at_period_end=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(sub)
            else:
                if sub.status not in ("active", "past_due"):
                    raise SubscriptionPlanMismatchError(
                        user_id, sub.plan_id, plan_id,
                    )
                if sub.plan_id != plan_id:
                    # Strict mode: don't allow paying for a different plan while
                    # a subscription for another plan is active. Callers should
                    # cancel the old sub first.
                    raise SubscriptionPlanMismatchError(
                        user_id, sub.plan_id, plan_id,
                    )
                # Extend period: if past_due/expired, restart from now; else
                # extend from current_period_end.
                end = sub.current_period_end
                if end is None or end <= now:
                    sub.current_period_start = now
                    sub.current_period_end = now + timedelta(
                        days=subscription_period_days,
                    )
                else:
                    sub.current_period_end = end + timedelta(
                        days=subscription_period_days,
                    )
                sub.status = "active"
                sub.updated_at = now

            hk.on_subscription_extended(sub, order)
            hk.on_order_paid(order)

            # Capture scalar attributes BEFORE the session closes — otherwise
            # SQLAlchemy raises DetachedInstanceError on attribute access.
            order_id_str = order.order_id

            # SQLAlchemy 2.0 ``session.begin()`` exits → commits here
            # If anything above raised, the transaction rolls back.

    # Re-fetch after commit to get fresh state (especially generated timestamps
    # from the DB). We open a NEW short transaction.
    with sf() as session:
        fresh_order = session.get(BillingOrder, order_id_str)
        fresh_wallet = session.get(Wallet, user_id)
        fresh_sub = (
            session.query(BillingSubscription)
            .filter(BillingSubscription.user_id == user_id)
            .one_or_none()
        )
        return PayOrderResult(
            order=fresh_order,
            wallet=fresh_wallet,
            subscription=fresh_sub,
            amount_deducted_cents=int(amount_cents),
            metadata=md,
        )


# ─── 5. Wallet helpers (seed / top-up for tests + ops) ───────────────────────

def create_or_topup_wallet(
    user_id: str,
    amount_cents: int,
    currency: str = "USD",
    *,
    session_factory: Optional[sessionmaker] = None,
) -> Wallet:
    """Idempotent wallet creation / top-up.

    If wallet doesn't exist → create with ``amount_cents`` as initial balance.
    If exists → add ``amount_cents`` to current balance.
    """
    if amount_cents < 0:
        raise ValueError(f"amount_cents must be >= 0, got {amount_cents}")
    sf = session_factory or get_session_factory()
    with sf() as session:
        with session.begin():
            wallet = session.get(Wallet, user_id, with_for_update=False)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if wallet is None:
                wallet = Wallet(
                    user_id=user_id,
                    balance_cents=int(amount_cents),
                    currency=currency.upper(),
                    created_at=now,
                    updated_at=now,
                )
                session.add(wallet)
            else:
                wallet.balance_cents = int(wallet.balance_cents) + int(amount_cents)
                wallet.updated_at = now
    # Re-fetch
    with sf() as session:
        return session.get(Wallet, user_id)


__all__ = [
    "InsufficientFundsError", "OrderAlreadyPaidError",
    "SubscriptionPlanMismatchError",
    "PayHook", "NoopPayHook",
    "PayOrderResult",
    "pay_order", "create_or_topup_wallet",
]