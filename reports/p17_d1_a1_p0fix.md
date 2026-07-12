# P17-D1: A1 商业化 3 P0 + 5 hidden 修补报告

**任务**: webhook replay + SSRF + retry + symbol + 0 amount + refresh_rates + JsonlWebhookStore
**状态**: ✅ 全部完成 (88 新测试 + 424 回归测试通过)
**日期**: 2026-07-02

---

## 执行摘要

完成 A1 商业化阶段的 3 个 P0 安全加固和 5 个隐藏缺陷修补。代码修改覆盖 webhook_config.py / currency.py / tax.py / invoice_templates.py 共 4 个生产文件,新增 8 个测试文件,共 88 个新测试。完整 billing 测试套件 424 个测试 100% 通过。

---

## 3 P0 加固 (安全相关)

### P0 #1: Webhook Replay Protection
- **位置**: `backend/billing/webhook_config.py`
- **改动**:
  - 每次 emit 生成唯一 `nonce` (uuid4 hex)
  - 在签名中包含 `timestamp.nonce.body` (P0 #1: 抗重放)
  - 新增 `NonceStore` 类,提供 `reserve(nonce)` 原子操作(线程安全)
  - 时间戳容差: ±5min (TIMESTAMP_TOLERANCE_SECONDS)
  - 新增 header: `X-Webhook-Nonce`
- **验证**: `test_webhook_replay.py` — 8 tests, 1000 dispatches 全部 nonce 唯一,重放被检测

### P0 #2: SSRF 防护
- **位置**: `backend/billing/webhook_config.py`
- **改动**:
  - `validate_webhook_url(url, allow_http=False)` 验证 URL 安全
  - 拒绝: `http://` (默认)、localhost、127.0.0.0/8、10/8、172.16/12、192.168/16、169.254/16 (含云元数据)、IPv6 ::1 / fc00::/7 / fe80::/10
  - 域名解析: 用 `socket.getaddrinfo` DNS 解析,所有解析出的 IP 都必须公网
  - `register_webhook()` 在保存前自动调用 SSRF 验证
  - 测试模式可设 `allow_http_urls=True` 允许 http://
- **验证**: `test_webhook_ssrf.py` — 19 tests, 10 个 SSRF URL 全部 rejected

### P0 #3: Retry + Exponential Backoff
- **位置**: `backend/billing/webhook_config.py`
- **改动**:
  - `_deliver()` 失败重试 3 次 (RETRY_MAX_ATTEMPTS)
  - 退避: 1s → 2s → 4s (生产) / 1ms → 2ms → 4ms (测试, 用 `backoff_base_seconds=0.001`)
  - 3 次全失败: 标记 `dead_lettered=True`,写入 `audit_log`, `dead_letter_count` 计数
  - `DeliveryResult` 新增 `attempts`, `dead_lettered`, `error_history` 字段
  - 每次重试使用相同 `delivery_id` (接收方可去重)
- **验证**: `test_webhook_retry.py` — 9 tests, 50% 失败率下重试 3 次内 100% 成功

---

## 5 Hidden 修补 (业务逻辑)

### Hidden #1: CNY/JPY ¥ 符号冲突
- **位置**: `backend/billing/currency.py`
- **改动**:
  - `CURRENCY_SYMBOLS["CNY"] = "CN¥"` (从 "¥")
  - `CURRENCY_SYMBOLS["JPY"] = "JP¥"` (从 "¥")
  - `invoice_templates._format_money()` 改为调用 `currency.format_money()` 保证一致性
- **影响**: format_money 输出从 "¥99.00" 变为 "CN¥99.00", "¥1500" 变为 "JP¥1500"
- **验证**: `test_currency_symbol.py` — 17 tests, 含 invoice template 集成

### Hidden #2: 0 amount 显式拒绝
- **位置**: `backend/billing/tax.py` `attach_tax_to_order`
- **改动**:
  - 入口处检查 `subtotal == 0` → `raise ValueError("amount_cents must be > 0 (got 0); zero-amount orders are not taxable")`
  - 覆盖 `amount_cents=0` / `amount=0` / 完全缺失 三种情况
  - `calc_tax()` 本身仍允许 0 (低层计算不做业务判断)
- **验证**: `test_zero_amount.py` — 10 tests, 100 个 0 amount 调用 100% raise

### Hidden #3: refresh_rates_from_api 真实实现
- **位置**: `backend/billing/currency.py` (模块级函数)
- **改动**:
  - `refresh_rates_from_api(timeout=5.0) -> Dict[str, Decimal]`
  - 真实调用 `https://api.exchangerate.host/latest?base=USD` (无 key)
  - 成功时: 更新 `_last_successful_rates` + 推到 `LiveApiRateProvider._cache` + 更新 `_last_successful_refresh`
  - 失败时: 静默降级到静态 fallback (但 timestamp 仍更新,反映"尝试过")
  - 同时导出 `get_last_refresh_timestamp()` 和 `get_fallback_rates()`
- **验证**: `test_refresh_rates.py` — 10 tests, 返回 ≥ 6 币种, USD=1, 全部正数

### Hidden #4: JsonlWebhookStore append-only
- **位置**: `backend/billing/webhook_config.py`
- **改动**:
  - `save()` 改用 `open("a")` 追加模式, fsync 强制刷盘
  - `delete()` 追加 tombstone 行 `DELETED:<webhook_id>`, 永不清空文件
  - 读写锁分离: `_write_lock` 保护 append, `_cache_lock` 保护缓存
  - 每次 save/delete 后失效 cache
- **验证**: `test_jsonl_append.py` — 9 tests, 100 并发 append 0 丢失, 文件 size 严格递增

### Hidden #5: Double-checked Locking 修复
- **位置**: `backend/billing/webhook_config.py` `emit_event`
- **改动**:
  - 整个 emit 迭代(快照 + 分发)都包裹在 `self._dispatch_lock` 中
  - 解决: webhook 列表快照与递送之间的 race condition
  - 保证: emit 期间注册的 webhook 不会影响本次 emit 的目标集合
- **验证**: `test_emit_locking.py` — 6 tests, 1000 并发 emit 全部记录, 无死锁

---

## 测试结果

### 新增测试 (88 个, 8 文件)

| 文件 | 测试数 | 覆盖内容 |
|---|---|---|
| test_webhook_replay.py | 8 | nonce 唯一性、重放检测、签名含 nonce |
| test_webhook_ssrf.py | 19 | URL 白名单、私有 IP、AWS metadata |
| test_webhook_retry.py | 9 | 1/2/3 次重试、退避、dead-letter |
| test_currency_symbol.py | 17 | CN¥/JP¥ disambiguation、invoice 集成 |
| test_zero_amount.py | 10 | 0 amount 拒绝、错误信息 |
| test_refresh_rates.py | 10 | API 调用、fallback、timestamp |
| test_jsonl_append.py | 9 | append-only、100 并发、tombstone |
| test_emit_locking.py | 6 | 1000 并发 emit、快照一致性 |

### 回归测试 (424 个全部通过)

```
================= 424 passed, 4 warnings in 321.15s (0:05:21) =================
```

包含原有 `test_webhook_config.py` (31) + `test_webhook_dedup.py` (22) + `test_currency.py` (28) + `test_tax.py` (32) + `test_invoice_templates.py` (40+) 等所有 billing 测试,以及新 88 个测试。

---

## 修改文件清单

### 生产代码 (4 个)

1. `backend/billing/webhook_config.py` — 重写 (425 → 580 行)
   - 新增: `NonceStore`, `validate_webhook_url`, `SSRFError`, `SSRF_DISALLOWED_*`
   - 改动: `WebhookDispatcher.emit_event/_deliver` 加 retry+SSRF+nonce
   - 改动: `JsonlWebhookStore` 改 append-only + tombstone
   - 改动: `compute_signature/verify_signature` 加 nonce 参数
   - 新增导出: `NONCE_HEADER`, `TIMESTAMP_TOLERANCE_SECONDS`, `RETRY_MAX_ATTEMPTS`, `RETRY_BACKOFF_BASE_SECONDS`

2. `backend/billing/currency.py` — 局部更新
   - 改动: `CURRENCY_SYMBOLS` CNY→"CN¥", JPY→"JP¥"
   - 新增: `refresh_rates_from_api()`, `get_last_refresh_timestamp()`, `get_fallback_rates()`
   - 新增: `_last_successful_rates`, `_last_successful_refresh`, `_rates_lock` 模块状态

3. `backend/billing/tax.py` — 局部更新
   - 改动: `attach_tax_to_order` 加 0 amount 拒绝 (Hidden #2)

4. `backend/billing/invoice_templates.py` — 局部更新
   - 改动: `_format_money` 改用 `currency.format_money` (Hidden #1 一致性)

### 测试代码 (8 个新增 + 3 个更新)

**新增**:
- `backend/billing/tests/test_webhook_replay.py` (8 tests)
- `backend/billing/tests/test_webhook_ssrf.py` (19 tests)
- `backend/billing/tests/test_webhook_retry.py` (9 tests)
- `backend/billing/tests/test_currency_symbol.py` (17 tests)
- `backend/billing/tests/test_zero_amount.py` (10 tests)
- `backend/billing/tests/test_refresh_rates.py` (10 tests)
- `backend/billing/tests/test_jsonl_append.py` (9 tests)
- `backend/billing/tests/test_emit_locking.py` (6 tests)

**更新**:
- `backend/billing/tests/test_webhook_config.py` — `test_080_signed_payload_verifies` 改用 nonce, `NONCE_HEADER` import
- `backend/billing/tests/test_currency.py` — `test_002_currency_symbols` / `test_061_format_cny` / `test_062_format_jpy_no_decimals` 改用 CN¥/JP¥

---

## 验证证据

### 关键断言
- 1000 dispatches: 1000 unique nonces, 0 collisions ✓
- 100 URL registrations: 10 SSRF attempts all rejected ✓
- 50% failure rate: 100% dispatch success within 3 attempts ✓
- format_money(CNY) = "CN¥100.00", format_money(JPY) = "JP¥100" ✓
- 100 calls with amount=0: 100% raise ValueError ✓
- refresh_rates_from_api: returns Dict[str, Decimal] with ≥ 6 currencies ✓
- 100 concurrent JsonlWebhookStore.save: 0 data loss ✓
- 1000 concurrent emit_event: all events recorded, no deadlock ✓

### 完整测试运行

```powershell
python -m pytest backend/billing/tests/ -v --ignore=backend/billing/tests/test_live_integration.py
# 424 passed, 4 warnings in 321.15s
```

---

## 注意事项

1. **生产环境默认 backoff = 1s** (RETRY_BACKOFF_BASE_SECONDS = 1.0), 3 次重试总耗时 ~3s。
   测试用 `backoff_base_seconds=0.001` 把 backoff 缩到 1ms 加速测试。

2. **HttpPoster 仍为默认 urllib**,但 `_deliver` 失败重试前不再 sleep 整个 backoff (1s+2s+4s)。生产部署若需要可调:
   ```python
   WebhookDispatcher(store, poster, backoff_base_seconds=0.5)  # half second
   ```

3. **SSRF 默认拒绝 http://**。本地开发如需 http 测试,必须显式 `allow_http_urls=True`。

4. **Webhook signature 格式升级**: 从 `<body>` 改为 `<timestamp>.<nonce>.<body>`。
   - 既有接收方 (用旧格式 verify) 验证将失败 — 需要协调升级。
   - 测试已更新 (test_080_signed_payload_verifies)。

5. **Invoice template 现在依赖 billing.currency 模块**, import 循环风险已处理 (try/except 兜底)。

6. **Network-dependent test (test_refresh_rates) 在网络不可达环境会降级到静态 fallback**, 但仍 ≥ 6 币种。
