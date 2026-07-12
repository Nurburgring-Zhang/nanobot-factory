"""P15-A1: Runtime DB initialization for quota persistence.

Two initialization entry points:

1. :func:`ensure_quota_schema` — idempotent (safe at every startup).
   Creates the 4 quota tables IF they don't exist. No-op otherwise.
   Recommended for production startup and dev ``main()``.

2. :func:`reset_quota_schema` — DESTRUCTIVE. Drops and recreates the
   quota tables only (NOT Wallet / Order / Subscription). For tests and
   admin "factory reset" tools.

This module is intentionally tiny — most of the work lives in
:mod:`billing.quota_models` and :mod:`billing.quota_db`. It's a thin
façade so the startup sequence reads naturally:

.. code-block:: python

    from billing.db import init_db
    from billing.db_init import ensure_quota_schema

    init_db()              # Wallet / Order / Subscription
    ensure_quota_schema()  # 4 quota tables
"""
from __future__ import annotations

import logging
from typing import Optional

from .db import get_engine
from .quota_models import (
    QuotaDecisionLog, QuotaEvent, QuotaResetLog, QuotaUsage,
    drop_quota_db, init_quota_db,
)

log = logging.getLogger(__name__)


def ensure_quota_schema(url: Optional[str] = None) -> bool:
    """Create the 4 quota tables if missing. Returns True if newly created.

    Safe to call on every process start — ``Base.metadata.create_all()`` is
    idempotent and emits no ``CREATE TABLE`` for tables that already exist.
    """
    eng = get_engine(url) if url else get_engine()
    # Pre-check: are the tables already there? We can ask the inspector.
    from sqlalchemy import inspect
    inspector = inspect(eng)
    existing = set(inspector.get_table_names())
    needed = {"quota_usage", "quota_event",
              "quota_reset_log", "quota_decision_log"}
    if needed.issubset(existing):
        log.debug("quota tables already exist — skipping create_all")
        return False
    log.info("creating quota tables: %s", sorted(needed - existing))
    init_quota_db(url)
    return True


def reset_quota_schema(url: Optional[str] = None) -> None:
    """Drop and recreate the 4 quota tables (DESTRUCTIVE).

    Does NOT touch Wallet / Order / Subscription tables.

    Test/dev use only. Logs a WARNING before executing.
    """
    log.warning("reset_quota_schema: dropping 4 quota tables (data loss!)")
    drop_quota_db(url)
    init_quota_db(url)


def ensure_all_billing_schema(url: Optional[str] = None) -> None:
    """One-shot helper: create billing core tables + quota tables.

    Equivalent to::

        from billing.db import init_db
        from billing.db_init import ensure_quota_schema

        init_db()
        ensure_quota_schema()

    Useful in ``main()`` / startup scripts so they don't have to remember
    the two-step.
    """
    # Lazy import to keep this module's surface area narrow.
    from .db import init_db
    init_db(url)
    ensure_quota_schema(url)


__all__ = ["ensure_quota_schema", "reset_quota_schema", "ensure_all_billing_schema"]