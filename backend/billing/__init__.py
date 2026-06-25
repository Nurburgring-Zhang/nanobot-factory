"""Billing & subscription package.

Public surface:
- plans:        5 plans + 12 features
- orders:       order state machine + store
- payments:     3 payment providers (Stripe / Alipay / WeChat)
- subscriptions: recurring billing + cron renewal
- quotas:       12-dimension quota check
- admin:        admin service (revenue / orders / customers)
- db:           SQLAlchemy ORM (Wallet / BillingOrder / BillingSubscription) — P6-Fix-C-3
- atomic_pay:   pay_order() with session.begin() transaction — P6-Fix-C-3
- routes:       FastAPI router
"""
from . import plans, orders, payments, subscriptions, quotas, admin, db, atomic_pay
from .routes import router, build_billing_router, reset_state, get_state

__all__ = [
    "plans", "orders", "payments", "subscriptions", "quotas", "admin",
    "db", "atomic_pay",
    "router", "build_billing_router", "reset_state", "get_state",
]
