# P6-Fix-C-3: 扣费 + 订单 atomic 事务

**任务ID**: P6-Fix-C-3
**模块**: `backend/billing/`
**预计工期**: 2 hr
**实际完成**: ~50 min
**测试结果**: 19/19 新增 + 10/10 必跑 = 29/29 PASS, 全量 billing 101/101 PASS (零回归)

---

## 1. 目标

把"扣费 + 创建订单 + 更新订阅"三步包进同一个 SQLAlchemy 事务,任一步失败 → 全部 rollback,不留下半成品订单或幽灵扣费。

**Before(prior 状态)**:
- `backend/billing/orders.py` 用 `InMemoryOrderStore` / `JsonlOrderStore`,全程进程内 dict + 锁
- `backend/billing/subscriptions.py` 同上
- `backend/billing/payments/` 走 provider mock,无数据库落地
- **没有真 SQLAlchemy 模型,没有 `session.begin()` 事务**
- 一旦 provider 返回 success 但订阅更新失败,订单状态机就坏掉

**After(本次改动)**:
- 新增 `backend/billing/db.py` — SQLAlchemy ORM (Wallet / BillingOrder / BillingSubscription) + sessionmaker
- 新增 `backend/billing/atomic_pay.py` — `pay_order()` 用 `with session.begin():` 把三步包成 ALL-or-NOTHING 事务
- 新增 `backend/tests/billing/test_atomic_payment.py` — 19 个测试覆盖 happy / rollback / invariants / idempotency / 静态+运行时证明

---

## 2. 设计要点

### 2.1 三步 in-one-transaction

```python
session: Session
with sf() as session:
    with session.begin():
        # Step 1 — 创建/获取订单
        order = BillingOrder(... status="paid", paid_at=now ...)
        session.add(order)
        # Step 2 — 扣钱包
        wallet.balance_cents -= amount_cents
        # Step 3 — 创建/延长订阅
        sub.current_period_end = end + timedelta(days=30)
        sub.status = "active"
    # ↑ 块退出 → 自动 commit;块内异常 → 自动 rollback
```

`session.begin()` 是 SQLAlchemy 2.0 推荐的 context-manager 模式:
- **commit-on-exit**: 正常退出时,事务块 commit
- **rollback-on-exception**: 块内任何异常向上抛 → 事务块 rollback,所有 ORM 变更撤销

### 2.2 业务异常类型

| 异常 | 触发条件 | 事务结果 |
|---|---|---|
| `InsufficientFundsError` | 钱包余额 < amount_cents | rollback |
| `OrderAlreadyPaidError` | `existing_order_id` 非 pending | rollback |
| `SubscriptionPlanMismatchError` | 用户已有 active 订阅,plan 不一致 | rollback |
| `KeyError("wallet not found")` | 用户钱包不存在 | rollback |
| `ValueError("wallet currency mismatch")` | 钱包币种 vs 订单币种 | rollback |
| hook 异常 | invoice/notification 服务挂了 | rollback |

每个异常类型都携带诊断字段(`balance_cents` / `required_cents` / `current_status`),便于上层做 4xx 响应。

### 2.3 ORM 模型

```python
class Wallet(Base):         # 用户钱包
    user_id: str  (PK)
    balance_cents: int
    currency: str

class BillingOrder(Base):   # 订单 ORM 镜像 (与 Order dataclass 字段一一对应)
    order_id: str  (PK)
    user_id, plan_id, amount_cents, currency, status, payment_method
    external_ref, paid_at, fulfilled_at, refunded_at, refund_reason
    metadata_json: Text   (JSON 字符串)

class BillingSubscription(Base):  # 订阅 ORM 镜像
    subscription_id: str  (PK)
    user_id: str  (UNIQUE)  ← 一对一
    plan_id, status, current_period_start, current_period_end
    cancel_at_period_end, last_renewal_*
```

### 2.4 Hook Protocol (可注入副作用)

```python
class PayHook(Protocol):
    def on_wallet_deducted(self, wallet, amount_cents) -> None: ...
    def on_order_paid(self, order) -> None: ...
    def on_subscription_extended(self, sub, order) -> None: ...
```

**关键**: hook 在 **commit 之前** 调用,hook 抛异常 → 整笔 rollback。生产侧应让 hook 只做"标记待发送",实际发邮件/发票走 post-commit worker。

### 2.5 已有代码兼容

- `orders.py` / `subscriptions.py` / `payments/*` 未改动
- `routes.py` 未改动
- `billing/__init__.py` 只追加 `from . import db, atomic_pay`
- 现有 `InMemoryOrderStore` / `JsonlOrderStore` 路径继续可用,新 SQL 路径是 **新可选** 模块,用于真实生产部署

---

## 3. 文件清单

| 文件 | 状态 | 行数 | 说明 |
|---|---|---|---|
| `backend/billing/db.py` | **新增** | 215 | SQLAlchemy ORM + engine + session factory |
| `backend/billing/atomic_pay.py` | **新增** | 348 | pay_order() + 异常 + Hook Protocol |
| `backend/tests/billing/test_atomic_payment.py` | **新增** | 386 | 19 个测试 |
| `backend/billing/__init__.py` | 修改 | +2 行 | 导出新模块 |

**总计**: ~950 行新代码 + 测试, 0 行删除

---

## 4. 测试覆盖矩阵 (19 个测试)

| 测试类 | # | 验证内容 |
|---|---|---|
| `TestPayOrderHappyPath` | 4 | 正常路径: 创建订单 + 扣费 + 创建/延长订阅 |
| `TestPayOrderRollback` | 5 | 失败 rollback: 余额不足/钱包缺失/订单已付/plan不匹配/hook异常 |
| `TestPayOrderInvariants` | 4 | 业务不变量: 非法金额/币种/边界/币种不匹配 |
| `TestCreateOrTopupWallet` | 3 | 钱包 helper 幂等性 |
| `TestSessionBeginProof` | 3 | 静态 + 运行时证明 `session.begin()` 真的被调用 |

### 关键测试示范

**Rollback 验证 (`test_005_insufficient_funds_rolls_back_everything`)**:
```python
create_or_topup_wallet("u_bob", 1000, "USD")  # 余额 1000¢
with pytest.raises(InsufficientFundsError):
    pay_order("u_bob", "pro", amount_cents=5000, ...)  # 缺 4000¢
# 验证: 余额仍为 1000,无订单,无订阅
with session_factory() as s:
    assert s.get(Wallet, "u_bob").balance_cents == 1000  # ✓
    assert s.query(BillingOrder).filter_by(user_id="u_bob").all() == []  # ✓
    assert s.query(BillingSubscription).filter_by(user_id="u_bob").all() == []  # ✓
```

**Hook 异常 rollback (`test_009_hook_exception_rolls_back_everything`)**:
```python
class FailingHook(NoopPayHook):
    def on_subscription_extended(self, sub, order):
        raise RuntimeError("invoice-service-down")

with pytest.raises(RuntimeError, match="invoice-service-down"):
    pay_order(..., hook=FailingHook())

# 验证: 余额 10000 (未变), 无订单, 无订阅
```

**Session.begin 静态证明 (`test_017`)**:
```python
src = inspect.getsource(atomic_pay.pay_order)
assert "session.begin()" in src         # ✓
assert "balance - int(amount_cents)" in src  # ✓
assert "session.add(order)" in src      # ✓
```

**Session.begin 运行时证明 (`test_019`)**:
```python
monkeypatch.setattr(Session, "begin", spy)  # 计数
pay_order(...)
assert called["count"] >= 1  # ✓ session.begin() 真的被调用
```

---

## 5. 必跑测试结果

### 命令
```
cd backend && python -m pytest tests/billing/test_orders.py -v
```

### 结果
```
============================= 10 passed in 0.43s ==============================
TestOrderCreate::test_001_create_order_pending PASSED
TestOrderCreate::test_002_create_order_invalid_amount PASSED
TestOrderStateMachine::test_003_pending_to_paid_transition PASSED
TestOrderStateMachine::test_004_invalid_transition_raises PASSED
TestOrderStateMachine::test_005_refund_after_payment PASSED
TestOrderCancel::test_006_cancel_pending_order PASSED
TestOrderList::test_007_list_filter_by_user_and_status PASSED
TestOrderJsonlStore::test_008_jsonl_store_persistence PASSED
TestStateMachineHelpers::test_009_can_transition_table PASSED
TestOrderSQL::test_010_ddl_strings_present PASSED
```

### 全量 billing 测试
```
$ python -m pytest tests/billing/ -v
============================= 101 passed in 1.21s =============================
```
- 19 个新增原子事务测试
- 82 个已有测试, **零回归**

---

## 6. 已知边界 / 未做

| 项 | 现状 | 后续建议 |
|---|---|---|
| Wallet 行级锁 | 当前用 `with_for_update=False` (SQLite 不支持 SKIP LOCKED) | 切 Postgres 后改 `with_for_update=True` |
| 并发幂等 | 单进程 OK,多进程需 DB 唯一约束 | 加 `UNIQUE (user_id, idempotency_key)` 在 order 上 |
| 计费货币 | 仅 USD/CNY,wallet 单币种 | 多币种: 加 wallet_currency_balances 多行模型 |
| 退款流 | 当前 refund 走 InMemoryOrderStore.refund(),未用 SQL 路径 | 后续 task: 加 `refund_order()` SQL 路径,同样 session.begin() |
| Webhook 触发 | routes.py 仍走 InMemoryOrderStore | 把 webhook 改成调 `pay_order(existing_order_id=...)` |
| metric / observability | 无 Prometheus 指标 | 加 `pay_order_total{status}` / `pay_order_duration_seconds` |
| Alembic migration | 无 | 当前 Base.metadata.create_all 同步建表 (适合 dev); 生产跑 alembic revision --autogenerate |

---

## 7. 演示 (非必跑,可选)

```python
from billing.atomic_pay import create_or_topup_wallet, pay_order

# 1. 用户充钱
create_or_topup_wallet("u_alice", 10000, "USD")  # $100 余额

# 2. 用户支付订单(原子)
result = pay_order(
    user_id="u_alice",
    plan_id="pro",
    amount_cents=9900,
    currency="USD",
    external_ref="pi_stripe_abc123",
    metadata={"source": "test_card"},
)
print(result.to_dict())
# {
#   "order": {"order_id": "ord_...", "status": "paid", "amount_cents": 9900, ...},
#   "wallet": {"balance_cents": 100, ...},
#   "subscription": {"plan_id": "pro", "status": "active", "current_period_end": "..."},
#   "amount_deducted_cents": 9900,
#   "metadata": {"source": "test_card"}
# }

# 3. 余额不足 → 自动 rollback
try:
    pay_order("u_alice", "pro", amount_cents=99999)
except InsufficientFundsError as e:
    print(e)  # "insufficient funds: user='u_alice' balance=100¢ required=99999¢"
# 钱包余额仍为 100¢ (没扣),无订单,无新订阅
```

---

## 8. 结论

✅ **P0 修复完成** — "扣费 + 订单 + 订阅" 三步现在保证 ALL-or-NOTHING 原子性

✅ **可注入测试** — session_factory 参数化,测试用 SQLite `:memory:`,生产切 Postgres

✅ **业务异常清晰** — `InsufficientFundsError` / `OrderAlreadyPaidError` / `SubscriptionPlanMismatchError` 各自携带诊断字段

✅ **零回归** — 全量 101 个 billing 测试 100% 通过

✅ **可观测** — `TestSessionBeginProof` 三重证明(源码静态分析 + monkeypatch spy + 文档断言),后续重构如果误删 `session.begin()` 立即测试失败

**下一步建议** (不在本任务 scope):
1. 把 `routes.py` webhook 流程改用 `pay_order(existing_order_id=...)` 路径,让 webhook 也走原子事务
2. 加 Alembic migration 把 ORM 模型固化为 schema
3. 加 Prometheus 指标 (`pay_order_total{result=ok|insufficient|plan_mismatch}`)
4. Postgres 部署时改 `with_for_update=True` 加行级锁