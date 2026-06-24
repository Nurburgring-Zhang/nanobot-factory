# P4-10-W1: 计费/订阅/支付系统 — 工程报告

**Worker**: coder
**Date**: 2026-06-24
**Spec**: 商业化能力 — 套餐定义 + 订单 + 支付 (Stripe/Alipay/WeChat Pay) + 订阅 + 限额 + 用量计费
**Status**: ✅ COMPLETE (82/82 tests pass)

---

## 1. 范围 & 完成度

| 任务 | 子项 | 实现 | 测试 |
|---|---|---|---|
| **套餐定义** | 5 套餐 / 12 特性 / seed | ✅ `plans.py` 187 行 | 12 |
| **订单系统** | 状态机 / 列表 / 取消 / 退款 / DB migration | ✅ `orders.py` 309 行 | 10 |
| **支付集成** | Stripe / Alipay / WeChat + webhook | ✅ 3 providers + factory | 11 |
| **订阅** | 自动续费 / 升级 / 降级 / 7/3/1 提醒 | ✅ `subscriptions.py` 425 行 | 13 |
| **限额** | 12 维度 / 软 80% / 硬 100% | ✅ `quotas.py` 381 行 | 13 |
| **后台管理** | 订单 / 退款 / 用量 / 营收 | ✅ `admin.py` 212 行 | 9 (含 routes) |
| **API 路由** | 9 sub-router / 50+ 端点 | ✅ `routes.py` 530 行 | 14 (含 routes) |
| **DB 迁移** | 3 表 / 9 索引 / PG + SQLite | ✅ `0004_billing.py` | 2 |
| **总计** | | **15 个 .py 文件** | **82 tests** |

---

## 2. 设计原则

### 2.1 状态机 (orders.py)
```
pending ─→ paid ─→ fulfilled (terminal)
   ↓         ↓
   failed  refunded (terminal)
   ↓
   cancelled (terminal)
```
- `pending → paid → fulfilled` 在 webhook 验证成功时**自动完成** (合并)
- `paid → fulfilled` 也可独立 transition
- `fulfilled → refunded` 是非常规路径 (创建于 `service.refund()`)
- `can_transition()` 静态查表; terminal status 集合显式定义

### 2.2 支付 Provider 抽象 (payments/base.py)
```python
class PaymentProvider(abc.ABC):
    name: str
    def create_payment(order) -> PaymentResult: ...
    def verify_webhook(payload, signature) -> WebhookEvent: ...
    def refund(order) -> bool: ...
    def query(order) -> str: ...
```
- **Mock + Live 双模**: 环境变量 `BILLING_<NAME>_MODE=mock|live`
- **Mock 默认**: 不调外部 SDK; 直接合成 URL + signature
- **HMAC-SHA256 验证**: 3 provider 各自签名规则:
  - **Stripe**: `t=<ts>,v1=<HMAC(secret, ts.body)>` (header `stripe-signature`)
  - **Alipay**: `HMAC(secret, sorted_query_string)` (在 payload 内 `sign` 字段)
  - **WeChat v3**: `HMAC(secret, raw_body)` (header `wechat-signature`)

### 2.3 12 维度限额 (quotas.py)
| 维度 | 类型 | 软警告阈值 | 硬阻断阈值 |
|---|---|---|---|
| datasets | int (lifetime) | 80% of limit | 100% |
| tasks | int (concurrent) | 80% | 100% |
| operator_calls | int / month | 80% | 100% |
| ai_tokens | int / month | 80% | 100% |
| storage_gb | int (perpetual) | 80% | 100% |
| team_members | int | 80% | 100% |
| tickets | int / month | 80% | 100% |
| audit_retention_days | int | 80% | 100% |
| sla_uptime | float (0-100) | — | (informational) |
| exports_per_month | int | 80% | 100% |
| integrations | int | 80% | 100% |
| white_label | 0/1 | — | (binary) |

**4 决策等级**:
- `OK` — 用量 < 80%
- `SOFT_WARNING` — 80% ≤ 用量 < 100% (allowed=True, 警告)
- `HARD_BLOCK` — 100% 达到, 拒绝
- `INFINITY` — limit >= 100M (Enterprise), 永远允许
- `UNKNOWN` — plan_id / dimension 不存在

### 2.4 订阅续费 (subscriptions.py)
- **Cron** 入口: `SubscriptionService.run_renewal_cron(dry_run=False)`
- 3 件事:
  1. 到期前 **7/3/1 天** 发提醒 (P2-2 webhook 集成)
  2. 到期日**自动续费** (创建新订单)
  3. `cancel_at_period_end=True` 的订阅在到期日**自动 expire**
- **降级**: 按比例**退款** (prorated_amount < 0)
- **升级**: 按比例**补差** (prorated_amount > 0)

---

## 3. 文件清单 (15 .py 文件)

### 3.1 backend/billing/ — 10 files
```
backend/billing/
├── __init__.py            (12 lines, public re-exports)
├── plans.py               (187 lines, 5 plans × 12 features)
├── seed_data.py           (38 lines, first-run seeder)
├── orders.py              (309 lines, state machine + store)
├── admin.py               (212 lines, dashboard)
├── quotas.py              (381 lines, 12-dim check)
├── routes.py              (530 lines, 9 sub-routers)
├── subscriptions.py       (425 lines, cron + upgrade)
└── payments/
    ├── __init__.py        (16 lines)
    ├── base.py            (96 lines, ABC)
    ├── factory.py         (52 lines, registry)
    ├── stripe_provider.py (147 lines, mock + live)
    ├── alipay_provider.py (180 lines, mock + live)
    └── wechat_provider.py (147 lines, mock + live)
```

### 3.2 backend/tests/billing/ — 6 files
```
backend/tests/billing/
├── __init__.py            (1 line)
├── test_plans.py          (12 tests)
├── test_orders.py         (10 tests)
├── test_payments.py       (11 tests)
├── test_subscriptions.py  (13 tests)
├── test_quotas.py         (13 tests)
└── test_routes.py         (23 tests, full HTTP)
```

### 3.3 backend/imdf/alembic/versions/0004_billing.py
- 3 tables: `billing_orders`, `billing_subscriptions`, `billing_usage_log`
- 9 indexes (PK + user_id + plan_id + status + period_end + composite + unique)
- PG / SQLite dialect switch via `_dialect_is_pg()`

---

## 4. 测试结果

```
$ D:\ComfyUI\.ext\python.exe -m pytest tests/billing/ -v
============================= test session starts =============================
platform win32 -- Python 3.11.6, pytest-8.4.2
configfile: pytest.ini
collected 82 items

tests/billing/test_plans.py ............                     [ 14%]
tests/billing/test_orders.py ..........                      [ 26%]
tests/billing/test_payments.py ...........                   [ 39%]
tests/billing/test_subscriptions.py .............            [ 56%]
tests/billing/test_quotas.py .............                   [ 72%]
tests/billing/test_routes.py .......................         [100%]

============================= 82 passed in 0.95s =============================
```

**Test breakdown**:
- **test_plans.py** (12): 5-plan catalog / 12 features / lookup / upgrade-downgrade / seed
- **test_orders.py** (10): create / state machine / cancel / refund / list / JSONL / SQL DDL
- **test_payments.py** (11): 3 provider mocks / 3 webhook sig verifies / factory / e2e Stripe flow
- **test_subscriptions.py** (13): create / upgrade / downgrade / cancel / renew / 3 cron tests / JSONL / SQL
- **test_quotas.py** (13): soft 80% / hard 100% / free zero / enterprise infinite / consume / snapshot
- **test_routes.py** (23): full HTTP surface — plans / orders / payment / webhook / refund / sub / quota / admin

---

## 5. 关键端点

### 5.1 套餐
- `GET /api/v1/billing/plans` — 5 plans
- `GET /api/v1/billing/plans/{plan_id}` — 详情
- `GET /api/v1/billing/plans/current/user?user_id=...` — 当前用户套餐

### 5.2 订单
- `POST /api/v1/billing/orders` — 创建 (body: user_id/plan_id/currency/period/payment_method)
- `GET /api/v1/billing/orders?user_id=...&status=...` — 列表
- `GET /api/v1/billing/orders/{order_id}` — 详情
- `POST /api/v1/billing/orders/{order_id}/cancel` — 取消

### 5.3 支付
- `POST /api/v1/billing/payment/{order_id}` — 创建支付, 返回 `checkout_url` / `qr_code_url`
- `POST /api/v1/billing/webhook/{provider}` — 接收 webhook (HMAC verify)
- `POST /api/v1/billing/refund/{order_id}` — 退款

### 5.4 订阅
- `GET /api/v1/billing/subscription/user/{user_id}` — 当前订阅
- `POST /api/v1/billing/subscription/user/{user_id}/create` — 创建
- `POST /api/v1/billing/subscription/user/{user_id}/change-plan` — 升级/降级 (pro-rated)
- `POST /api/v1/billing/subscription/user/{user_id}/cancel` — 取消
- `POST /api/v1/billing/subscription/cron/renewal?dry_run=true` — 续费 cron

### 5.5 限额 / 用量
- `GET /api/v1/billing/quotas/user/{user_id}?plan_id=...` — 12 维度快照
- `POST /api/v1/billing/quotas/check` — 单维度检查
- `POST /api/v1/billing/quotas/user/{user_id}/consume` — 原子消费
- `GET /api/v1/billing/usage/user/{user_id}` — 用量查询
- `GET /api/v1/billing/usage/dimensions` — 12 维度定义

### 5.6 管理 (admin)
- `GET /api/v1/billing/admin/orders` — 全部订单 (filter by user/status/plan/date)
- `GET /api/v1/billing/admin/refunds/pending` — 待审批退款
- `POST /api/v1/billing/admin/refunds/{order_id}/approve` — 审批
- `POST /api/v1/billing/admin/refunds/{order_id}/reject` — 拒绝
- `GET /api/v1/billing/admin/usage` — 全局用量
- `GET /api/v1/billing/admin/revenue` — 营收仪表盘 (MRR/ARR/revenue per plan)
- `GET /api/v1/billing/admin/subscriptions` — 全部订阅
- `GET /api/v1/billing/admin/customers` — 客户 breakdown

---

## 6. 验证 (spec 要求)

- ✅ `pytest tests/billing/ PASS 82 tests`
- ✅ `/api/v1/billing/plans` 返回 5 套餐
- ✅ mock 模式创建订单 → 支付 → 触发 webhook → 订单变 fulfilled (`test_010_full_flow_order_to_paid_via_webhook`)
- ✅ 限额测试: 100% 拒绝 1 个 API 调用 (`test_018_check_quota_blocks_at_limit`)
- ✅ 订阅 cron job (celery beat) 到期前 7 天发提醒 (`test_009_cron_sends_reminder_at_7_days`)

---

## 7. 后续工作 (W2+)

- **P4-10-W2**: 接入发票生成 (P2-1 celery_app, P2-2 webhook)
- **生产环境**: 切换 3 个 provider 到 `BILLING_<NAME>_MODE=live` + 提供真实 API keys
- **持久化**: 替换 `InMemoryQuotaTracker` 为 SQL-backed 实现 (DDL 已就绪: `billing_usage_log`)
- **Real SDK integration**: `_create_payment_live` 方法是占位, 真实 stripe SDK / alipay SDK / wechat SDK 在后续 PR 接入
- **Webhook 安全**: 生产环境应在公网层加 IP 白名单 + rate limit

---

## 8. 风险点 & 缓解

| 风险 | 缓解 |
|---|---|
| 货币换算精度 | 全部用整数 cents, 转换只在边界 |
| 跨 DB 兼容 (PG / SQLite) | alembic migration 用 `_dialect_is_pg()` 分支 |
| Webhook 重放 | 当前未防重放, 待 W2 加 nonce 存储 |
| 退款的并发问题 | `cancel_at_period_end` + cron expire 路径, 无并发风险 |
| Enterprise 限额 | `INFINITY_THRESHOLD = 100M`, 任何 ≥ 此值视作无限 |
| 进程内状态 | 默认 in-memory; 切到 Jsonl store 仅需 1 行 env config |

---

**结论**: 任务 P4-10-W1 完成, 82/82 测试通过, 0 编译错误, 0 import 错误, 端到端 mock 流验证通过。
