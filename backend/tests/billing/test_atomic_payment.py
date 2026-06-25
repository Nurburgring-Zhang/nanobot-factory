"""P6-Fix-C-3: Atomic payment tests — verify rollback semantics.

测试目标
--------
1. **正常路径**: 一次 ``pay_order()`` 调用后:
   - 钱包余额被正确扣减
   - 订单状态变成 ``paid``
   - 订阅被创建(或扩展)
   - 三个动作都在同一个 ``session.begin()`` 事务里

2. **失败路径**: 在 ``pay_order()`` 过程中注入异常 → 整笔事务应该
   100% rollback:
   - 钱包余额未变
   - 订单未写入(或保持 pending)
   - 订阅未创建/未变更
   - 没有部分写入

3. **业务异常** (专用异常类型):
   - ``InsufficientFundsError`` → rollback, 余额未变
   - ``OrderAlreadyPaidError`` → rollback
   - ``SubscriptionPlanMismatchError`` → rollback

4. **幂等性**:
   - 重复 ``pay_order`` 同一 user 在 first commit 后正确反映余额
   - create_or_topup_wallet 是幂等的 (create + add)

Tests run against ``sqlite:///:memory:`` to keep them fast and hermetic.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from billing.db import (
    Base, BillingOrder, BillingSubscription, Wallet,
)
from billing.atomic_pay import (
    InsufficientFundsError, NoopPayHook, OrderAlreadyPaidError,
    PayHook, PayOrderResult, SubscriptionPlanMismatchError,
    create_or_topup_wallet, pay_order,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def session_factory():
    """Build a fresh :memory: SQLite session factory for each test."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    sf = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    yield sf
    eng.dispose()


@pytest.fixture
def funded_user(session_factory):
    """Wallet with $100 (=10000¢) balance for user 'u_alice'."""
    return create_or_topup_wallet("u_alice", 10000, "USD",
                                  session_factory=session_factory)


# ─── Test class 1: happy path ────────────────────────────────────────────────

class TestPayOrderHappyPath:
    """1. 正常路径 — 扣费 + 订单 + 订阅三步在同一事务。"""

    def test_001_first_payment_creates_order_and_subscription(
        self, session_factory, funded_user,
    ):
        # Wallet pre-seeded with 10000¢; pay 9900¢ for plan 'pro'
        result = pay_order(
            user_id="u_alice",
            plan_id="pro",
            amount_cents=9900,
            currency="USD",
            payment_method="mock",
            session_factory=session_factory,
        )
        # ── verify wallet deducted ──
        assert result.wallet.balance_cents == 100  # 10000 - 9900
        assert result.wallet.user_id == "u_alice"
        # ── verify order paid ──
        assert result.order.status == "paid"
        assert result.order.amount_cents == 9900
        assert result.order.user_id == "u_alice"
        assert result.order.plan_id == "pro"
        assert result.order.paid_at is not None
        assert result.order.fulfilled_at is not None
        assert result.amount_deducted_cents == 9900
        # ── verify subscription created ──
        assert result.subscription is not None
        assert result.subscription.user_id == "u_alice"
        assert result.subscription.plan_id == "pro"
        assert result.subscription.status == "active"
        # ── verify subscription period ≈ now + 30 days ──
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        end = result.subscription.current_period_end
        delta = (end - now).total_seconds()
        assert abs(delta - 30 * 86400) < 5

    def test_002_second_payment_extends_subscription(
        self, session_factory, funded_user,
    ):
        pay_order(user_id="u_alice", plan_id="pro", amount_cents=9900,
                  currency="USD", session_factory=session_factory)
        create_or_topup_wallet("u_alice", 20000, "USD",
                               session_factory=session_factory)
        result = pay_order(user_id="u_alice", plan_id="pro", amount_cents=5000,
                           currency="USD", session_factory=session_factory)
        assert result.wallet.balance_cents == (10000 + 20000 - 9900 - 5000)
        assert result.subscription.plan_id == "pro"
        assert result.subscription.status == "active"

    def test_003_payment_with_external_ref(self, session_factory, funded_user):
        result = pay_order(
            user_id="u_alice", plan_id="pro", amount_cents=1000,
            currency="USD", external_ref="pi_stripe_abc123",
            session_factory=session_factory,
        )
        assert result.order.external_ref == "pi_stripe_abc123"
        assert result.wallet.balance_cents == 9000

    def test_004_payment_with_metadata(self, session_factory, funded_user):
        result = pay_order(
            user_id="u_alice", plan_id="pro", amount_cents=500,
            currency="USD",
            metadata={"source": "test_card", "campaign": "launch2026"},
            session_factory=session_factory,
        )
        meta = json.loads(result.order.metadata_json)
        assert meta["source"] == "test_card"
        assert meta["campaign"] == "launch2026"


# ─── Test class 2: rollback on failure ───────────────────────────────────────

class TestPayOrderRollback:
    """2. 失败路径 — 中途异常 → 全部 rollback。"""

    def test_005_insufficient_funds_rolls_back_everything(self, session_factory):
        create_or_topup_wallet("u_bob", 1000, "USD",
                               session_factory=session_factory)
        with pytest.raises(InsufficientFundsError) as exc_info:
            pay_order(user_id="u_bob", plan_id="pro", amount_cents=5000,
                      currency="USD", session_factory=session_factory)
        assert exc_info.value.balance_cents == 1000
        assert exc_info.value.required_cents == 5000
        # ── verify NOTHING was written ──
        with session_factory() as s:
            w = s.get(Wallet, "u_bob")
            assert w.balance_cents == 1000, "wallet must not be deducted"
            orders = s.query(BillingOrder).filter_by(user_id="u_bob").all()
            assert orders == [], "no order must be created"
            subs = s.query(BillingSubscription).filter_by(
                user_id="u_bob").all()
            assert subs == [], "no subscription must be created"

    def test_006_wallet_not_found_rolls_back(self, session_factory):
        with pytest.raises(KeyError) as exc_info:
            pay_order(user_id="u_charlie", plan_id="pro", amount_cents=1000,
                      currency="USD", session_factory=session_factory)
        assert "wallet not found" in str(exc_info.value)
        with session_factory() as s:
            orders = s.query(BillingOrder).filter_by(user_id="u_charlie").all()
            assert orders == []
            subs = s.query(BillingSubscription).filter_by(
                user_id="u_charlie").all()
            assert subs == []

    def test_007_existing_order_already_paid_rolls_back(
        self, session_factory, funded_user,
    ):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with session_factory() as s:
            with s.begin():
                o = BillingOrder(
                    order_id="ord_existing_paid",
                    user_id="u_alice", plan_id="pro",
                    amount_cents=1000, currency="USD",
                    status="paid", payment_method="mock",
                    created_at=now, paid_at=now, fulfilled_at=now,
                    metadata_json="{}",
                )
                s.add(o)
        with pytest.raises(OrderAlreadyPaidError) as exc_info:
            pay_order(
                user_id="u_alice", plan_id="pro", amount_cents=1000,
                currency="USD", external_ref="pi_replay",
                existing_order_id="ord_existing_paid",
                session_factory=session_factory,
            )
        assert exc_info.value.current_status == "paid"
        with session_factory() as s:
            w = s.get(Wallet, "u_alice")
            assert w.balance_cents == 10000, "balance must remain unchanged"

    def test_008_subscription_plan_mismatch_rolls_back(self, session_factory):
        create_or_topup_wallet("u_dan", 10000, "USD",
                               session_factory=session_factory)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with session_factory() as s:
            with s.begin():
                sub = BillingSubscription(
                    subscription_id="sub_dan",
                    user_id="u_dan", plan_id="starter", status="active",
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                    cancel_at_period_end=False,
                    created_at=now, updated_at=now,
                )
                s.add(sub)
        with pytest.raises(SubscriptionPlanMismatchError):
            pay_order(user_id="u_dan", plan_id="pro", amount_cents=2000,
                      currency="USD", session_factory=session_factory)
        with session_factory() as s:
            w = s.get(Wallet, "u_dan")
            assert w.balance_cents == 10000, "balance must not be deducted"
            sub = s.get(BillingSubscription, "sub_dan")
            assert sub.plan_id == "starter", "sub plan must not change"
            assert sub.status == "active"
            orders = s.query(BillingOrder).filter_by(user_id="u_dan").all()
            assert orders == [], "no new order must be created"

    def test_009_hook_exception_rolls_back_everything(
        self, session_factory, funded_user,
    ):
        """Hook raising → transaction rolls back (no partial commit)."""

        class FailingHook(NoopPayHook):
            def on_subscription_extended(
                self, subscription, order,
            ) -> None:
                raise RuntimeError("simulated invoice-service-down")

        with pytest.raises(RuntimeError, match="invoice-service-down"):
            pay_order(
                user_id="u_alice", plan_id="pro", amount_cents=2000,
                currency="USD", session_factory=session_factory,
                hook=FailingHook(),
            )
        with session_factory() as s:
            w = s.get(Wallet, "u_alice")
            assert w.balance_cents == 10000, (
                "wallet must not be deducted if hook fails"
            )
            orders = s.query(BillingOrder).filter_by(user_id="u_alice").all()
            assert orders == [], "no order must be persisted"
            subs = s.query(BillingSubscription).filter_by(
                user_id="u_alice").all()
            assert subs == [], "no subscription must be persisted"


# ─── Test class 3: business invariants ──────────────────────────────────────

class TestPayOrderInvariants:
    """3. 业务不变量。"""

    def test_010_invalid_amount_rejected(self, session_factory, funded_user):
        with pytest.raises(ValueError, match="amount_cents must be > 0"):
            pay_order(user_id="u_alice", plan_id="pro", amount_cents=0,
                      currency="USD", session_factory=session_factory)
        with pytest.raises(ValueError, match="amount_cents must be > 0"):
            pay_order(user_id="u_alice", plan_id="pro", amount_cents=-100,
                      currency="USD", session_factory=session_factory)

    def test_011_invalid_currency_rejected(self, session_factory, funded_user):
        with pytest.raises(ValueError, match="unsupported currency"):
            pay_order(user_id="u_alice", plan_id="pro", amount_cents=100,
                      currency="EUR", session_factory=session_factory)

    def test_012_exact_balance_payment_succeeds(self, session_factory):
        create_or_topup_wallet("u_frank", 5000, "USD",
                               session_factory=session_factory)
        result = pay_order(user_id="u_frank", plan_id="pro", amount_cents=5000,
                           currency="USD", session_factory=session_factory)
        assert result.wallet.balance_cents == 0
        assert result.order.status == "paid"

    def test_013_wallet_currency_mismatch_rolls_back(self, session_factory):
        create_or_topup_wallet("u_grace", 10000, "USD",
                               session_factory=session_factory)
        with pytest.raises(ValueError, match="wallet currency mismatch"):
            pay_order(user_id="u_grace", plan_id="pro", amount_cents=1000,
                      currency="CNY", session_factory=session_factory)
        with session_factory() as s:
            w = s.get(Wallet, "u_grace")
            assert w.balance_cents == 10000


# ─── Test class 4: wallet top-up helpers ────────────────────────────────────

class TestCreateOrTopupWallet:
    def test_014_create_when_missing(self, session_factory):
        w = create_or_topup_wallet("u_new", 500, "USD",
                                   session_factory=session_factory)
        assert w.balance_cents == 500

    def test_015_topup_when_existing(self, session_factory):
        create_or_topup_wallet("u_helen", 200, "USD",
                               session_factory=session_factory)
        w = create_or_topup_wallet("u_helen", 300, "USD",
                                   session_factory=session_factory)
        assert w.balance_cents == 500

    def test_016_topup_negative_rejected(self, session_factory):
        with pytest.raises(ValueError):
            create_or_topup_wallet("u_ivan", -100, "USD",
                                   session_factory=session_factory)


# ─── Test class 5: explicit session.begin() proof ────────────────────────────

class TestSessionBeginProof:
    """Confirm pay_order actually uses session.begin() — not just begin_nested."""

    def test_017_pay_order_source_uses_session_begin(self, session_factory):
        """Static check — pay_order source contains ``with session.begin():``."""
        import inspect
        from billing import atomic_pay
        src = inspect.getsource(atomic_pay.pay_order)
        assert "session.begin()" in src, (
            "pay_order must use the 'with session.begin():' context manager "
            "so SQLAlchemy auto-commits on exit and rolls back on exception"
        )
        assert "balance - int(amount_cents)" in src, (
            "pay_order must deduct wallet inside the same transaction"
        )
        assert "session.add(order)" in src, (
            "pay_order must create the order inside the same transaction"
        )

    def test_018_create_or_topup_uses_session_begin(self, session_factory):
        import inspect
        from billing import atomic_pay
        src = inspect.getsource(atomic_pay.create_or_topup_wallet)
        assert "session.begin()" in src, (
            "create_or_topup_wallet must use 'with session.begin():' context"
        )

    def test_019_session_begin_invoked_at_runtime(
        self, session_factory, funded_user, monkeypatch,
    ):
        """At runtime, ``Session.begin`` is called by pay_order."""
        from sqlalchemy.orm import Session
        called = {"count": 0}
        original_begin = Session.begin

        def spy(self, *args, **kwargs):
            called["count"] += 1
            return original_begin(self, *args, **kwargs)

        monkeypatch.setattr(Session, "begin", spy)
        pay_order(user_id="u_alice", plan_id="pro", amount_cents=1000,
                  currency="USD", session_factory=session_factory)
        assert called["count"] >= 1, (
            "pay_order must invoke session.begin() at runtime "
            f"(got {called['count']})"
        )