"""Daily reconciliation between third-party payment providers and local orders.

对账机制 (P6-Fix-C-4):
- daily_reconcile(provider, date) → 拉第三方昨日所有交易 vs 本地 orders
- 差异标记 (mismatch)
- 告警 webhook

Reconciliation strategy
------------------------
We compare **two parallel ledgers**:

  1. **Local ledger**: ``OrderService.list_all(...)`` filtered by status (paid/fulfilled/
     refunded) and ``created_at`` in the target window.

  2. **Remote ledger**: ``ProviderAdapter.fetch_transactions(date)`` — a thin
     abstraction that pulls the provider's authoritative list of transactions
     for that date. In mock mode this is a fake ledger; in live mode this would
     call Stripe / Alipay / WeChat's reconciliation endpoints.

We then build two ``dict[order_id -> NormalizedTxn]`` and compute symmetric
difference. Mismatches are bucketed into:

  - MISSING_LOCAL      order at provider has no local record (refund clawback
                       risk — money came in but our system doesn't know).
  - MISSING_REMOTE     local order says paid but provider doesn't have it
                       (webhook lost — must be replayed).
  - AMOUNT_MISMATCH    both ledgers have the order but the amount differs
                       (currency rounding bug, partial capture, etc.).
  - STATUS_MISMATCH    local status differs from provider status (e.g. local
                       says PAID, provider says REFUNDED).
  - REFUND_MISMATCH    refund at provider has no matching local refund (or
                       amount differs).

All findings are returned in ``ReconcileResult.mismatches``. If
``alert_hook`` is configured, the engine fires the webhook once per non-empty
run (with a payload describing every mismatch). The webhook is best-effort:
if it raises, the run still returns the result and records ``alert_error``.

Public surface
--------------
- MismatchType (enum)
- ReconcileMismatch (dataclass)
- ReconcileResult (dataclass)
- NormalizedTxn (dataclass) — provider-agnostic txn record
- ProviderAdapter (ABC) — implement ``fetch_transactions(date) -> List[NormalizedTxn]``
- MockProviderAdapter (concrete)
- ReconcileAlertHook (Protocol) — ``send_alert(result: ReconcileResult) -> None``
- WebhookAlertHook (concrete) — POSTs JSON to ``webhook_url``
- LoggingAlertHook (concrete) — writes structured log
- ReconciliationEngine
- daily_reconcile(provider, date, ...) — module-level convenience
"""
from __future__ import annotations

import abc
import enum
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date as _date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

from .orders import Order, OrderService, OrderStatus


logger = logging.getLogger("billing.reconciliation")


# ============================================================================
# 1. Core data types
# ============================================================================

class MismatchType(str, enum.Enum):
    """Categories of reconciliation mismatch."""
    MISSING_LOCAL = "missing_local"      # provider has order, local doesn't
    MISSING_REMOTE = "missing_remote"    # local has order, provider doesn't
    AMOUNT_MISMATCH = "amount_mismatch"  # amount differs
    STATUS_MISMATCH = "status_mismatch"  # status differs
    REFUND_MISMATCH = "refund_mismatch"  # refund amount/count differs
    CURRENCY_MISMATCH = "currency_mismatch"  # currency code differs


@dataclass
class NormalizedTxn:
    """Provider-agnostic normalized transaction record.

    The reconciliation engine normalizes provider-specific transaction
    objects (Stripe charge, Alipay trade, WeChat pay transaction) into this
    common shape. ``order_id`` is the **internal** order id (NOT the provider's
    external reference), ``provider_txn_id`` is the provider-side identifier.
    """
    order_id: str                       # internal order_id (e.g. ord_xxxx)
    provider_txn_id: str                # provider-side id (pi_xxx / trade_no / transaction_id)
    provider: str                       # "stripe" / "alipay" / "wechat" / "mock"
    amount_cents: int                   # gross amount (positive for charge, negative for refund)
    currency: str                       # "USD" / "CNY"
    status: str                         # "paid" / "refunded" / "pending" / "failed"
    refunded_amount_cents: int = 0      # cumulative refund amount (in cents)
    occurred_at: str = ""               # ISO8601 UTC
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def is_refund(self) -> bool:
        return self.amount_cents < 0

    @property
    def net_amount_cents(self) -> int:
        """Net of refund (charge + cumulative refunds). For reconciliation purposes
        this is what the merchant actually 'kept' from this order.
        """
        return self.amount_cents - self.refunded_amount_cents


@dataclass
class ReconcileMismatch:
    """A single discrepancy between local and remote ledgers."""
    mismatch_type: MismatchType
    order_id: str
    provider: str
    description: str
    expected: Any = None     # local-side value (or None if missing local)
    actual: Any = None       # remote-side value (or None if missing remote)
    delta_cents: int = 0     # for AMOUNT_MISMATCH / REFUND_MISMATCH — diff in cents

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mismatch_type"] = self.mismatch_type.value
        return d


@dataclass
class ReconcileResult:
    """Result of a reconciliation run for a single provider + date."""
    run_id: str                       # recon_<uuid>
    provider: str                     # "stripe" / "alipay" / "wechat" / "mock"
    date: str                         # YYYY-MM-DD (UTC)
    started_at: str                   # ISO8601
    finished_at: str                  # ISO8601
    duration_ms: int = 0
    local_count: int = 0
    remote_count: int = 0
    matched_count: int = 0
    mismatch_count: int = 0
    mismatches: List[ReconcileMismatch] = field(default_factory=list)
    total_local_amount_cents: int = 0
    total_remote_amount_cents: int = 0
    total_delta_cents: int = 0
    alert_sent: bool = False
    alert_error: Optional[str] = None
    error: Optional[str] = None       # fatal error (provider unreachable, etc.)

    @property
    def has_mismatches(self) -> bool:
        return self.mismatch_count > 0

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "date": self.date,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "local_count": self.local_count,
            "remote_count": self.remote_count,
            "matched_count": self.matched_count,
            "mismatch_count": self.mismatch_count,
            "total_local_amount_cents": self.total_local_amount_cents,
            "total_remote_amount_cents": self.total_remote_amount_cents,
            "total_delta_cents": self.total_delta_cents,
            "alert_sent": self.alert_sent,
            "alert_error": self.alert_error,
            "error": self.error,
            "by_type": self._by_type(),
        }

    def _by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for m in self.mismatches:
            t = m.mismatch_type.value
            out[t] = out.get(t, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        d = self.summary()
        d["mismatches"] = [m.to_dict() for m in self.mismatches]
        return d


# ============================================================================
# 2. Provider adapter — abstract + mock concrete
# ============================================================================

class ProviderAdapter(abc.ABC):
    """Abstract adapter for fetching transactions from a payment provider.

    Implementations may use the real provider API (Stripe / Alipay / WeChat),
    a cached snapshot, or a mock for tests.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    @abc.abstractmethod
    def fetch_transactions(self, date: Union[str, _date]) -> List[NormalizedTxn]:
        """Fetch all transactions (charges + refunds) that occurred on ``date``
        (UTC). Returns list of NormalizedTxn, may be empty.

        Raises:
            ProviderReconciliationError on unrecoverable error (network, auth).
        """


class ProviderReconciliationError(RuntimeError):
    """Raised when the provider adapter cannot complete the fetch."""


class MockProviderAdapter(ProviderAdapter):
    """In-memory mock adapter — for tests and stub provider.

    Holds a dictionary ``txns_by_date[date_str] -> List[NormalizedTxn]``
    that callers can pre-populate. ``fetch_transactions`` returns the snapshot
    for that date (or empty list if date not seeded).

    Optional injectable fetch function:
        fetch_fn(date_str) -> List[NormalizedTxn] | None
    is called first; if it returns None, the in-memory snapshot is used.
    """

    def __init__(self, provider_name: str = "mock",
                 fetch_fn: Optional[Callable[[str], Optional[List[NormalizedTxn]]]] = None,
                 fail_on_dates: Optional[List[str]] = None,
                 latency_ms: int = 0) -> None:
        self._provider_name = provider_name
        self._fetch_fn = fetch_fn
        self._fail_on_dates = set(fail_on_dates or [])
        self._latency_ms = latency_ms
        self._txns_by_date: Dict[str, List[NormalizedTxn]] = {}
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def add(self, txn: NormalizedTxn, occurred_on: Union[str, _date]) -> None:
        """Pre-seed a transaction for a date."""
        d = _normalize_date(occurred_on)
        with self._lock:
            self._txns_by_date.setdefault(d, []).append(txn)

    def clear(self) -> None:
        with self._lock:
            self._txns_by_date.clear()

    def fetch_transactions(self, date: Union[str, _date]) -> List[NormalizedTxn]:
        d = _normalize_date(date)
        if self._latency_ms:
            time.sleep(self._latency_ms / 1000.0)
        if d in self._fail_on_dates:
            raise ProviderReconciliationError(
                f"mock fetch failed for date {d}"
            )
        if self._fetch_fn is not None:
            out = self._fetch_fn(d)
            if out is not None:
                return list(out)
        with self._lock:
            return list(self._txns_by_date.get(d, []))


# ============================================================================
# 3. Alert hooks
# ============================================================================

class ReconcileAlertHook(Protocol):
    """Hook called when reconciliation finds mismatches (or always, depending
    on implementation). Implementations must NOT raise on transient errors —
    they should catch internally and log, OR raise and let the engine catch.
    """
    def send_alert(self, result: ReconcileResult) -> None: ...


class WebhookAlertHook:
    """POSTs the result as JSON to ``webhook_url``.

    Config:
        webhook_url:  full URL to POST to (required)
        timeout_s:    HTTP timeout (default 10s)
        min_severity: only fire if mismatch_count >= min_severity (default 1)
        auth_header:  optional pre-built Authorization header value (e.g. "Bearer xxx")
        session:      optional injectable requests.Session (tests)

    If requests is not installed OR HTTP fails, the hook records the error
    but does NOT raise — the reconciliation run completes regardless.
    """

    def __init__(self, webhook_url: str, timeout_s: float = 10.0,
                 min_severity: int = 1, auth_header: Optional[str] = None,
                 session: Optional[Any] = None) -> None:
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self.webhook_url = webhook_url
        self.timeout_s = timeout_s
        self.min_severity = min_severity
        self.auth_header = auth_header
        self._session = session
        self._owns_session = session is None

    def send_alert(self, result: ReconcileResult) -> None:
        if result.mismatch_count < self.min_severity:
            return
        payload = result.to_dict()
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "nanobot-billing-reconciler/1.0",
            "X-Reconcile-Run-Id": result.run_id,
            "X-Reconcile-Provider": result.provider,
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        try:
            sess = self._session or _lazy_requests_session()
            resp = sess.post(self.webhook_url, data=body, headers=headers,
                             timeout=self.timeout_s)
            # 2xx is success; 4xx/5xx we consider transient and raise
            if not (200 <= resp.status_code < 300):
                raise RuntimeError(
                    f"webhook responded {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:  # noqa: BLE001 — we want to log+continue
            logger.warning(
                "reconcile webhook failed: provider=%s run_id=%s err=%s",
                result.provider, result.run_id, e,
            )
            raise

    def __repr__(self) -> str:
        return f"WebhookAlertHook(url={self.webhook_url!r})"


class LoggingAlertHook:
    """Logs the result at WARNING level (if mismatches) or INFO (clean run).
    Always a no-op alert — for local observability / smoke tests."""
    LOG_PREFIX = "billing.reconcile.alert"

    def send_alert(self, result: ReconcileResult) -> None:
        if result.has_mismatches:
            logger.warning(
                "%s MISMATCH provider=%s date=%s count=%d delta=%d",
                self.LOG_PREFIX, result.provider, result.date,
                result.mismatch_count, result.total_delta_cents,
            )
        else:
            logger.info(
                "%s CLEAN provider=%s date=%s matched=%d",
                self.LOG_PREFIX, result.provider, result.date, result.matched_count,
            )


class MultiAlertHook:
    """Fan-out to multiple hooks. Each hook is called independently; if one
    fails, others still run."""
    def __init__(self, hooks: List[ReconcileAlertHook]) -> None:
        self.hooks = list(hooks)

    def send_alert(self, result: ReconcileResult) -> None:
        for h in self.hooks:
            try:
                h.send_alert(result)
            except Exception as e:  # noqa: BLE001
                logger.warning("alert hook %r failed: %s", h, e)


class NoopAlertHook:
    """Default alert hook — silent. Override with WebhookAlertHook in prod."""
    def send_alert(self, result: ReconcileResult) -> None:  # noqa: ARG002
        return None


# ============================================================================
# 4. Reconciliation engine
# ============================================================================

class OrderSource(Protocol):
    """Anything that can return a list of orders.

    OrderService satisfies this (via ``list_all``); a raw ``InMemoryOrderStore``
    also satisfies it (via ``list``). The engine accepts either.
    """
    def list(self, user_id: Optional[str] = None,
             status: Optional[OrderStatus] = None,
             limit: int = 100) -> List[Order]: ...


class ReconciliationEngine:
    """Compares local orders with provider-side transactions.

    Usage:
        engine = ReconciliationEngine(
            order_service=svc,
            adapters={"stripe": MockProviderAdapter("stripe"), ...},
            alert_hook=WebhookAlertHook("https://hooks.example.com/billing"),
        )
        result = engine.run(provider="stripe", date=date(2026, 6, 24))

    The engine is stateless; calling run() multiple times is safe and produces
    fresh results (each with a unique run_id).
    """

    def __init__(self, order_source: Any,
                 adapters: Dict[str, ProviderAdapter],
                 alert_hook: Optional[ReconcileAlertHook] = None) -> None:
        """Args:
            order_source:  either an ``OrderService`` (preferred) or any
                           duck-typed object exposing ``list(...)`` returning
                           ``List[Order]`` (e.g. ``InMemoryOrderStore``).
            adapters:      dict mapping provider name → ProviderAdapter
            alert_hook:    optional alert hook (defaults to NoopAlertHook)
        """
        self.order_source: Any = order_source
        self.adapters = dict(adapters)
        self.alert_hook = alert_hook or NoopAlertHook()

    @property
    def order_service(self) -> Any:
        """Backward-compat alias for the underlying order source."""
        return self.order_source

    def register_adapter(self, adapter: ProviderAdapter) -> None:
        self.adapters[adapter.provider_name] = adapter

    def run(self, provider: str,
            date: Optional[Union[str, _date]] = None,
            order_statuses: Optional[List[OrderStatus]] = None,
            include_payment_methods: Optional[List[str]] = None) -> ReconcileResult:
        """Run reconciliation for one provider on one date.

        Args:
            provider: name registered in self.adapters
            date:     target date (UTC). Default = yesterday
            order_statuses: which local order statuses to include. Default =
                            [PAID, FULFILLED, REFUNDED]
            include_payment_methods: optional list of payment_method values to
                            include in the local scan. Default = [provider] only
                            (each provider reconciles its own orders).
        """
        if provider not in self.adapters:
            raise KeyError(
                f"no adapter registered for provider {provider!r}. "
                f"available: {list(self.adapters.keys())}"
            )
        target_date = _normalize_date(date) if date is not None else _yesterday_utc()
        statuses = order_statuses or [
            OrderStatus.PAID, OrderStatus.FULFILLED, OrderStatus.REFUNDED,
        ]
        payment_methods = include_payment_methods or [provider]
        run_id = f"recon_{uuid.uuid4().hex[:16]}"
        started_at = _utcnow_iso()
        t0 = time.monotonic()

        result = ReconcileResult(
            run_id=run_id,
            provider=provider,
            date=target_date,
            started_at=started_at,
            finished_at=started_at,
        )

        try:
            # 1. Fetch local orders (filtered by status + payment_method + date)
            local_orders = self._fetch_local_orders(
                target_date, statuses, payment_methods=payment_methods,
            )
            local_by_id = {o.order_id: o for o in local_orders}
            result.local_count = len(local_by_id)

            # 2. Fetch remote transactions
            adapter = self.adapters[provider]
            try:
                remote_txns = adapter.fetch_transactions(target_date)
            except ProviderReconciliationError as e:
                result.error = f"provider fetch failed: {e}"
                result.finished_at = _utcnow_iso()
                result.duration_ms = int((time.monotonic() - t0) * 1000)
                logger.error("reconcile provider fetch failed: %s", e)
                return result
            remote_by_id: Dict[str, NormalizedTxn] = {}
            for t in remote_txns:
                # Same order_id may appear twice (charge + refund) — we keep
                # the most recent.
                remote_by_id.setdefault(t.order_id, t)
            result.remote_count = len(remote_by_id)

            # 3. Build totals (local net + remote net for sanity check)
            result.total_local_amount_cents = sum(
                max(0, _order_net_cents(o)) for o in local_orders
            )
            result.total_remote_amount_cents = sum(
                max(0, t.amount_cents) for t in remote_by_id.values()
            )

            # 4. Diff
            mismatches: List[ReconcileMismatch] = []
            all_ids = set(local_by_id.keys()) | set(remote_by_id.keys())
            for oid in sorted(all_ids):
                local = local_by_id.get(oid)
                remote = remote_by_id.get(oid)
                if local is not None and remote is None:
                    mismatches.append(ReconcileMismatch(
                        mismatch_type=MismatchType.MISSING_REMOTE,
                        order_id=oid,
                        provider=provider,
                        description="local order exists but provider has no record",
                        expected=_order_summary(local),
                        actual=None,
                    ))
                    continue
                if local is None and remote is not None:
                    mismatches.append(ReconcileMismatch(
                        mismatch_type=MismatchType.MISSING_LOCAL,
                        order_id=oid,
                        provider=provider,
                        description="provider has order but local record missing",
                        expected=None,
                        actual=_txn_summary(remote),
                    ))
                    continue
                # Both sides present — compare
                assert local is not None and remote is not None
                local_net = _order_net_cents(local)
                remote_net = remote.net_amount_cents
                if local.currency.upper() != remote.currency.upper():
                    mismatches.append(ReconcileMismatch(
                        mismatch_type=MismatchType.CURRENCY_MISMATCH,
                        order_id=oid,
                        provider=provider,
                        description=(
                            f"currency differs: local={local.currency} "
                            f"remote={remote.currency}"
                        ),
                        expected=local.currency,
                        actual=remote.currency,
                    ))
                # Status mapping: local REFUNDED vs remote status 'refunded'
                local_status = _map_local_status(local.status)
                if local_status != remote.status.lower():
                    mismatches.append(ReconcileMismatch(
                        mismatch_type=MismatchType.STATUS_MISMATCH,
                        order_id=oid,
                        provider=provider,
                        description=(
                            f"status differs: local={local_status} "
                            f"remote={remote.status}"
                        ),
                        expected=local_status,
                        actual=remote.status,
                    ))
                if local_net != remote_net:
                    delta = local_net - remote_net
                    if local.refunded_amount_cents != remote.refunded_amount_cents:
                        mismatches.append(ReconcileMismatch(
                            mismatch_type=MismatchType.REFUND_MISMATCH,
                            order_id=oid,
                            provider=provider,
                            description=(
                                f"refund amount differs: local="
                                f"{local.refunded_amount_cents} "
                                f"remote={remote.refunded_amount_cents}"
                            ),
                            expected=local.refunded_amount_cents,
                            actual=remote.refunded_amount_cents,
                            delta_cents=delta,
                        ))
                    else:
                        mismatches.append(ReconcileMismatch(
                            mismatch_type=MismatchType.AMOUNT_MISMATCH,
                            order_id=oid,
                            provider=provider,
                            description=(
                                f"net amount differs: local={local_net} "
                                f"remote={remote_net}"
                            ),
                            expected=local_net,
                            actual=remote_net,
                            delta_cents=delta,
                        ))
            result.mismatches = mismatches
            result.mismatch_count = len(mismatches)
            # matched_count = unique order_ids that reconciled cleanly.
            # Each order_id contributes 1 to matched if no mismatch on it.
            matched_ids = (
                (set(local_by_id.keys()) & set(remote_by_id.keys()))
                - {m.order_id for m in mismatches}
            )
            result.matched_count = len(matched_ids)
            if result.matched_count < 0:
                result.matched_count = 0
            result.total_delta_cents = sum(m.delta_cents for m in mismatches)

            # 5. Fire alert hook if mismatches
            if result.has_mismatches or _always_alert(self.alert_hook):
                try:
                    self.alert_hook.send_alert(result)
                    result.alert_sent = True
                except Exception as e:  # noqa: BLE001
                    result.alert_error = str(e)
                    logger.warning(
                        "alert hook failed: provider=%s run_id=%s err=%s",
                        provider, run_id, e,
                    )
        except Exception as e:  # noqa: BLE001
            result.error = f"reconcile crashed: {e}"
            logger.exception("reconcile crashed: provider=%s date=%s", provider, target_date)

        result.finished_at = _utcnow_iso()
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    # ── private ─────────────────────────────────────────────────────────
    def _fetch_local_orders(self, date_str: str,
                            statuses: List[OrderStatus],
                            payment_methods: Optional[List[str]] = None) -> List[Order]:
        # Build aware-UTC day boundaries (handles ISO with `Z`, `+00:00`, or naive)
        try:
            day_start = _parse_iso(date_str + "T00:00:00+00:00")
        except ValueError:
            day_start = _parse_iso(date_str)
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        out: List[Order] = []
        # Pull generously then filter (no native index — list scans)
        candidates = self._list_orders(limit=10000)
        pm_filter = set(payment_methods) if payment_methods else None
        for o in candidates:
            if o.status not in statuses:
                continue
            if pm_filter is not None and o.payment_method not in pm_filter:
                continue
            ts = o.paid_at or o.created_at
            if not ts:
                continue
            try:
                t = _parse_iso(ts)
            except ValueError:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if day_start <= t < day_end:
                out.append(o)
        return out

    def _list_orders(self, limit: int = 10000) -> List[Order]:
        """Call the right method on the underlying order source.

        OrderService has ``list_all`` + ``list_for_user``; raw stores only
        have ``list``. We try both.
        """
        src = self.order_source
        # OrderService-style: has list_all
        if hasattr(src, "list_all"):
            return src.list_all(limit=limit)  # type: ignore[attr-defined]
        # Raw store: has list(user_id, status, limit)
        if hasattr(src, "list"):
            return src.list(limit=limit)  # type: ignore[attr-defined]
        raise TypeError(
            f"order_source must expose list() or list_all(), got {type(src).__name__}"
        )


# ============================================================================
# 5. Module-level convenience
# ============================================================================

_DEFAULT_ENGINE: Optional[ReconciliationEngine] = None
_DEFAULT_LOCK = threading.Lock()


def daily_reconcile(provider: str,
                    date: Optional[Union[str, _date]] = None,
                    order_service: Optional[Any] = None,
                    adapters: Optional[Dict[str, ProviderAdapter]] = None,
                    alert_hook: Optional[ReconcileAlertHook] = None,
                    order_statuses: Optional[List[OrderStatus]] = None) -> ReconcileResult:
    """Module-level convenience for running one daily reconciliation.

    If you have not constructed an engine, pass ``order_service`` + ``adapters``
    + ``alert_hook`` (or use ``get_default_engine`` to set up once).

    Args:
        provider:        "stripe" / "alipay" / "wechat" / "mock"
        date:            target date (default = yesterday UTC)
        order_service:   OrderService instance OR any object with ``list()``
                          returning ``List[Order]`` (e.g. InMemoryOrderStore)
        adapters:        dict of provider name → adapter
        alert_hook:      optional alert hook (overrides engine's hook if engine set)
        order_statuses:  override default [PAID, FULFILLED, REFUNDED]

    Returns:
        ReconcileResult (always — never raises for normal failures)
    """
    engine: Optional[ReconciliationEngine] = None
    if order_service is not None and adapters is not None:
        engine = ReconciliationEngine(
            order_source=order_service,
            adapters=adapters,
            alert_hook=alert_hook or NoopAlertHook(),
        )
    else:
        engine = get_default_engine()
        if engine is None:
            raise RuntimeError(
                "daily_reconcile: must provide order_service+adapters or "
                "call set_default_engine() first"
            )

    if alert_hook is not None:
        engine.alert_hook = alert_hook

    return engine.run(
        provider=provider,
        date=date,
        order_statuses=order_statuses,
    )


def get_default_engine() -> Optional[ReconciliationEngine]:
    return _DEFAULT_ENGINE


def set_default_engine(engine: Optional[ReconciliationEngine]) -> None:
    global _DEFAULT_ENGINE
    with _DEFAULT_LOCK:
        _DEFAULT_ENGINE = engine


def reset_default_engine() -> None:
    set_default_engine(None)


# ============================================================================
# 6. Helpers
# ============================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _yesterday_utc() -> str:
    d = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    return d.isoformat()


def _normalize_date(date: Union[str, _date, datetime]) -> str:
    if isinstance(date, _date) and not isinstance(date, datetime):
        return date.isoformat()
    if isinstance(date, datetime):
        return date.date().isoformat()
    if isinstance(date, str):
        return date[:10]  # accept full ISO, return YYYY-MM-DD
    raise TypeError(f"unsupported date type: {type(date).__name__}")


def _parse_iso(s: str) -> datetime:
    """Parse ISO8601 string. Accepts trailing 'Z'."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _order_net_cents(o: Order) -> int:
    """Net amount the merchant kept for this order (charge - refund)."""
    return int(o.amount_cents) - int(getattr(o, "refunded_amount_cents", 0) or 0)


def _map_local_status(s: OrderStatus) -> str:
    if s == OrderStatus.REFUNDED:
        return "refunded"
    if s in (OrderStatus.PAID, OrderStatus.FULFILLED):
        return "paid"
    if s == OrderStatus.PENDING:
        return "pending"
    if s in (OrderStatus.FAILED, OrderStatus.CANCELLED):
        return s.value
    return s.value


def _order_summary(o: Order) -> Dict[str, Any]:
    return {
        "order_id": o.order_id,
        "amount_cents": o.amount_cents,
        "currency": o.currency,
        "status": o.status.value,
        "refunded_amount_cents": getattr(o, "refunded_amount_cents", 0),
        "payment_method": o.payment_method,
        "external_ref": o.external_ref,
    }


def _txn_summary(t: NormalizedTxn) -> Dict[str, Any]:
    return {
        "order_id": t.order_id,
        "provider_txn_id": t.provider_txn_id,
        "amount_cents": t.amount_cents,
        "currency": t.currency,
        "status": t.status,
        "refunded_amount_cents": t.refunded_amount_cents,
    }


def _always_alert(_hook: Any) -> bool:
    """Marker — subclasses may override; default is mismatch-only."""
    return False


def _lazy_requests_session() -> Any:
    """Lazy-import requests (keeps reconciliation importable without it)."""
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "requests library required for WebhookAlertHook; "
            "pip install requests"
        ) from e
    sess = requests.Session()
    return sess


# ============================================================================
# 7. Webhook DDL (reconcile audit table for postgres + sqlite)
# ============================================================================

RECONCILE_RUNS_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS billing_reconcile_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    date VARCHAR(10) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_ms INTEGER DEFAULT 0,
    local_count INTEGER DEFAULT 0,
    remote_count INTEGER DEFAULT 0,
    matched_count INTEGER DEFAULT 0,
    mismatch_count INTEGER DEFAULT 0,
    total_local_amount_cents BIGINT DEFAULT 0,
    total_remote_amount_cents BIGINT DEFAULT 0,
    total_delta_cents BIGINT DEFAULT 0,
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_error TEXT DEFAULT '',
    error TEXT DEFAULT '',
    mismatches JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

RECONCILE_RUNS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS billing_reconcile_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    date VARCHAR(10) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_ms INTEGER DEFAULT 0,
    local_count INTEGER DEFAULT 0,
    remote_count INTEGER DEFAULT 0,
    matched_count INTEGER DEFAULT 0,
    mismatch_count INTEGER DEFAULT 0,
    total_local_amount_cents INTEGER DEFAULT 0,
    total_remote_amount_cents INTEGER DEFAULT 0,
    total_delta_cents INTEGER DEFAULT 0,
    alert_sent BOOLEAN DEFAULT 0,
    alert_error TEXT DEFAULT '',
    error TEXT DEFAULT '',
    mismatches TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

RECONCILE_RUNS_INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_billing_reconcile_runs_provider ON billing_reconcile_runs(provider);",
    "CREATE INDEX IF NOT EXISTS ix_billing_reconcile_runs_date ON billing_reconcile_runs(date);",
    "CREATE INDEX IF NOT EXISTS ix_billing_reconcile_runs_provider_date ON billing_reconcile_runs(provider, date);",
    "CREATE INDEX IF NOT EXISTS ix_billing_reconcile_runs_mismatch ON billing_reconcile_runs(mismatch_count);",
]


__all__ = [
    # enums
    "MismatchType",
    # dataclasses
    "NormalizedTxn", "ReconcileMismatch", "ReconcileResult",
    # adapter
    "ProviderAdapter", "ProviderReconciliationError", "MockProviderAdapter",
    # hooks
    "ReconcileAlertHook", "WebhookAlertHook", "LoggingAlertHook",
    "MultiAlertHook", "NoopAlertHook",
    # engine
    "ReconciliationEngine", "daily_reconcile",
    "get_default_engine", "set_default_engine", "reset_default_engine",
    # DDL
    "RECONCILE_RUNS_DDL_POSTGRES", "RECONCILE_RUNS_DDL_SQLITE",
    "RECONCILE_RUNS_INDEXES_DDL",
]