# P17-A1 报告: 商业化 4 P1

**任务**: multi-currency + tax + invoice-template + webhook-config (25 min)  
**状态**: ✅ DONE (实际 ~25 min)  
**测试**: 125/125 新增 PASS, 384/384 整体 billing PASS (0 回归)

---

## 4 模块交付

| # | 模块 | 文件 | 行数 | 测试 | 关键能力 |
|---|---|---|---|---|---|
| 1 | multi-currency | `backend/billing/currency.py` | ~290 | 37 | 6 币种, 实时 API + 静态 fallback, 100+ 轮换验证 |
| 2 | tax | `backend/billing/tax.py` | ~260 | 40 | CN/US/EU 3 税制, 12 country×category 组合 |
| 3 | invoice-template | `backend/billing/invoice_templates.py` | ~390 | 17 | 5 模板, ReportLab PDF, CJK 字体 |
| 4 | webhook-config | `backend/billing/webhook_config.py` | ~310 | 31 | 5 事件, HMAC-SHA256 签名, E2E dispatch |

---

## 验证证据

```
$ python -m pytest backend/billing/tests/test_currency.py \
                  backend/billing/tests/test_tax.py \
                  backend/billing/tests/test_invoice_templates.py \
                  backend/billing/tests/test_webhook_config.py
================= 125 passed, 4 warnings in 92.64s (0:01:32) =================

$ python -m pytest backend/billing/tests/   # 整体回归
================= 384 passed, 4 warnings in 137.16s (0:02:17) =================
```

### Spec 要求 vs 实际

| Spec | 实际 | 状态 |
|---|---|---|
| 6 币种互转 100 次 | 240 round-trip, 全部 within `max(10 cents, 0.01%)` | ✅ |
| 12 country × category 组合 | 12 parametrized test, 全部 PASS | ✅ |
| 5 模板各 1 sample PDF | 5 PDF 写入 tmp_path, 全部 valid (`%PDF-`/`%%EOF`) | ✅ |
| 5 事件全部 dispatch | 5 event emit, 全部 `success=True`, sig 已签 | ✅ |
| HMAC-SHA256 签名 | `X-Webhook-Signature: sha256=<hex>`, 含 timestamp 防重放 | ✅ |
| `Order.currency` 字段 | 已存在 (`orders.py:69`), `convert_currency` 提供机制 | ✅ |
| `Order.tax_amount` + `tax_rate` | 通过 `attach_tax_to_order()` 计算 (避免改 frozen dataclass) | ✅ |
| 实时汇率 (ENV) | `EXCHANGE_RATE_API_KEY` 可选, 失败 fallback 静态 | ✅ |

---

## 设计决策

### 1. 不改 `Order`/`Plan` dataclass
- `Order` 已 P6 交付, 含 `currency` 字段, 重构会破坏现有代码
- `tax_amount`/`tax_rate` 通过 `attach_tax_to_order()` 计算返回, 不污染 frozen dataclass
- `currency.convert_currency()` 是无状态函数, 任何 Order/Plan 可按需调用

### 2. Webhook poster 可注入
- `WebhookDispatcher(poster=...)` 接受自定义 poster
- 测试用 `MockPoster` 模拟响应 (无网络调用)
- 生产用 `HTTPPoster` (urllib + 10s timeout)

### 3. 实时汇率缓存 6h
- 汇率不需秒级刷新, 6h TTL 平衡新鲜度与 API 配额
- 失败 fallback 静默 (一次性 warning), 不影响业务

### 4. CJK 字体自动注册
- ReportLab 的 `STSong-Light` (CID 字体) 一次注册, 5 模板通用
- 客户名/商品名中英文混排无忧

---

## 8 个文件清单

### Source (4)
```
backend/billing/currency.py             # 6 currency + provider + convert
backend/billing/tax.py                  # 3 regime + calc_tax + OrderTotals
backend/billing/invoice_templates.py    # 5 templates + ReportLab
backend/billing/webhook_config.py       # 5 events + HMAC-SHA256
```

### Tests (4)
```
backend/billing/tests/test_currency.py            # 37 tests
backend/billing/tests/test_tax.py                 # 40 tests
backend/billing/tests/test_invoice_templates.py   # 17 tests
backend/billing/tests/test_webhook_config.py      # 31 tests
```

---

## Deliverable

完整 deliverable 报告: `C:\Users\Administrator\.mavis\plans\plan_5bbc2cec\outputs\p17_a1_billing_p1\deliverable.md`

包含 8 文件清单、4 模块详细 public surface、设计决策、verifier notes。
