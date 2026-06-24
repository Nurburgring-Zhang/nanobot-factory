"""Order system for billing — state machine + persistence.

订单状态机:
    pending → paid → fulfilled (terminal)
       ↓       ↓
    cancelled refunded (terminal)
       ↓
    failed (terminal)

Public surface:
- Order dataclass (id / user_id / plan_id / amount / currency / status / payment_method / created_at / paid_at)
- OrderStore ABC + InMemoryOrderStore + JsonlOrderStore
- OrderService: state transitions with validation
- billing_orders SQL DDL for alembic
"""
from __future__ import annotations

import enum
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ============================================================================
# 1. Order model + state machine
# ============================================================================

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FULFILLED = "fulfilled"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


# Allowed transitions
_ALLOWED_TRANSITIONS: Dict[OrderStatus, set] = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.FAILED,
                          OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.FULFILLED, OrderStatus.REFUNDED},
    OrderStatus.FULFILLED: set(),  # terminal
    OrderStatus.FAILED: set(),     # terminal
    OrderStatus.REFUNDED: set(),   # terminal
    OrderStatus.CANCELLED: set(),  # terminal
}

# Convenience predicates
TERMINAL_STATUSES = {OrderStatus.FULFILLED, OrderStatus.FAILED,
                     OrderStatus.REFUNDED, OrderStatus.CANCELLED}


def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, set())


@dataclass
class Order:
    order_id: str
    user_id: str
    plan_id: str
    amount_cents: int          # always cents (e.g. 9900 = $99 or ¥99)
    currency: str              # "USD" / "CNY"
    status: OrderStatus
    payment_method: str        # "stripe" / "alipay" / "wechat" / "mock"
    created_at: str            # ISO8601 UTC
    paid_at: Optional[str] = None
    fulfilled_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 外部引用: Stripe Checkout session id / Alipay trade_no / WeChat prepay_id
    external_ref: Optional[str] = None
    # Refund info
    refunded_at: Optional[str] = None
    refund_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Order":
        d = dict(d)
        if "status" in d and isinstance(d["status"], str):
            d["status"] = OrderStatus(d["status"])
        return cls(**d)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


# ============================================================================
# 2. Order store — ABC + in-memory + JSONL
# ============================================================================

class OrderStore(Protocol):
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Optional[Order]: ...
    def list(self, user_id: Optional[str] = None,
             status: Optional[OrderStatus] = None,
             limit: int = 100) -> List[Order]: ...


class InMemoryOrderStore:
    """In-memory order store. Thread-safe (single-process)."""
    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._lock = threading.Lock()

    def save(self, order: Order) -> None:
        with self._lock:
            self._orders[order.order_id] = order

    def get(self, order_id: str) -> Optional[Order]:
        with self._lock:
            return self._orders.get(order_id)

    def list(self, user_id: Optional[str] = None,
             status: Optional[OrderStatus] = None,
             limit: int = 100) -> List[Order]:
        with self._lock:
            orders = list(self._orders.values())
        # Filter
        if user_id is not None:
            orders = [o for o in orders if o.user_id == user_id]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        # Sort: newest first
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders[:limit]


class JsonlOrderStore:
    """JSONL file-backed order store. Thread-safe within a process."""
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()
        # In-memory cache for fast lookup (loaded on first access)
        self._cache: Optional[Dict[str, Order]] = None

    def _load(self) -> Dict[str, Order]:
        if self._cache is not None:
            return self._cache
        out: Dict[str, Order] = {}
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
                        order = Order.from_dict(rec)
                    except Exception:
                        continue
                    out[order.order_id] = order
        self._cache = out
        return out

    def _flush(self) -> None:
        """Flush cache to JSONL (rewrite)."""
        if self._cache is None:
            return
        with self.path.open("w", encoding="utf-8") as f:
            for o in self._cache.values():
                f.write(json.dumps(o.to_dict(), ensure_ascii=False,
                                   separators=(",", ":")) + "\n")

    def save(self, order: Order) -> None:
        with self._lock:
            cache = self._load()
            cache[order.order_id] = order
            self._flush()

    def get(self, order_id: str) -> Optional[Order]:
        with self._lock:
            cache = self._load()
        return cache.get(order_id)

    def list(self, user_id: Optional[str] = None,
             status: Optional[OrderStatus] = None,
             limit: int = 100) -> List[Order]:
        with self._lock:
            cache = self._load()
            orders = list(cache.values())
        if user_id is not None:
            orders = [o for o in orders if o.user_id == user_id]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        orders.sort(key=lambda o: o.created_at, reverse=True)
        return orders[:limit]


# ============================================================================
# 3. Order service — orchestrates state machine + invoice trigger hook
# ============================================================================

class InvoiceTriggerHook(Protocol):
    """Hook called after a successful payment (paid → fulfilled)."""
    def on_paid(self, order: Order) -> None: ...


class NoopInvoiceTrigger:
    """Default no-op hook."""
    def on_paid(self, order: Order) -> None:  # noqa: ARG002
        pass


class OrderService:
    """High-level order service — creates orders + drives state machine.

    状态机规则:
    - pending → paid:    收到 webhook (create_payment_provider 后台)
    - pending → failed:  支付失败 (用户取消 / 超时 / provider 报错)
    - pending → cancelled: 用户主动取消
    - paid → fulfilled:  履约完成 (订阅激活 / 资源开通)
    - paid → refunded:   退款完成
    """
    def __init__(self, store: OrderStore,
                 invoice_hook: Optional[InvoiceTriggerHook] = None) -> None:
        self.store = store
        self.invoice_hook = invoice_hook or NoopInvoiceTrigger()

    def create_order(self, user_id: str, plan_id: str,
                     amount_cents: int, currency: str = "USD",
                     payment_method: str = "mock",
                     metadata: Optional[Dict[str, Any]] = None) -> Order:
        """Create a new pending order."""
        if amount_cents < 0:
            raise ValueError("amount_cents must be >= 0")
        currency = currency.upper()
        if currency not in ("USD", "CNY"):
            raise ValueError(f"unsupported currency: {currency!r}")
        order = Order(
            order_id=f"ord_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            plan_id=plan_id,
            amount_cents=int(amount_cents),
            currency=currency,
            status=OrderStatus.PENDING,
            payment_method=payment_method,
            created_at=_utcnow_iso(),
            metadata=dict(metadata or {}),
        )
        self.store.save(order)
        return order

    def transition(self, order_id: str, to_status: OrderStatus,
                   external_ref: Optional[str] = None,
                   reason: Optional[str] = None) -> Order:
        """Move order to new status. Raises ValueError on invalid transition."""
        order = self.store.get(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id!r}")
        if not can_transition(order.status, to_status):
            raise ValueError(
                f"invalid transition: {order.status.value} → {to_status.value}"
            )
        order.status = to_status
        now = _utcnow_iso()
        if to_status == OrderStatus.PAID:
            order.paid_at = now
            order.fulfilled_at = now  # by default, paid auto-fulfills
            order.status = OrderStatus.FULFILLED
            if external_ref:
                order.external_ref = external_ref
            # Hook: invoice trigger
            try:
                self.invoice_hook.on_paid(order)
            except Exception:
                pass
        elif to_status == OrderStatus.FULFILLED:
            order.fulfilled_at = now
        elif to_status == OrderStatus.REFUNDED:
            order.refunded_at = now
            order.refund_reason = reason
        self.store.save(order)
        return order

    def mark_paid(self, order_id: str, external_ref: Optional[str] = None) -> Order:
        """Convenience: pending → paid → fulfilled (combined)."""
        return self.transition(order_id, OrderStatus.PAID, external_ref=external_ref)

    def cancel(self, order_id: str, reason: Optional[str] = None) -> Order:
        """Cancel a pending order."""
        order = self.transition(order_id, OrderStatus.CANCELLED)
        if reason:
            order.metadata["cancel_reason"] = reason
            self.store.save(order)
        return order

    def refund(self, order_id: str, reason: Optional[str] = None) -> Order:
        """Refund a paid/fulfilled order."""
        order = self.store.get(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id!r}")
        if order.status not in (OrderStatus.PAID, OrderStatus.FULFILLED):
            raise ValueError(
                f"cannot refund order in status {order.status.value!r}"
            )
        if order.status == OrderStatus.PAID:
            return self.transition(order_id, OrderStatus.REFUNDED, reason=reason)
        # fulfilled → refunded (special path: not in normal transition table,
        # but we support refund after fulfillment)
        order.status = OrderStatus.REFUNDED
        order.refunded_at = _utcnow_iso()
        order.refund_reason = reason
        self.store.save(order)
        return order

    def list_for_user(self, user_id: str, limit: int = 100) -> List[Order]:
        return self.store.list(user_id=user_id, limit=limit)

    def list_all(self, status: Optional[OrderStatus] = None,
                 limit: int = 100) -> List[Order]:
        return self.store.list(status=status, limit=limit)

    def get(self, order_id: str) -> Optional[Order]:
        return self.store.get(order_id)


# ============================================================================
# 4. SQL DDL for billing_orders (alembic uses this)
# ============================================================================

BILLING_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS billing_orders (
    order_id VARCHAR(40) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(40) NOT NULL,
    amount_cents BIGINT NOT NULL DEFAULT 0,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_method VARCHAR(20) NOT NULL DEFAULT 'mock',
    external_ref VARCHAR(120) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP,
    fulfilled_at TIMESTAMP,
    refunded_at TIMESTAMP,
    refund_reason TEXT DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

BILLING_ORDERS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS billing_orders (
    order_id VARCHAR(40) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(40) NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_method VARCHAR(20) NOT NULL DEFAULT 'mock',
    external_ref VARCHAR(120) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP,
    fulfilled_at TIMESTAMP,
    refunded_at TIMESTAMP,
    refund_reason TEXT DEFAULT '',
    metadata JSON NOT NULL DEFAULT '{}'
);
"""

BILLING_ORDERS_INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_billing_orders_user_id ON billing_orders(user_id);",
    "CREATE INDEX IF NOT EXISTS ix_billing_orders_plan_id ON billing_orders(plan_id);",
    "CREATE INDEX IF NOT EXISTS ix_billing_orders_status ON billing_orders(status);",
    "CREATE INDEX IF NOT EXISTS ix_billing_orders_created_at ON billing_orders(created_at);",
    "CREATE INDEX IF NOT EXISTS ix_billing_orders_user_status ON billing_orders(user_id, status);",
]


# ============================================================================
# Helpers
# ============================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_order_id() -> str:
    return f"ord_{uuid.uuid4().hex[:16]}"


__all__ = [
    "OrderStatus", "can_transition", "TERMINAL_STATUSES",
    "Order",
    "OrderStore", "InMemoryOrderStore", "JsonlOrderStore",
    "OrderService", "InvoiceTriggerHook", "NoopInvoiceTrigger",
    "BILLING_ORDERS_DDL", "BILLING_ORDERS_DDL_SQLITE", "BILLING_ORDERS_INDEXES_DDL",
    "new_order_id",
]
