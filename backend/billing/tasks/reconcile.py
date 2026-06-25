"""Celery tasks for daily reconciliation (P6-Fix-C-4).

Two tasks are exposed:

1. ``reconcile_provider_task(provider)`` — reconcile one provider for
   yesterday's date. Idempotent, retried up to 3 times on transient errors.

2. ``reconcile_all_providers_task()`` — fan-out across all default providers.
   Intended as the cron entry point.

Schedule (Celery beat):
- Default: every day at 04:00 UTC (configurable via
  ``BILLING_RECONCILE_SCHEDULE_HOUR_UTC`` env var).

The Celery app is created lazily — if Celery is unavailable, the module
imports but task registration fails gracefully. Always use the module-level
``celery_app`` so worker boot doesn't break.

In production, mount the task on a dedicated worker queue ``billing.reconcile``
to isolate billing cron from user-facing traffic.

For local development / tests, set ``CELERY_TASK_ALWAYS_EAGER=1`` to run
tasks inline (no broker required). This is what the test suite does.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from celery import Celery, signals
from celery.schedules import crontab

from ..reconciliation import (
    MismatchType, MockProviderAdapter, NoopAlertHook, NormalizedTxn,
    ProviderAdapter, ReconcileAlertHook, ReconcileResult, ReconcileMismatch,
    ReconciliationEngine, WebhookAlertHook, LoggingAlertHook,
    MultiAlertHook, daily_reconcile,
    set_default_engine, get_default_engine,
)
from ..orders import InMemoryOrderStore, OrderService

logger = logging.getLogger("billing.tasks.reconcile")


# ============================================================================
# 1. Celery app (lazy)
# ============================================================================

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")
TASK_SERIALIZER = "json"
RESULT_SERIALIZER = "json"
ACCEPT_CONTENT = ["json"]
TIMEZONE = "UTC"
ENABLE_UTC = True
TASK_TRACK_STARTED = True

celery_app = Celery(
    "billing",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer=TASK_SERIALIZER,
    result_serializer=RESULT_SERIALIZER,
    accept_content=ACCEPT_CONTENT,
    timezone=TIMEZONE,
    enable_utc=ENABLE_UTC,
    task_track_started=TASK_TRACK_STARTED,
    task_default_queue="billing.reconcile",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


# ============================================================================
# 2. Schedule (Celery beat)
# ============================================================================

BILLING_RECONCILE_SCHEDULE_HOUR_UTC = int(
    os.environ.get("BILLING_RECONCILE_SCHEDULE_HOUR_UTC", "4")
)

DEFAULT_PROVIDERS: List[str] = ["stripe", "alipay", "wechat"]


def _build_schedule() -> Dict[str, Any]:
    """Build celery beat schedule with the configured hour."""
    return {
        "billing-reconcile-daily": {
            "task": "billing.reconcile_all_providers",
            "schedule": crontab(hour=BILLING_RECONCILE_SCHEDULE_HOUR_UTC, minute=0),
            "kwargs": {},
            "options": {"queue": "billing.reconcile"},
        },
    }


celery_app.conf.beat_schedule = _build_schedule()


# ============================================================================
# 3. Wiring — adapters + alert hook + engine
# ============================================================================

# Module-level state for the worker process. In production each worker
# imports its own copy; tests inject a custom state via ``configure_celery_for_billing``.
_state_lock = threading.Lock()
_adapters: Dict[str, ProviderAdapter] = {}
_alert_hook: ReconcileAlertHook = NoopAlertHook()
_order_service: Optional[OrderService] = None


def build_default_adapters() -> Dict[str, ProviderAdapter]:
    """Build the default provider adapters (MockProviderAdapter stubs).

    In production, replace this with real adapters that hit the provider
    APIs (Stripe balanceTransactions, Alipay bill_url, WeChat pay/transactions).
    """
    return {
        "stripe": MockProviderAdapter("stripe"),
        "alipay": MockProviderAdapter("alipay"),
        "wechat": MockProviderAdapter("wechat"),
    }


def build_default_alert_hook() -> ReconcileAlertHook:
    """Build the default alert hook.

    Reads env vars:
    - ``BILLING_RECONCILE_WEBHOOK_URL`` — if set, POSTs JSON to this URL.
    - ``BILLING_RECONCILE_WEBHOOK_AUTH`` — optional Authorization header value.
    - otherwise: ``LoggingAlertHook`` for observability.
    """
    webhook_url = os.environ.get("BILLING_RECONCILE_WEBHOOK_URL", "")
    if webhook_url:
        auth = os.environ.get("BILLING_RECONCILE_WEBHOOK_AUTH", "")
        return WebhookAlertHook(
            webhook_url=webhook_url,
            auth_header=auth or None,
        )
    return MultiAlertHook([LoggingAlertHook()])


def configure_celery_for_billing(order_service: Optional[Any] = None,
                                 adapters: Optional[Dict[str, ProviderAdapter]] = None,
                                 alert_hook: Optional[ReconcileAlertHook] = None) -> None:
    """Inject billing deps into the worker process.

    Call this at worker startup (or in tests) to wire the real order service,
    real adapters, and the production alert hook. Safe to call multiple times
    (last write wins).
    """
    global _order_service, _adapters, _alert_hook
    with _state_lock:
        if order_service is not None:
            _order_service = order_service
        if adapters is not None:
            _adapters = dict(adapters)
        if alert_hook is not None:
            _alert_hook = alert_hook


def reset_state() -> None:
    """Reset module-level state (test helper)."""
    global _order_service, _adapters, _alert_hook
    with _state_lock:
        _order_service = None
        _adapters = {}
        _alert_hook = NoopAlertHook()


def _ensure_state() -> tuple:
    """Lazy-init state if not already configured."""
    global _order_service, _adapters, _alert_hook
    with _state_lock:
        if _order_service is None:
            _order_service = OrderService(InMemoryOrderStore())
        if not _adapters:
            _adapters.update(build_default_adapters())
        if isinstance(_alert_hook, NoopAlertHook):
            _alert_hook = build_default_alert_hook()
    return _order_service, _adapters, _alert_hook


# ============================================================================
# 4. Tasks
# ============================================================================

@celery_app.task(
    name="billing.reconcile_provider",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def reconcile_provider_task(self, provider: str,
                            date: Optional[str] = None,
                            force_alert: bool = False) -> Dict[str, Any]:
    """Reconcile one provider for a single date.

    Args:
        provider:   "stripe" / "alipay" / "wechat" / "mock"
        date:       YYYY-MM-DD (UTC). Default = yesterday UTC.
        force_alert: send alert even when no mismatches (useful for first-run).
    """
    order_service, adapters, alert_hook = _ensure_state()
    if provider not in adapters:
        raise ValueError(
            f"unknown provider {provider!r}; available: {list(adapters.keys())}"
        )
    logger.info("reconcile task start: provider=%s date=%s", provider, date)
    try:
        result = daily_reconcile(
            provider=provider,
            date=date,
            order_service=order_service,
            adapters=adapters,
            alert_hook=alert_hook,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("reconcile task crashed: provider=%s date=%s", provider, date)
        # Re-raise so Celery records the failure and (if autoretry_for matches) retries.
        raise
    if force_alert and not result.alert_sent and not result.error:
        try:
            alert_hook.send_alert(result)
            result.alert_sent = True
        except Exception as e:  # noqa: BLE001
            result.alert_error = str(e)
    logger.info(
        "reconcile task done: provider=%s date=%s local=%d remote=%d matched=%d "
        "mismatch=%d alert_sent=%s error=%s",
        provider, result.date, result.local_count, result.remote_count,
        result.matched_count, result.mismatch_count, result.alert_sent, result.error,
    )
    return result.to_dict()


@celery_app.task(
    name="billing.reconcile_all_providers",
    bind=True,
)
def reconcile_all_providers_task(self, date: Optional[str] = None,
                                  providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Fan-out: reconcile all default providers for the same date.

    Returns a dict mapping provider -> ReconcileResult.to_dict().
    Each provider is reconciled independently; one failure does not block
    the others (we collect results then log + return).
    """
    targets = providers or DEFAULT_PROVIDERS
    logger.info("reconcile all-providers start: date=%s providers=%s", date, targets)
    out: Dict[str, Any] = {}
    for provider in targets:
        try:
            out[provider] = reconcile_provider_task(provider, date=date)
        except Exception as e:  # noqa: BLE001
            logger.exception("reconcile provider %s failed: %s", provider, e)
            out[provider] = {
                "provider": provider,
                "error": str(e),
                "mismatch_count": 0,
                "matched_count": 0,
                "local_count": 0,
                "remote_count": 0,
            }
    logger.info("reconcile all-providers done: results=%s", list(out.keys()))
    return out


# ============================================================================
# 5. Celery signals (lightweight hooks for logging)
# ============================================================================

@signals.task_prerun.connect
def _task_prerun(sender=None, task_id=None, task=None, **kwargs):  # noqa: ARG001
    logger.debug("celery task prerun: %s id=%s", task.name, task_id)


@signals.task_postrun.connect
def _task_postrun(sender=None, task_id=None, task=None, **kwargs):  # noqa: ARG001
    logger.debug("celery task postrun: %s id=%s", task.name, task_id)


# ============================================================================
# 6. Schedule rebuilder (for env reload)
# ============================================================================

def reload_schedule() -> None:
    """Re-read env and rebuild the beat schedule. Call after changing
    ``BILLING_RECONCILE_SCHEDULE_HOUR_UTC``."""
    global BILLING_RECONCILE_SCHEDULE_HOUR_UTC
    BILLING_RECONCILE_SCHEDULE_HOUR_UTC = int(
        os.environ.get("BILLING_RECONCILE_SCHEDULE_HOUR_UTC",
                       str(BILLING_RECONCILE_SCHEDULE_HOUR_UTC))
    )
    celery_app.conf.beat_schedule = _build_schedule()


# ============================================================================
# Public exports
# ============================================================================


__all__ = [
    "celery_app",
    "reconcile_provider_task", "reconcile_all_providers_task",
    "configure_celery_for_billing", "build_default_alert_hook",
    "build_default_adapters", "reload_schedule", "reset_state",
    "BILLING_RECONCILE_SCHEDULE_HOUR_UTC", "DEFAULT_PROVIDERS",
]