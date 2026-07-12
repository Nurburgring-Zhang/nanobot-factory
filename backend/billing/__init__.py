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

P15-B + P15-C: ``init_billing_runtime()`` boots the production schema +
tracker on application startup. Hook it into your FastAPI ``lifespan`` or
call it once in ``main()``::

    from billing import init_billing_runtime

    @asynccontextmanager
    async def lifespan(app):
        init_billing_runtime()
        yield

Or::

    if __name__ == "__main__":
        from billing import init_billing_runtime
        init_billing_runtime()
        uvicorn.run(app, ...)

P15-C data-loss safety: by default ``reset_db=False``, so production quota
data is preserved across restarts. For dev/test clean-slate behavior, set
``BILLING_RESET_DB_ON_STARTUP=1`` (or pass ``reset_db=True`` explicitly).
"""
import os as _os
from typing import Optional

from . import plans, orders, payments, subscriptions, quotas, admin, db, atomic_pay
from .routes import (
    router, build_billing_router, reset_state, get_state,
    set_quota_tracker_backend,
)

__all__ = [
    "plans", "orders", "payments", "subscriptions", "quotas", "admin",
    "db", "atomic_pay",
    "router", "build_billing_router", "reset_state", "get_state",
    "set_quota_tracker_backend",
    "init_billing_runtime",  # P15-B: production startup hook
]


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _resolve_reset_db(reset_db: Optional[bool]) -> bool:
    """Resolve ``reset_db`` flag from explicit arg > ENV > default-False.

    P15-C: production-safe default is ``False`` (preserve quota tables
    across restarts). ENV ``BILLING_RESET_DB_ON_STARTUP`` accepts the
    standard truthy tokens ``1/true/yes/on`` (case-insensitive); any
    other value (including unset) means ``False``.
    """
    if reset_db is not None:
        return bool(reset_db)
    env_val = _os.environ.get("BILLING_RESET_DB_ON_STARTUP", "")
    return env_val.strip().lower() in _TRUTHY


def init_billing_runtime(
    url: Optional[str] = None,
    reset_db: Optional[bool] = None,
) -> None:
    """P15-B + P15-C: Production startup hook.

    1. ``init_db()`` — Wallet / Order / Subscription tables (idempotent).
    2. ``ensure_quota_schema()`` — quota_usage / quota_event / quota_reset_log
       / quota_decision_log (idempotent, no-op if tables exist).
    3. ``reset_state(reset_db=...)`` — rebuild ``_STATE`` so it picks up the
       freshly-created tracker (so the singleton quota_service carries a
       DBQuotaTracker, not the InMemoryQuotaTracker that was bound at import
       time).

    P15-C fix: ``reset_db`` now defaults to ``False`` so quota tables are
    preserved across process restarts. The previous default of ``True``
    would wipe all persisted quota usage on every startup — a P0
    data-loss bug in production.

    Resolution order for ``reset_db``:

    1. Explicit ``reset_db`` argument (highest priority).
    2. ENV ``BILLING_RESET_DB_ON_STARTUP`` — truthy (``1``/``true``/``yes``/``on``,
       case-insensitive) enables the destructive reset; anything else means
       ``False``.
    3. Hard default: ``False`` (production-safe).

    Other environment variables honored:

    - ``QUOTA_TRACKER_BACKEND`` — ``db`` (default) or ``memory``.
    - ``BILLING_DB_URL`` — SQLAlchemy URL for the DB backend (default
      ``sqlite:///backend/data/billing.db``).

    Returns nothing — failures during schema bootstrap are logged but do not
    raise (so an unbootable DB does not crash module import; quota enforcement
    will surface the failure on the first write).
    """
    import logging as _logging
    log = _logging.getLogger(__name__)
    resolved_reset = _resolve_reset_db(reset_db)
    # 1+2: schema bootstrap (idempotent).
    try:
        from .db_init import ensure_all_billing_schema
        ensure_all_billing_schema(url)
    except Exception as exc:
        log.warning("init_billing_runtime: schema bootstrap failed: %s", exc)
    # 3: rebuild state so the singleton quota_service is bound to the chosen
    # tracker backend (env-driven via build_default_tracker).
    # P15-C: pass ``reset_db=False`` by default to preserve quota data.
    try:
        reset_state(reset_db=resolved_reset)
    except Exception as exc:
        log.warning("init_billing_runtime: reset_state failed: %s", exc)
    if resolved_reset:
        log.warning(
            "init_billing_runtime: reset_db=True (DEV/TEST mode) — "
            "quota tables were wiped on this startup"
        )
    else:
        log.debug(
            "init_billing_runtime: reset_db=False (production default) — "
            "quota tables preserved"
        )