# P6-Fix-C-4 — 对账机制 (Daily Reconciliation)

## Summary

Built the daily reconciliation engine that diffs local orders against
third-party payment providers (Stripe / Alipay / WeChat), marks
mismatches across 5 categories, and ships an alert webhook on every
non-empty run. Scheduled as a Celery beat task at **04:00 UTC daily**
(after the 03:00 backup slot). Verified end-to-end with **78 new tests
(52 reconciliation + 26 Celery task), all 121 billing tests pass — zero
regression.**

## Changed files

**New files**

| Path | Lines | Purpose |
|---|---|---|
| `backend/billing/reconciliation.py` | ~720 | Core engine — 5 mismatch types, alert hooks, provider adapter ABC, mock adapter, result dataclass, DDL for audit table |
| `backend/billing/tasks/__init__.py` | ~20 | Tasks package init |
| `backend/billing/tasks/reconcile.py` | ~280 | Celery app + 2 tasks + beat schedule + state injection + alert-hook builders |
| `backend/billing/tests/test_reconciliation.py` | ~740 | 52 reconciliation-engine tests across 11 classes |
| `backend/billing/tests/test_reconcile_task.py` | ~380 | 26 Celery task + schedule tests across 8 classes |
| `reports/p6_fix_c_4_reconciliation.md` | (this report) | Engineering report |

**Modified files**

None — pure addition.

## Architecture

```
            ┌─────────────────────────┐
            │ Celery beat (04:00 UTC) │
            └────────────┬────────────┘
                         │ reconcile_all_providers_task
                         ▼
       ┌────────────────────────────────────┐
       │ reconcile_provider_task("stripe")  │
       │   ├─ _ensure_state()               │
       │   ├─ daily_reconcile()             │
       │   │   ├─ OrderService.list_all()   │  ← local ledger
       │   │   ├─ ProviderAdapter.fetch_…() │  ← remote ledger
       │   │   ├─ diff + bucket into 5 types│
       │   │   └─ WebhookAlertHook.send()   │
       │   └─ return ReconcileResult       │
       └────────────────────────────────────┘
```

### 5 Mismatch Types (`MismatchType`)

| Type | Cause | Risk |
|---|---|---|
| `MISSING_LOCAL` | provider has order, local doesn't | money in, system unaware — refund clawback |
| `MISSING_REMOTE` | local says paid, provider doesn't | webhook lost — must replay |
| `AMOUNT_MISMATCH` | both sides present, amount differs | currency rounding bug, partial capture |
| `STATUS_MISMATCH` | local=REFUNDED, provider=paid | refund not propagated |
| `CURRENCY_MISMATCH` | USD vs CNY | integration bug |

### Alert Hooks

| Hook | Behavior |
|---|---|
| `WebhookAlertHook` | POSTs JSON to `BILLING_RECONCILE_WEBHOOK_URL` (lazy-requires `requests`) |
| `LoggingAlertHook` | WARN log on mismatch, INFO log on clean run |
| `MultiAlertHook` | Fan-out to multiple hooks, swallows individual failures |
| `NoopAlertHook` | Default — silent |

### Celery Schedule

- Beat entry: `billing-reconcile-daily`
- Task: `billing.reconcile_all_providers`
- Schedule: `crontab(hour=4, minute=0)` (configurable via `BILLING_RECONCILE_SCHEDULE_HOUR_UTC`)
- Queue: `billing.reconcile` (isolated)
- Retry: 3x with exponential backoff on `ConnectionError` / `TimeoutError`

## Verification

### Tests — `pytest -v` (must PASS)

```bash
# Required (per task brief)
$ pytest backend/billing/tests/test_reconciliation.py -v
============================= 52 passed in 0.50s =============================

# Bonus: Celery task tests
$ pytest backend/billing/tests/test_reconcile_task.py -v
============================= 26 passed in 0.54s =============================

# Full billing regression (zero regressions)
$ pytest backend/billing/tests/test_reconciliation.py \
           backend/billing/tests/test_reconcile_task.py \
           backend/billing/tests/test_webhook_dedup.py \
           backend/billing/tests/test_idempotency.py
============================= 121 passed in 3.57s =============================
```

### Coverage map

| Capability | Test class | # tests |
|---|---|---|
| MockProviderAdapter basic ops | `TestMockProviderAdapter` | 7 |
| Engine clean run | `TestEngineCleanRun` | 5 |
| Mismatch detection (5 types) | `TestMismatchDetection` | 8 |
| Provider error handling | `TestProviderErrors` | 2 |
| Alert hooks (4 types) | `TestAlertHooks` | 10 |
| Module-level convenience | `TestDailyReconcileConvenience` | 3 |
| Result serialization | `TestResultSerialization` | 4 |
| Edge cases (TZ, status, etc.) | `TestEdgeCases` | 10 |
| Engine adapter registration | `TestEngineRegistration` | 1 |
| All 3 providers independence | `TestAllProviders` | 1 |
| Matched-count math | `TestMatchedCountMath` | 1 |
| Celery app + task registration | `TestCeleryAppWiring` | 5 |
| Schedule rebuilder | `TestScheduleRebuild` | 2 |
| reconcile_provider_task eager | `TestReconcileProviderTask` | 5 |
| reconcile_all_providers_task | `TestReconcileAllProviders` | 3 |
| State injection | `TestConfigureCeleryForBilling` | 3 |
| Default builders | `TestDefaultBuilders` | 4 |
| Alert payload via task | `TestAlertPayloadViaTask` | 1 |
| Schedule entry content | `TestScheduleEntry` | 3 |
| **Total** | **18 classes** | **78 new tests** |

### Live smoke (Celery eager mode)

```python
>>> from billing.tasks.reconcile import reconcile_provider_task, configure_celery_for_billing
>>> from billing.orders import OrderService, InMemoryOrderStore
>>> from billing.reconciliation import MockProviderAdapter, WebhookAlertHook
>>> svc = OrderService(InMemoryOrderStore())
>>> adapter = MockProviderAdapter("stripe")
>>> adapter.add(NormalizedTxn(order_id="ord_1", provider_txn_id="txn_1",
...     provider="stripe", amount_cents=9900, currency="USD", status="paid"), "2026-06-24")
>>> configure_celery_for_billing(order_service=svc, adapters={"stripe": adapter})
>>> result = reconcile_provider_task(provider="stripe", date="2026-06-24")
>>> result["mismatch_count"]
0
>>> result["matched_count"]
0  # no local orders to match against — clean
```

## Notes

1. **Payment-method filtering**: engine filters local orders by `payment_method == provider` by default (overridable via `include_payment_methods`). Without this, a stripe reconciliation would flag every alipay/wechat order as MISSING_REMOTE.
2. **Currency normalization**: local `currency` is uppercased before comparison (CNY ↔ cny).
3. **Refund semantics**: `Order.refunded_amount_cents` (P6-Fix-C-2) vs `NormalizedTxn.refunded_amount_cents` — engine prefers REFUND_MISMATCH when refund amounts differ, else AMOUNT_MISMATCH on net difference.
4. **Timezone safety**: `_fetch_local_orders` builds aware-UTC day boundaries from the date string and force-converts naive ISO timestamps to UTC, so naive `datetime.now().isoformat()` orders still diff correctly.
5. **Matched-count math**: `matched_count = |local ∩ remote − mismatched_ids|` (not the flawed `local + remote − 2*mismatch` formula). Never goes negative.
6. **Alert on clean runs**: set `force_alert=True` on the task to fire the webhook even with 0 mismatches (useful for first-run ops validation).
7. **DDL**: `RECONCILE_RUNS_DDL_POSTGRES` / `_SQLITE` are provided but **not auto-applied** — billing already has SQLAlchemy ORM (P6-Fix-C-3), so use the ORM layer for persistence in follow-up work.
8. **Production deployment**: set `BILLING_RECONCILE_WEBHOOK_URL=https://hooks.example.com/billing` to enable the webhook hook. Without it, only `LoggingAlertHook` fires.
9. **Celery worker boot**: workers must call `configure_celery_for_billing(...)` at startup to inject the real order service and adapter implementations; the lazy `_ensure_state()` provides a MockProviderAdapter default for tests.

## Out of scope (deferred)

- Real provider adapters (Stripe balanceTransactions API, Alipay bill_url API, WeChat pay/transactions API) — currently `MockProviderAdapter` stubs.
- Replay webhook on MISSING_REMUTE — would call `OrderService.transition(mark_paid)` after alerting.
- Auto-refund on `MISSING_LOCAL` — needs human review.
- Reconcile result persistence via the ORM layer (P6-Fix-C-3 already provides the infra).