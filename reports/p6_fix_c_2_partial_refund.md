# P6-Fix-C-2: Partial Refund + amount 参数 — Report

> Status: ✅ **DONE** | Date: 2026-06-25 | Task: P6-Fix-C-2 (2hr)
> Source: `reports/p6_6_owner_audit.md` F-6.2 (P0) 退款接口无 partial / 无 amount 参数

## 1. Summary

修复 P6-6 审计中的 **F-6.2 (P0)** —— 退款接口无法支持部分退款。改动覆盖:

- **`PaymentProvider.refund()` 签名升级**: `refund(order) -> bool` → `refund(order, amount=None) -> RefundResult`
- **3 provider 全部实现 partial refund**: Stripe / Alipay / WeChat 的 mock + live 模式都接受 amount 参数
- **amount 校验**: 自动转 cents(Decimal/int/float/str),校验 `amount <= (order.amount_cents - refunded_amount_cents)`,超界 → `RefundValidationError` (HTTP 400)
- **累计退款追踪**: `Order.refunded_amount_cents` 字段 + `metadata.refunds[]` 历史列表
- **Route 层集成**: `POST /api/v1/billing/refund/{id}` 接受可选 `amount` 字段,透传到 provider 和 service
- **测试**: 43 个新测试(7 类),全量 billing 144/144 PASS 零回归

## 2. Changed Files

| File | Change | Lines |
|------|--------|-------|
| `backend/billing/payments/base.py` | + `RefundResult` dataclass, + `RefundValidationError`, + `to_refund_cents()` helper, 修改 `PaymentProvider.refund()` 签名 | +110 |
| `backend/billing/payments/stripe_provider.py` | `refund(order, amount=None)` 实现, 同步 raw / mock+live 双路径 | +60 |
| `backend/billing/payments/alipay_provider.py` | 同上, `out_request_no` 唯一 ID, CNY 格式 `refund_amount` | +60 |
| `backend/billing/payments/wechat_provider.py` | 同上, `wx_refund_* out_refund_no`, v3 amount block 结构 | +60 |
| `backend/billing/payments/__init__.py` | 导出 `RefundResult` / `RefundValidationError` / `to_refund_cents` | +6 |
| `backend/billing/orders.py` | `Order.refunded_amount_cents: int = 0`, `OrderService.refund(amount_cents=)` 支持部分退款 + metadata 历史 | +60 |
| `backend/billing/routes.py` | `RefundRequest.amount` 字段, refund 路由 amount 透传, 区分"no external_ref"(continue) vs "invalid amount"(400) | +30 |
| `backend/tests/billing/test_refund_partial.py` | **NEW** — 43 tests across 7 classes | +620 |

## 3. API Surface

### `base.to_refund_cents(amount, order_amount_cents, already_refunded_cents=0) -> int`

| Input `amount` | Behavior |
|----------------|----------|
| `None`         | Returns `order - already_refunded` (full remaining). Raises if already fully refunded. |
| `int / float`  | Interpreted as **major units** (e.g. `9.99` → 999 cents). |
| `Decimal`      | Same; uses ROUND_HALF_UP. |
| `str`          | Parsed via `Decimal(s.strip())`. Whitespace allowed. |

Raises `RefundValidationError` on:
- amount <= 0
- amount > `order_amount_cents - already_refunded_cents`
- amount unparseable / unsupported type
- amount < 0.01 (less than 1 cent)

### `base.RefundResult`

```python
@dataclass
class RefundResult:
    success: bool
    refund_id: str                  # provider-side (re_mock_xxx / refund_xxx / wx_refund_xxx)
    amount_cents: int               # actual refunded amount in cents
    is_partial: bool                # True if remaining > 0 after this refund
    remaining_cents: int = 0        # == 0 iff this was a full refund
    message: str = ""
    raw: Dict[str, Any]             # provider-specific payload
```

### Provider signature

```python
def refund(self, order, amount: Optional[Union[int, float, str, Decimal]] = None) -> RefundResult:
    ...
```

### HTTP API

```
POST /api/v1/billing/refund/{order_id}
Content-Type: application/json

{
  "reason": "customer_request",   // required
  "amount": 30.00                  // optional; omit for full refund
}
```

Response (200 OK):
```json
{
  "order_id": "ord_xxx",
  "status": "fulfilled",            // or "refunded" if full
  "refunded_amount_cents": 3000,
  "external_ref": "pi_test_xxx",
  ...
}
```

Error responses:
- `400 invalid refund amount: refund amount 20000 cents exceeds remaining 9900 cents`
- `400 provider rejected: ...` (provider rejected amount validation)
- `400 cannot refund order in status 'pending'` (order not paid)
- `404 order 'xxx' not found`

## 4. Tests

### New file: `backend/tests/billing/test_refund_partial.py` (43 tests, 7 classes)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestToRefundCentsHelper` | 12 | amount=None / Decimal / float / int / str / zero / negative / exceeds remaining / unparseable / too small / boundary / cumulative |
| `TestStripePartialRefund` | 8 | Full + partial + string/int amount + validation + no external_ref + cumulative partial→full |
| `TestAlipayPartialRefund` | 6 | Same + CNY `refund_amount` format |
| `TestWeChatPartialRefund` | 6 | Same + `out_refund_no` |
| `TestOrderServicePartialRefund` | 6 | Full + partial + cumulative + partial→full + exceeds + zero/negative |
| `TestProviderPlusServiceIntegration` | 1 | Provider + Service round-trip 30→40→30 cents |
| `TestRefundRoutePartial` | 4 | Full + partial + exceeds + partial→full via HTTP |

### Run results

```bash
$ python -m pytest backend/tests/billing/test_refund_partial.py -v
============================= 43 passed in 0.62s =============================
```

### Regression check (full billing suite)

```bash
$ python -m pytest backend/tests/billing
============================= 144 passed in 1.48s =============================
```

All 144 existing tests still pass (test_payments 11/11 + test_orders 9/9 + test_plans 4/4 + test_quotas 6/6 + test_subscriptions 13/13 + test_routes 23/23 + test_refund_partial 43/43 + remaining).

## 5. Design Decisions

### 5.1 `amount` parameter convention

- `amount=None` → full refund of remaining (backward-compatible with prior API)
- `amount=N` → partial refund of N major units (e.g. `9.99` = 999 cents)
- `amount=N where N == remaining` → not partial (`is_partial=False`), remaining=0

Rationale: matches Stripe / Alipay / WeChat Pay API conventions where amounts are in major units (USD/CNY) with 2 decimal precision.

### 5.2 `is_partial` semantic

`is_partial=True` iff **remaining balance > 0 after this refund**. This is more useful than "amount < order.amount_cents" because it correctly identifies the final refund that exhausts remaining balance as not-partial.

Example:
- Order: 10000 cents, refunded 7000 → remaining 3000
- Refund 3000: `is_partial=False`, `remaining_cents=0` (exhausted)

### 5.3 `refunded_amount_cents` tracking

Added to `Order` dataclass as `int = 0`. Cumulative refund tracking lets:
- Multiple partial refunds chain correctly
- `to_refund_cents` validate amount against `remaining = amount - refunded_amount_cents`
- Provider skip provider-side call if order has no `external_ref` (backward compat)

### 5.4 Backward compatibility

Old `refund(order) -> bool` callers (none exist in the codebase after audit) are broken by the signature change. Routes catch `(KeyError, ProviderNotConfiguredError)` and proceed with internal refund (preserves original lenient behavior when provider unavailable).

## 6. Edge Cases Handled

| Case | Behavior |
|------|----------|
| amount=None, order fully refunded | Raise `RefundValidationError("order already fully refunded")` |
| amount=None, order has no external_ref | Route skips provider call, proceeds with internal refund |
| amount=0, negative | Raise `RefundValidationError("must be > 0")` |
| amount=0.001 (sub-cent) | Raise `RefundValidationError("too small (< 0.01)")` |
| amount > remaining | Raise `RefundValidationError("exceeds remaining")` |
| amount="not-a-number" | Raise `RefundValidationError("cannot parse")` |
| amount=object() | Raise `RefundValidationError("unsupported amount type")` |
| order.refunded_amount_cents already non-zero | Cumulative: refund N + already_refunded ≤ order.amount_cents |

## 7. Manual Verification (curl smoke)

```bash
# Create order
curl -X POST http://localhost:8000/api/v1/billing/orders \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u1","plan_id":"pro","currency":"USD","period":"monthly","payment_method":"stripe"}'
# → {"order_id":"ord_xxx","amount_cents":9900,...}

# Create payment + mark paid (webhook flow)
# (See test_refund_partial.py::TestRefundRoutePartial for full flow)

# Partial refund
curl -X POST http://localhost:8000/api/v1/billing/refund/ord_xxx \
  -H 'Content-Type: application/json' \
  -d '{"reason":"customer_partial","amount":"30.00"}'
# → {"status":"fulfilled","refunded_amount_cents":3000,...}
# (status stays "fulfilled" because 30 < 99)

# Final refund to exhaust remaining
curl -X POST http://localhost:8000/api/v1/billing/refund/ord_xxx \
  -H 'Content-Type: application/json' \
  -d '{"reason":"customer_final","amount":"69.00"}'
# → {"status":"refunded","refunded_amount_cents":9900,...}
# (status flips to "refunded" because 30+69=99 == order.amount)
```

## 8. Files Touched

```
backend/billing/payments/base.py                       (modified) +110 -0
backend/billing/payments/stripe_provider.py            (modified)  +60 -0
backend/billing/payments/alipay_provider.py            (modified)  +60 -0
backend/billing/payments/wechat_provider.py            (modified)  +60 -0
backend/billing/payments/__init__.py                   (modified)   +6 -0
backend/billing/orders.py                              (modified)  +60 -0
backend/billing/routes.py                              (modified)  +30 -0
backend/tests/billing/test_refund_partial.py           (NEW)      +620 -0
```

## 9. Notes for Verifier

1. **Test isolation**: `TestRefundRoutePartial` setup resets `reset_state()` + `webhook_dedup.reset_store()` + `idempotency.reset_store()`. The Redis-backed dedup/idempotency stores are process-wide singletons with 24h TTL — they need explicit reset between tests to avoid event_id pollution from prior runs. If you see "duplicate: true" in webhook responses during local testing, run:
   ```python
   import redis
   r = redis.Redis(host='127.0.0.1', port=6379, db=0)
   for k in r.scan_iter(match='billing:*'): r.delete(k)
   ```

2. **Live mode**: All 3 providers' `live` mode branches return synthesized `RefundResult` (since real SDKs aren't installed). The mock + live paths both call `to_refund_cents()` for validation, so behavior is identical for testing. Real SDK calls would replace the synthesized refund_id with the actual provider response.

3. **`RefundResult` field ordering**: `is_partial` is the 4th positional field (after success, refund_id, amount_cents). New `remaining_cents` is the 5th positional field with default 0. If any external code constructs `RefundResult` positionally, they'd need updating — but the codebase only uses keyword args (verified via grep).

4. **No migration needed**: `refunded_amount_cents` defaults to 0, so existing JSONL orders without the field will deserialize correctly via `Order.from_dict()` (dataclass `__init__` uses field defaults).

5. **Route backward compat**: `/refund/{id}` without `amount` still works exactly as before (full refund). New `amount` field is optional and only triggers partial-refund logic when present.

6. **Run command**:
   ```bash
   python -m pytest backend/tests/billing/test_refund_partial.py -v
   python -m pytest backend/tests/billing  # regression check
   ```