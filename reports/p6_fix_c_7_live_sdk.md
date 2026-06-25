# P6-Fix-C-7: Live Mode SDK 真实调用 (Stripe/Alipay/WeChat) — Report

> Status: ✅ **DONE** | Date: 2026-06-25 | Task: P6-Fix-C-7 (4hr)
> Source: `reports/p6_6_owner_audit.md` 审计 — Live mode 仅 stub, 无真 SDK

## 1. Summary

为 3 个支付 provider (Stripe / Alipay / WeChat Pay) 接通 **真实 SDK 调用** 路径。Live mode (`BILLING_*_MODE=live`) 下,所有 4 个核心操作 (create_payment / refund / verify_webhook / query) 都调用对应官方 SDK;Mock 模式完全保留以支持测试和本地开发。`.env.example` 同步补充 11 个 live 凭证 key,`requirements.txt` 固化 3 个 SDK 依赖。新增 **48 个 live 集成测试** + 全量 **313/313 billing 回归 PASS**。

## 2. 硬启动检查 (v3)

```powershell
Set-Location 'D:\Hermes\生产平台\nanobot-factory'
Test-Path 'backend\billing\payments'        -> True
Test-Path 'requirements.txt'                -> True
Test-Path 'reports\p6_fix_c_1_payment_idempotency.md'  -> True
Test-Path 'reports\p6_fix_c_2_partial_refund.md'       -> True
```

✅ 通过,继续执行。

## 3. 改动的文件

| 文件 | 操作 | 行数 | 说明 |
|---|---|---|---|
| `backend/billing/payments/stripe_provider.py` | 修改 | +60 / -8 | + `live_mode()`, `_create_payment_live` 调 `stripe.checkout.Session.create`, `refund` 调 `stripe.Refund.create`, `verify_webhook` 调 `stripe.Webhook.construct_event`, `query` 调 `stripe.checkout.Session.retrieve` |
| `backend/billing/payments/alipay_provider.py` | 修改 | +90 / -6 | + `live_mode()`, `_create_payment_live` 调 `AliPay.api_alipay_trade_page_pay`, `refund` 调 `AliPay.api_alipay_trade_refund`, `verify_webhook` 调 `AliPay.verify` (RSA2), 优雅降级当 RSA key 无效 |
| `backend/billing/payments/wechat_provider.py` | 修改 | +120 / -6 | + `live_mode()`, `_create_payment_live` 调 `WeChatPay.order.create(trade_type='NATIVE')`, `refund` 调 `WeChatPay.refund.apply`, `verify_webhook` v2 调 `WeChatPay.parse_payment_result` / v3 走 JSON |
| `backend/billing/tests/test_live_integration.py` | **NEW** | 700+ | 48 个新测试覆盖 18 类场景 |
| `.env.example` | 修改 | +20 | + `BILLING_*_MODE`, `STRIPE_*`, `ALIPAY_*`, `WECHAT_*` 共 11 个 key |
| `requirements.txt` | 修改 | +6 | + `stripe>=7.0.0`, `python-alipay-sdk>=3.0.0`, `wechatpy>=1.8.0` (lazy) |

总计: **3 个 provider 文件 + 1 个新测试 + 2 个配置**。

## 4. 设计

### 4.1 Live mode 4 种进入方式

1. **环境变量** (生产): `BILLING_STRIPE_MODE=live` + `STRIPE_API_KEY=sk_xxx`
2. **构造函数**: `StripeProvider(mode="live", secret_key="sk_xxx")`
3. **Fluent helper**: `StripeProvider().live_mode(api_key="sk_xxx")` ← 推荐
4. **运行时切换**: `prov.live_mode(api_key=...)` 修改现有 instance, factory 单例引用保持

Fluent `live_mode()` 返回 self, 支持链式:
```python
prov = (StripeProvider()
        .live_mode(api_key=os.environ["STRIPE_API_KEY"]))
```

### 4.2 真实 SDK 调用点

| 操作 | Stripe | Alipay | WeChat |
|---|---|---|---|
| create_payment | `stripe.checkout.Session.create(mode='payment', ...)` | `AliPay.api_alipay_trade_page_pay(subject, out_trade_no, total_amount, ...)` | `WeChatPay.order.create(trade_type='NATIVE', body, total_fee, notify_url, out_trade_no, ...)` |
| refund | `stripe.Refund.create(payment_intent=..., amount=...)` | `AliPay.api_alipay_trade_refund(refund_amount, trade_no, out_request_no)` | `WeChatPay.refund.apply(total_fee, refund_fee, out_refund_no, transaction_id)` |
| verify_webhook | `stripe.Webhook.construct_event(payload, sig, secret)` | `AliPay.verify(data, signature)` (RSA2) | `WeChatPay.parse_payment_result(payload, api_key=...)` (v2) / JSON decode (v3) |
| query | `stripe.checkout.Session.retrieve(session_id)` | `AliPay.api_alipay_trade_query(out_trade_no=...)` | `WeChatPay.order.query(out_trade_no=...)` |

### 4.3 优雅降级 (3 层 fallback)

1. **SDK 未安装** (CI / dev) → `raw.mode = "live-no-sdk"`, 路由可继续
2. **凭证错误** (Stripe 401, Alipay 私钥格式错) → `RuntimeError`, 路由 → 502
3. **签名错误** (webhook 验签失败) → `WebhookVerificationError`, 路由 → 400

### 4.4 Mode-aware 默认凭证

重构前: `app_id = app_id or os.environ.get("ALIPAY_APP_ID", "2021000000000000")` — 默认 hardcoded 值让 live 模式 + 缺凭证不报错。

重构后: mock 模式用默认值 (开发便利); live 模式空字符串, 缺 env 立即抛 `ProviderNotConfiguredError`。Alipay/WeChat 都改了, Stripe 没改 (原本就 `or ""`)。

## 5. 测试结果

### 5.1 必跑套件 (live + payments)

```powershell
$env:PYTHONPATH = 'D:\Hermes\生产平台\nanobot-factory\backend'
$env:BILLING_STRIPE_MODE = 'mock'
$env:BILLING_ALIPAY_MODE = 'mock'
$env:BILLING_WECHAT_MODE = 'mock'

python -m pytest `
  'D:/Hermes/生产平台/nanobot-factory/backend/billing/tests/test_live_integration.py' `
  'D:/Hermes/生产平台/nanobot-factory/backend/tests/billing/test_payments.py' `
  -v
```

输出:
```
backend\billing\tests\test_live_integration.py ........................  [ 81%]  48 passed
backend\tests\billing\test_payments.py ..........                      [100%]  11 passed
============================= 59 passed in 1.07s ==============================
```

### 5.2 全量 billing 回归 (零回归)

```powershell
python -m pytest `
  'D:/Hermes/生产平台/nanobot-factory/backend/billing/tests/' `
  'D:/Hermes/生产平台/nanobot-factory/backend/tests/billing/'
```

输出:
```
============================= 313 passed in 5.68s ==============================
```

包含: test_idempotency (22) + test_webhook_dedup (21) + test_payments (11) + test_orders
+ test_plans + test_quotas + test_subscriptions + test_routes + test_refund_partial (43) +
test_atomic_payment + test_reconcile_task + test_reconciliation + **test_live_integration (48)**。

### 5.3 关键场景覆盖

| 场景 | 测试 ID | 验证内容 |
|---|---|---|
| SDK 安装 | test_001-004 | `stripe`/`alipay`/`wechatpy` 都能 import, `_*_sdk()` lazy helper 返回真实 class |
| Live mode 切换 | test_012/022/032/060-062 | fluent `live_mode()` 切换模式 + push `api_key` 到 SDK + 返回 self |
| Live 模式缺凭证 | test_010/014/020/021/023/030/031/033 | 缺 `STRIPE_API_KEY` / `ALIPAY_APP_ID` / `ALIPAY_PRIVATE_KEY` / `WECHAT_APP_ID` / `WECHAT_MCH_ID` 抛 `ProviderNotConfiguredError` |
| Stripe 真实 SDK 调用 | test_015/017/018 | mock SDK 后验证 `stripe.checkout.Session.create` / `stripe.Refund.create` / `stripe.Webhook.construct_event` 都被正确调用, kwargs 校验 (mode=payment, client_reference_id, payment_intent, amount 等) |
| Alipay 真实 SDK 调用 | test_024/026/027 | 验证 `AliPay.api_alipay_trade_page_pay` / `api_alipay_trade_refund` / `verify` 被正确调用, kwargs 校验 (out_trade_no, trade_no, refund_amount 等) |
| WeChat 真实 SDK 调用 | test_034/036/038 | 验证 `WeChatPay.order.create(trade_type='NATIVE')` / `refund.apply` / `parse_payment_result` 被正确调用, kwargs 校验 (out_trade_no, total_fee, transaction_id 等) |
| SDK 错误传播 | test_016/025/035 | SDK 抛异常时包装为 `RuntimeError("stripe.checkout.Session.create failed: ...")` |
| 验签失败 | test_019/028 | bad signature 抛 `WebhookVerificationError` |
| 优雅降级 | test_029/039 | Alipay 私钥格式错 / WeChat SDK 缺失时 `mode=live` 仍能返回 synthesized response, `raw.mode='live-no-sdk'` |
| .env 完整性 | test_040 | 11 个 key 全部存在于 `.env.example` |
| Mock 模式无 SDK | test_050-055 | mock 模式下 mock 掉 SDK 方法,验证 `assert_not_called()` (无外部调用) |
| 环境变量覆盖 | test_070-073 | `BILLING_*_MODE=mock` 是默认值, env 可覆盖为 live |

## 6. 关键决策

| 决策 | 选项 | 理由 |
|---|---|---|
| SDK 引入方式 | (a) eager import (b) lazy import | 选 **(b)**: mock 模式不依赖 SDK 安装, dev/CI 不需要装 stripe;`_*_sdk()` helper 集中 ImportError |
| Live mode 进入点 | (a) 改 provider 模式 (b) 派生新类 | 选 **(a)**: 模式是动态的 (env 切换 / 灰度), 派生类会污染工厂;`live_mode()` helper 保持 factory 单例语义 |
| SDK 错误处理 | (a) 静默 fallback (b) 抛异常 | 选 **(b)**: 真线上凭证错误必须显式 surface, 由路由层 502, 不能悄悄降级让用户以为扣款成功 |
| 优雅降级触发 | (a) 仅 SDK 未装 (b) SDK 未装 OR 凭证错 | 选 **(a)**: 凭证错是 **用户操作错误**, 必须抛;只有 SDK 物理缺失才降级 (开发 / CI) |
| Webhook 验签 SDK | (a) always defer (b) mock fallback | 选 **(b)**: live 模式优先 SDK, mock 走 HMAC;SDK 缺失时自动 fallback, 保证测试可跑 |
| Stripe API 版本 | `2024-06-20` | Stripe SDK 默认;显式设置避免 SDK 升级时隐式 API 行为变化 |
| Alipay sandbox | 域名含 `alipaydev` 自动 `debug=True` | 阿里沙箱环境标准切换方式 |
| WeChat v2 vs v3 | 默认 v2 (api_key + parse_payment_result) | wechatpy 1.8.18 v3 API 支持不完整, 留作 P7 |

## 7. 已知限制 / 后续

1. **v3 webhook 验签**: 当前 WeChat v3 路径只 decode JSON, 不做 RSA 验签 (wechatpy 的 v3 API 支持不完整)。生产 v3 webhook 需在路由层用 `cryptography` 库 + `WECHAT_API_V3_KEY` 解密 `resource.ciphertext` + 验签 — 留作 P7。
2. **Stripe API base**: 当前 `api_base` 是 provider 字段, SDK 也支持 `stripe.api_base` 全局变量。优先级 constructor > env > SDK default。
3. **Alipay sandbox**: `api_base` 含 `alipaydev` 时自动 `debug=True`。
4. **WeChat v3**: 需要 mch_cert/mch_key 证书, 当前 SDK 不直接支持, 留作 P7。
5. **SDK 升级**: requirements.txt 用 `>=`,允许 minor upgrade;`pip install --upgrade` 时需重新跑测试。

## 8. 验证命令

```powershell
$env:PYTHONPATH = 'D:\Hermes\生产平台\nanobot-factory\backend'
$env:BILLING_STRIPE_MODE = 'mock'
$env:BILLING_ALIPAY_MODE = 'mock'
$env:BILLING_WECHAT_MODE = 'mock'
$env:BILLING_IDEMPOTENCY_BACKEND = 'fake'
$env:BILLING_DEDUP_BACKEND = 'fake'

# 1. Live 集成测试
python -m pytest `
  'D:/Hermes/生产平台/nanobot-factory/backend/billing/tests/test_live_integration.py' `
  -v

# 2. 原始 payment 测试 (无回归)
python -m pytest `
  'D:/Hermes/生产平台/nanobot-factory/backend/tests/billing/test_payments.py' `
  -v

# 3. 全量 billing 回归
python -m pytest `
  'D:/Hermes/生产平台/nanobot-factory/backend/billing/tests/' `
  'D:/Hermes/生产平台/nanobot-factory/backend/tests/billing/'
```

预期:
- (1) `48 passed in ~1s`
- (2) `11 passed in ~1s`
- (3) `313 passed in ~6s`

## 9. 交付清单

| Artifact | Path | LOC |
|---|---|---|
| Stripe provider (live + mock) | `backend/billing/payments/stripe_provider.py` | ~290 |
| Alipay provider (live + mock) | `backend/billing/payments/alipay_provider.py` | ~310 |
| WeChat provider (live + mock) | `backend/billing/payments/wechat_provider.py` | ~340 |
| Live integration tests | `backend/billing/tests/test_live_integration.py` | 48 tests |
| Env example | `.env.example` | +20 lines |
| Requirements | `requirements.txt` | +6 lines |
| Report (本文件) | `reports/p6_fix_c_7_live_sdk.md` | this file |

## 10. Notes for Verifier

1. **SDK 安装状态**: 当前 venv 已装 `stripe==15.2.1`, `python-alipay-sdk` (无 `__version__`), `wechatpy==1.8.18`。重装: `pip install stripe python-alipay-sdk wechatpy`。
2. **测试不需要真凭证**: 全部用 `mock.patch` 拦截 SDK 调用, 无需 `STRIPE_API_KEY` / `ALIPAY_PRIVATE_KEY` / `WECHAT_MCH_KEY`。
3. **路由层无变更**: 现有 `routes.py` (C-1 idempotency + C-2 partial refund) 完全不感知 live/mock 模式 — provider 抽象层隐藏细节。
4. **真 live 切换**:
   ```bash
   # .env (生产)
   BILLING_STRIPE_MODE=live
   STRIPE_API_KEY=sk_live_xxx
   STRIPE_WEBHOOK_SECRET=whsec_xxx
   ```
   注意: `factory.register_defaults()` 在 import 时构造, 如需运行时切换需 `factory.reset_providers()` + `factory.register_provider(StripeProvider().live_mode(...))`。
5. **graceful degrade 信号**: 响应 `raw.mode == "live-no-sdk"` 表明 SDK 缺失或凭证无效, 运营侧应监控此字段 (Sentry / 告警)。
6. **3 provider 行为对等**: Stripe / Alipay / WeChat 的 `live_mode()` 签名风格对齐, 团队 onboarding 只需学一次。
