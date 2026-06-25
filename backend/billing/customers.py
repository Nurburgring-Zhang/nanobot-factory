"""P1-5: Stripe Customer + PaymentMethod 抽象 (复用模式).

业务背景:
- 国际支付最佳实践: 每个客户 (Stripe Customer) 绑定多个支付方式 (PaymentMethod),
  订阅扣款时复用 (无需每次重新填写卡片).
- 国内支付宝/微信的 Customer 概念不强制, 但商户侧仍然需要 (用户 ID 映射).

本模块独立于具体 provider, 抽象 Customer + PaymentMethod 概念, 真实环境:
- Stripe: stripe.Customer.create / stripe.PaymentMethod.attach
- Alipay/WeChat: 用户标识 + 授权 token (open_id / union_id), 在国内 provider 内部表示.

公开 API:
  - register_customer(user_id, email, name, currency="USD")  → Customer
  - get_customer(cus_id)                                      → Customer
  - get_customer_by_user(user_id)                             → Customer
  - attach_payment_method(cus_id, pm_type, token, **meta)    → PaymentMethod
  - detach_payment_method(pm_id)                              → bool
  - list_payment_methods(cus_id)                              → [PaymentMethod]
  - get_default_payment_method(cus_id, pm_type=None)         → Optional[PaymentMethod]
  - set_default_payment_method(pm_id)                         → PaymentMethod
  - customer_stats()                                          → Dict
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PM_TYPES = ["card", "alipay", "wechat", "bank_account", "mock"]
PM_TYPE_LABELS = {
    "card": "银行卡 (Stripe)",
    "alipay": "支付宝",
    "wechat": "微信支付",
    "bank_account": "银行账户 (ACH/SEPA)",
    "mock": "测试支付方式",
}


@dataclass
class PaymentMethod:
    """支付方式 (Stripe-style)."""
    pm_id: str
    customer_id: str
    pm_type: str            # card / alipay / wechat / bank_account / mock
    token: str              # provider-side token (Stripe pm_xxx / alipay user_id / wechat open_id)
    brand: Optional[str] = None    # visa / mastercard / unionpay / alipay / wechat
    last4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    is_default: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Customer:
    """Stripe-style Customer (跨 provider 复用)."""
    cus_id: str                # cus_xxx
    user_id: str               # 内部 user_id
    email: str
    name: str
    currency: str = "USD"
    provider: str = "stripe"   # 标识创建来源 (stripe/alipay/wechat)
    external_id: Optional[str] = None  # provider 侧 ID
    default_payment_method_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 进程内存储
# ---------------------------------------------------------------------------
_CUSTOMERS: Dict[str, Customer] = {}              # cus_id -> Customer
_BY_USER: Dict[str, str] = {}                     # user_id -> cus_id (1:1)
_PAYMENT_METHODS: Dict[str, PaymentMethod] = {}   # pm_id -> PaymentMethod
_BY_CUSTOMER: Dict[str, List[str]] = {}           # cus_id -> [pm_id]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
def register_customer(
    user_id: str,
    email: str,
    name: str,
    currency: str = "USD",
    provider: str = "stripe",
    external_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Customer:
    """注册一个 Customer (1 user 1 customer). 已存在则返回并更新."""
    if not user_id or not email:
        raise ValueError("user_id and email are required")
    existing_id = _BY_USER.get(user_id)
    if existing_id:
        c = _CUSTOMERS[existing_id]
        c.email = email
        c.name = name
        c.currency = currency.upper()
        c.updated_at = _now_iso()
        return c
    cus_id = f"cus_{uuid.uuid4().hex[:16]}"
    c = Customer(
        cus_id=cus_id,
        user_id=user_id,
        email=email,
        name=name,
        currency=currency.upper(),
        provider=provider,
        external_id=external_id or cus_id,
        metadata=metadata or {},
    )
    _CUSTOMERS[cus_id] = c
    _BY_USER[user_id] = cus_id
    logger.info("customer registered: %s user=%s", cus_id, user_id)
    return c


def get_customer(cus_id: str) -> Optional[Customer]:
    return _CUSTOMERS.get(cus_id)


def get_customer_by_user(user_id: str) -> Optional[Customer]:
    cus_id = _BY_USER.get(user_id)
    return _CUSTOMERS.get(cus_id) if cus_id else None


def list_customers(limit: int = 100) -> List[Customer]:
    return list(_CUSTOMERS.values())[:limit]


# ---------------------------------------------------------------------------
# PaymentMethod
# ---------------------------------------------------------------------------
def attach_payment_method(
    customer_id: str,
    pm_type: str,
    token: str,
    *,
    brand: Optional[str] = None,
    last4: Optional[str] = None,
    exp_month: Optional[int] = None,
    exp_year: Optional[int] = None,
    is_default: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> PaymentMethod:
    """绑定支付方式到客户."""
    if pm_type not in PM_TYPES:
        raise ValueError(f"invalid pm_type: {pm_type!r}. valid: {PM_TYPES}")
    c = _CUSTOMERS.get(customer_id)
    if not c:
        raise KeyError(f"customer not found: {customer_id}")
    if not token:
        raise ValueError("token is required")
    pm_id = f"pm_{uuid.uuid4().hex[:16]}"
    pm = PaymentMethod(
        pm_id=pm_id,
        customer_id=customer_id,
        pm_type=pm_type,
        token=token,
        brand=brand,
        last4=last4,
        exp_month=exp_month,
        exp_year=exp_year,
        is_default=is_default,
        metadata=metadata or {},
    )
    _PAYMENT_METHODS[pm_id] = pm
    _BY_CUSTOMER.setdefault(customer_id, []).append(pm_id)
    if is_default:
        c.default_payment_method_id = pm_id
        c.updated_at = _now_iso()
    logger.info(
        "payment_method attached: %s cus=%s type=%s",
        pm_id, customer_id, pm_type,
    )
    return pm


def detach_payment_method(pm_id: str) -> bool:
    """解绑支付方式."""
    pm = _PAYMENT_METHODS.pop(pm_id, None)
    if not pm:
        return False
    _BY_CUSTOMER[pm.customer_id] = [
        x for x in _BY_CUSTOMER.get(pm.customer_id, []) if x != pm_id
    ]
    # Clear default if was default
    c = _CUSTOMERS.get(pm.customer_id)
    if c and c.default_payment_method_id == pm_id:
        c.default_payment_method_id = None
        c.updated_at = _now_iso()
    return True


def list_payment_methods(
    customer_id: str,
    pm_type: Optional[str] = None,
) -> List[PaymentMethod]:
    items = [
        _PAYMENT_METHODS[pid] for pid in _BY_CUSTOMER.get(customer_id, [])
        if pid in _PAYMENT_METHODS
    ]
    if pm_type:
        items = [pm for pm in items if pm.pm_type == pm_type]
    return items


def get_payment_method(pm_id: str) -> Optional[PaymentMethod]:
    return _PAYMENT_METHODS.get(pm_id)


def get_default_payment_method(
    customer_id: str,
    pm_type: Optional[str] = None,
) -> Optional[PaymentMethod]:
    c = _CUSTOMERS.get(customer_id)
    if not c or not c.default_payment_method_id:
        # Fallback: 取第一个
        pms = list_payment_methods(customer_id, pm_type=pm_type)
        return pms[0] if pms else None
    pm = _PAYMENT_METHODS.get(c.default_payment_method_id)
    if pm and pm_type and pm.pm_type != pm_type:
        pms = list_payment_methods(customer_id, pm_type=pm_type)
        return pms[0] if pms else None
    return pm


def set_default_payment_method(pm_id: str) -> PaymentMethod:
    """设默认支付方式."""
    pm = _PAYMENT_METHODS.get(pm_id)
    if not pm:
        raise KeyError(f"payment_method not found: {pm_id}")
    # 取消该客户其他默认
    for other in list_payment_methods(pm.customer_id):
        other.is_default = False
    pm.is_default = True
    c = _CUSTOMERS.get(pm.customer_id)
    if c:
        c.default_payment_method_id = pm_id
        c.updated_at = _now_iso()
    return pm


def customer_stats() -> Dict[str, Any]:
    """客户 + 支付方式 分布统计."""
    by_provider: Dict[str, int] = {}
    by_currency: Dict[str, int] = {}
    by_pm_type: Dict[str, int] = {t: 0 for t in PM_TYPES}
    for c in _CUSTOMERS.values():
        by_provider[c.provider] = by_provider.get(c.provider, 0) + 1
        by_currency[c.currency] = by_currency.get(c.currency, 0) + 1
    for pm in _PAYMENT_METHODS.values():
        by_pm_type[pm.pm_type] = by_pm_type.get(pm.pm_type, 0) + 1
    return {
        "total_customers": len(_CUSTOMERS),
        "total_payment_methods": len(_PAYMENT_METHODS),
        "by_provider": by_provider,
        "by_currency": by_currency,
        "by_pm_type": by_pm_type,
    }


# ---------------------------------------------------------------------------
# 测试用 — 重置
# ---------------------------------------------------------------------------
def _reset_customers() -> None:
    _CUSTOMERS.clear()
    _BY_USER.clear()
    _PAYMENT_METHODS.clear()
    _BY_CUSTOMER.clear()


__all__ = [
    "PM_TYPES", "PM_TYPE_LABELS",
    "PaymentMethod", "Customer",
    "register_customer", "get_customer", "get_customer_by_user", "list_customers",
    "attach_payment_method", "detach_payment_method", "list_payment_methods",
    "get_payment_method", "get_default_payment_method", "set_default_payment_method",
    "customer_stats",
    "_reset_customers",
]
