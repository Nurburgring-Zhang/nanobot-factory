"""Billing & subscription package.

Public surface:
- plans:        5 plans + 12 features
- orders:       order state machine + store
- payments:     3 payment providers (Stripe / Alipay / WeChat)
- subscriptions: recurring billing + cron renewal
- quotas:       12-dimension quota check
- admin:        admin service (revenue / orders / customers)
- routes:       FastAPI router
"""
from . import plans, orders, payments, subscriptions, quotas, admin
from .routes import router, build_billing_router, reset_state, get_state

__all__ = [
    "plans", "orders", "payments", "subscriptions", "quotas", "admin",
    "router", "build_billing_router", "reset_state", "get_state",
]
