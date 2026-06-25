# P6-Fix-C-1: 支付 Idempotency + Webhook 重放保护

> Task ID: **P6-Fix-C-1**
> Worker: coder (mvs_1fec76fce7024f769a010ccdd0a67058)
> Parent: mvs_8ecc804a9afa42dc8e79427bfcff5828
> Date: 2026-06-25
> Status: **DONE — 54/54 tests PASS**

---

## 1. 摘要

为支付链路加上 **Stripe 风格 Idempotency-Key** 与 **Webhook Event-ID 去重** 双重保护,
确保重复的 `create_payment` 请求不会重复扣费、重复的 webhook 投递不会重复触发业务逻辑。
3 个支付 provider (Stripe / Alipay / WeChat) 全部接通,共写 **43 个新测试** 并保留全部 **11 个原 payment 测试** 通过。

---

## 2. 硬启动检查 (v3)

```
Set-Location 'D:\Hermes\生产平台\nanobot-factory'
Test-Path 'backend\billing\payments\stripe_provider.py'   -> True
Test-Path 'backend\billing\payments\alipay_provider.py'   -> True
Test-Path 'backend\billing\payments\wechat_provider.py'   -> True
Test-Path 'reports\p6_6_owner_audit.md'                   -> True
```
✅ 通过,继续执行。

---

## 3. 改动的文件

| 文件 | 操作 | 行数 | 说明 |
|---|---|---|---|
| `backend/billing/payments/idempotency.py` | **新增** | 199 | Redis-backed IdempotencyStore (Stripe 设计),带 fakeredis 兜底 |
| `backend/billing/payments/webhook_dedup.py` | **新增** | 211 | Redis SET-NX dedup + 3 provider event-id extractor |
| `backend/billing/tests/__init__.py` | **新增** | 1 | 标记 tests 包 |
| `backend/billing/tests/test_idempotency.py` | **新增** | 230 | 22 tests (9 unit + 8 stripe/alipay/wechat + 2 TTL + 3 routes E2E) |
| `backend/billing/tests/test_webhook_dedup.py` | **新增** | 244 | 21 tests (8 extractor + 8 store unit + 5 routes E2E) |
| `backend/billing/routes.py` | **修改** | +68 / -19 | `create_payment` 加 idempotency,`receive_webhook` 加 dedup |

总计: **+953 / -19** 行净增,**4 个新文件 + 1 个改动文件**。

---

## 4. 设计

### 4.1 Idempotency (Stripe 风格)

参考 [stripe.com/docs/api/idempotent_requests](https://stripe.com/docs/api/idempotent_requests),
策略:
- Client 发送 `Idempotency-Key: <uuid>` header(可选,没传则从 `order_id + payment_method` 推导)。
- `IdempotencyStore.lookup_or_reserve(key, request_hash)` 走 Redis `SET key value NX EX 86400`:
  - 第一次: 返回 `(None, True)`,预留 slot,caller 做事。
  - 重放: 返回 `(hit, False)`,caller 直接返回缓存结果。
  - 在途: 返回 `(None, False)`,返回 HTTP 409。
- `commit(key, request_hash, response)` 替换 placeholder 为真实响应。
- `release(key)` 失败时调用,允许 client 重试。
- TTL = 24h(Stripe 文档行为)。

请求体 hash 校验: 相同 key + 不同 body 返回 cached 结果,但 `_idempotent_replay=true` 提示
client 排查(避免重复扣款的同时不丢请求)。

**失败不缓存**: provider 抛异常时 `release(key)`,让 client 下次重试能跑通(避免"第一次失败永远卡死")。

### 4.2 Webhook 重放保护

参考 Stripe `Event-Id` 去重设计 + 三大 provider 文档:
- **Stripe**: `payload.id` = `evt_...`
- **Alipay**: `payload.notify_id` (Alipay 文档 `异步通知` 字段);缺则 hash(`out_trade_no|trade_no|trade_status`)
- **WeChat**: `payload.id` = `evt_...`;缺则 fallback `resource.transaction_id`

策略:
- 在 signature verify **之前** 用 `SET key value NX EX 86400` 占位。
- 如果 SET 返回 0 (key 存在),返回 `{"received": true, "duplicate": true}` — HTTP 200 让 provider 停止重试。
- Signature 验证失败时 `release()`,合法重试可以再次处理(避免签名错误吞掉 dedup slot)。
- Provider 维度隔离: `webhook_evt:{provider}:{event_id}` 防止跨 provider 撞 key。
- 默认 TTL = 24h(覆盖 Stripe 3-day / Alipay 24h / WeChat v3 5-min×24 ≈ 2h 重试窗口)。

---

## 5. 集成位置 (`backend/billing/routes.py`)

### `create_payment` (P0-1)

```python
# 提取 Idempotency-Key header (客户端控制)
idem_key = request.headers.get("Idempotency-Key") or derive_key_from_order(order_id, method)

# lookup_or_reserve → 三态:hit(重放)/ reserved(我们做)/ 409(在途)
hit, reserved = idem_store.lookup_or_reserve(idem_key, request_hash)
if hit is not None:
    return {**hit.parsed(), "_idempotent_replay": True, ...}
if not reserved:
    raise HTTPException(409, "request already in progress")

try:
    result = provider.create_payment(order)
except ProviderNotConfiguredError:
    idem_store.release(idem_key); raise
except Exception:
    idem_store.release(idem_key); raise  # 失败不缓存

idem_store.commit(idem_key, request_hash, result.to_dict())
return {**payload, "_idempotent_replay": False, "_idempotency_key": idem_key}
```

3 provider 都受保护(走的是同一 `create_payment` endpoint,通过 `provider.name` 选择实现)。

### `receive_webhook` (P0-2)

```python
body = await request.body()
event_id = extract_event_id(provider, body)
dedup = get_dedup_store()
if event_id:
    result = dedup.register(event_id, provider)
    if result.is_duplicate:
        return {"received": True, "duplicate": True, "event_id": event_id}

try:
    event = prov.verify_webhook(body, sig)
except WebhookVerificationError:
    if event_id: dedup.release(event_id, provider)  # 签名失败 → 释放
    raise HTTPException(400, "...")

# 业务逻辑 (mark_paid / refund) — 仅首次执行
order = _STATE["order_service"].get(event.order_id)
if order is not None:
    if event.status == "success": _STATE["order_service"].mark_paid(...)
    elif event.status == "refunded": _STATE["order_service"].refund(...)

return {"received": True, "duplicate": False, "business_applied": True, ...}
```

---

## 6. 存储后端

| Mode | 触发 | 用途 |
|---|---|---|
| `redis` (production) | `REDIS_URL` 可达(默认 `redis://127.0.0.1:6379/0`) | 跨进程/跨实例共享 |
| `fakeredis` (fallback / test) | 真 Redis 不可达 **或** `BILLING_IDEMPOTENCY_BACKEND=fake` / `BILLING_DEDUP_BACKEND=fake` | 单进程本地,CI/离线测试 |

选择逻辑在 `idempotency.py::_build_default_redis()` 和 `webhook_dedup.py::_build_default_redis()`,
两个 backend 互不耦合(idem 和 dedup 可独立切换)。

**已验证真 Redis 路径** (127.0.0.1:6379 alive):
```
first call: hit= None reserved= True
replay: payment_id= pi_real_001 replay_count= 1 reserved= False
extracted event_id: evt_real_redis_smoke
first: is_new= True dup: is_duplicate= True
```

---

## 7. 测试结果

### 7.1 必跑套件

```
$env:PYTHONPATH='D:\Hermes\生产平台\nanobot-factory\backend'
$env:BILLING_IDEMPOTENCY_BACKEND='fake'
$env:BILLING_DEDUP_BACKEND='fake'
python -m pytest backend/billing/tests/test_idempotency.py backend/billing/tests/test_webhook_dedup.py backend/tests/billing/test_payments.py -v

============================= test session starts =============================
collected 54 items

backend\billing\tests\test_idempotency.py ......................  [ 40%]  22 passed
backend\billing\tests\test_webhook_dedup.py .....................  [ 79%]  21 passed
backend\tests\billing\test_payments.py ..........                [100%]  11 passed
============================= 54 passed in 3.19s =============================
```

### 7.2 覆盖率分解

| 模块 | Unit | Provider-level | Routes E2E | TTL | 合计 |
|---|---|---|---|---|---|
| `idempotency.py` | 9 | 8 (stripe×4 + alipay×2 + wechat×2) | 3 | 2 | **22** |
| `webhook_dedup.py` | 16 (8 extractor + 8 store) | — | 5 (stripe×2 + alipay×1 + wechat×1 + bad-sig×1) | — | **21** |
| 原有 `test_payments.py` | — | 11 (回归) | — | — | **11** |
| **总计** | 25 | 19 | 8 | 2 | **54** |

关键场景:
- `test_011_stripe_duplicate_replays_cached_result` — 同一 key + 同一 body → 第二次拿到 cached `payment_id`
- `test_021_duplicate_webhook_short_circuits` — 同一 evt 重放 → 返回 `duplicate=true`,订单状态不再变
- `test_022_alipay_duplicate_webhook_short_circuits` — Alipay 走 `notify_id` 维度去重
- `test_023_wechat_duplicate_webhook_short_circuits` — WeChat 走 `id` 维度去重
- `test_024_bad_signature_releases_dedup_slot` — 签名失败时释放 dedup,合法重试可处理
- `test_050/051/052_routes_*` — 真实 HTTP 路径(POST `/api/v1/billing/payment/{id}`)幂等性
- `test_013_stripe_release_on_provider_failure` — provider 抛异常时释放 idempotency slot

### 7.3 真 Redis 烟测

```
real Redis (127.0.0.1:6379) → 全部 5 步操作 PASS,无 fall-back warning
```

---

## 8. 关键决策与权衡

| 决策 | 选项 | 理由 |
|---|---|---|
| Idempotency layer 放哪里? | (a) provider 内 (b) route 内 | 选 **(b)**: 单一 endpoint、3 provider 共享,client 不感知差异。Provider 仍可独立调用 `create_payment` 用于重放/迁移场景。 |
| Webhook dedup 放哪里? | (a) provider 内 (b) route 内 | 选 **(b)**: dedup 是协议层职责,与签名验证紧耦合,route 是唯一 ingress 点。 |
| Dedup 在签名前还是后? | — | 选 **签名前**: 避免恶意调用 burn 掉 dedup slot(攻击者拿真实 event id 灌死合法投递)。Signature verify 失败时主动 `release()` 让合法重试成功。 |
| TTL = 24h | (a) 1h (b) 24h (c) 7d | 选 **24h**: Stripe 文档明示;覆盖 Alipay 24h 重试、WeChat v3 5min×24 ≈ 2h、Stripe 3d 实际只用 24h 内。 |
| 失败是否缓存? | (a) 缓存 (b) 不缓存 | 选 **不缓存**: provider 异常 `release()` slot,client 可立即重试。Stripe 也这样。 |
| 真实 Redis 不可达时? | (a) 抛错 (b) fallback fakeredis | 选 **(b)**: dev / CI 环境无 Redis 也能跑。生产 `REDIS_URL` 必须存在,fallback 会触发 WARNING log 提醒。 |
| 重复 key + 不同 body? | (a) 422 (b) 200 + cached | 选 **(b)**: Stripe 行为(返回 cached,加 `_idempotent_replay=true` 让 client 排查)。422 容易让 client 重试时拿 409。 |

---

## 9. 已知限制 / 后续

1. **跨进程并发**: 当前用 Redis SET NX 原子操作,跨进程安全。但同一进程内 `threading.Lock` 仅保护
   单进程并发(`_BACKEND_LOCK`) — 真实场景下 IdempotencyStore 的 `lookup_or_reserve` 走 Redis SET NX,
   进程间不会双跑。
2. **Replay count**: 单调递增(每次命中 +1)。Long-running 测试中可观察到。
3. **Key namespace**: `billing:idem:*` 与 `billing:webhook_evt:*`,与现有 `billing:*` Redis keys 区分。
4. **Provider 接入**: 3 provider 当前都是 mock mode (`BILLING_*_MODE=mock`)。
   Live mode 接入只需确保 `provider.create_payment(order)` 抛出时调用方能 `release()` — 现有代码已覆盖。
5. **Header 校验**: `Idempotency-Key` 推荐 1-255 chars,目前没强制 (Stripe 建议 ≥ 16 chars)。
   可在未来 `CreatePaymentRequest` 中加 `idempotency_key: Optional[str]` body 字段。

---

## 10. 交付清单

| Artifact | Path |
|---|---|
| Idempotency store | `backend/billing/payments/idempotency.py` (199 lines) |
| Webhook dedup store | `backend/billing/payments/webhook_dedup.py` (211 lines) |
| Idempotency tests | `backend/billing/tests/test_idempotency.py` (22 tests) |
| Webhook dedup tests | `backend/billing/tests/test_webhook_dedup.py` (21 tests) |
| Routes 接入 | `backend/billing/routes.py` (create_payment + receive_webhook) |
| Report (本文档) | `reports/p6_fix_c_1_payment_idempotency.md` |

---

## 11. 验证命令

```powershell
cd 'D:\Hermes\生产平台\nanobot-factory'
$env:PYTHONPATH = 'D:\Hermes\生产平台\nanobot-factory\backend'
$env:BILLING_IDEMPOTENCY_BACKEND = 'fake'
$env:BILLING_DEDUP_BACKEND = 'fake'
python -m pytest `
  backend/billing/tests/test_idempotency.py `
  backend/billing/tests/test_webhook_dedup.py `
  backend/tests/billing/test_payments.py -v
```

预期:`54 passed in ~3s`

真 Redis 烟测:
```powershell
$env:BILLING_IDEMPOTENCY_BACKEND = ''
$env:BILLING_DEDUP_BACKEND = ''
python -c "import sys; sys.path.insert(0,r'D:/Hermes/生产平台/nanobot-factory/backend'); ..."
```
预期:5 行 PASS 输出 (见 §7.3)。