"""SQLAlchemy ORM models + session factory for the billing module.

P6-Fix-C-3: 添加 SQLAlchemy ORM 层,让 ``pay_order()`` 可以在 ``session.begin()``
事务中原子地完成「扣费 + 创建订单 + 更新订阅」三步。

设计原则:
- **单 Base,多 model** — 一个 ``declarative_base`` 同时承载 Wallet / Order / Subscription。
- **Idempotent create_all** — ``init_db()`` 可重复调用 (开发/测试友好)。
- **SQLite / PostgreSQL 双兼容** — 默认 SQLite (``backend/data/billing.db``),
  生产可通过 ``BILLING_DB_URL`` 环境变量切换到 Postgres。
- **SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)**
  遵循项目已有的 imdf/db.py 模式。
- **显式 ``session.begin()`` 上下文管理器** — 这是 SQLAlchemy 2.0 推荐的「自动
  commit-on-exit / rollback-on-exception」事务语法。
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ─── 1. Base ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Declarative base for all billing ORM models."""


# ─── 2. Models ────────────────────────────────────────────────────────────────

class Wallet(Base):
    """用户钱包(余额以「分」为单位,避免浮点)。"""
    __tablename__ = "billing_wallets"

    user_id = Column(String(64), primary_key=True)
    balance_cents = Column(BigInteger, nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="USD")
    created_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "balance_cents": int(self.balance_cents),
            "currency": self.currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BillingOrder(Base):
    """SQL mirror of the dataclass :class:`billing.orders.Order`."""
    __tablename__ = "billing_orders"

    order_id = Column(String(40), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    plan_id = Column(String(40), nullable=False, index=True)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="USD")
    status = Column(String(20), nullable=False, default="pending", index=True)
    payment_method = Column(String(20), nullable=False, default="mock")
    external_ref = Column(String(120), nullable=True, default="")
    created_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    paid_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    refund_reason = Column(Text, nullable=True, default="")
    metadata_json = Column(Text, nullable=False, default="{}")

    def to_dict(self) -> dict:
        import json
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "amount_cents": int(self.amount_cents),
            "currency": self.currency,
            "status": self.status,
            "payment_method": self.payment_method,
            "external_ref": self.external_ref,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
            "refunded_at": self.refunded_at.isoformat() if self.refunded_at else None,
            "refund_reason": self.refund_reason,
            "metadata": json.loads(self.metadata_json or "{}"),
        }


class BillingSubscription(Base):
    """SQL mirror of the dataclass :class:`billing.subscriptions.Subscription`."""
    __tablename__ = "billing_subscriptions"

    subscription_id = Column(String(40), primary_key=True)
    user_id = Column(String(64), nullable=False, unique=True, index=True)
    plan_id = Column(String(40), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False, index=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def to_dict(self) -> dict:
        return {
            "subscription_id": self.subscription_id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "current_period_start": (
                self.current_period_start.isoformat()
                if self.current_period_start else None),
            "current_period_end": (
                self.current_period_end.isoformat()
                if self.current_period_end else None),
            "cancel_at_period_end": bool(self.cancel_at_period_end),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─── 3. Engine + SessionLocal ─────────────────────────────────────────────────

def _default_db_url() -> str:
    """Default DB URL: SQLite file under backend/data/billing.db."""
    base = Path(__file__).resolve().parent.parent  # backend/
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "billing.db"
    return f"sqlite:///{db_path}"


# Cache the engine in a thread-safe singleton.
_engine_lock = threading.Lock()
_engine_instance: Optional["object"] = None  # SQLAlchemy Engine


def get_engine(url: Optional[str] = None):
    """Get (or build) the SQLAlchemy engine. Thread-safe singleton."""
    global _engine_instance
    target_url = url or os.environ.get("BILLING_DB_URL") or _default_db_url()
    if _engine_instance is not None:
        return _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            connect_args = {}
            # SQLite needs check_same_thread=False for in-process TestClient reuse
            if target_url.startswith("sqlite"):
                connect_args = {"check_same_thread": False}
            _engine_instance = create_engine(
                target_url,
                connect_args=connect_args,
                pool_pre_ping=True,
                future=True,
            )
    return _engine_instance


# SessionLocal factory — bind happens lazily so tests can swap URL.
_SessionLocal: Optional[sessionmaker] = None


def get_session_factory(url: Optional[str] = None) -> sessionmaker:
    """Get a sessionmaker bound to the (current) engine.

    A fresh ``sessionmaker`` is built each call when ``url`` is provided so tests
    can run against :memory: SQLite without polluting the global singleton.
    """
    eng = get_engine(url) if url else get_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)


def reset_engine() -> None:
    """Test helper — drop cached engine so a new URL takes effect."""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is not None:
            try:
                _engine_instance.dispose()
            except Exception:
                pass
        _engine_instance = None


# ─── 4. DDL helpers ───────────────────────────────────────────────────────────

def init_db(url: Optional[str] = None) -> None:
    """Create all tables. Idempotent."""
    eng = get_engine(url) if url else get_engine()
    Base.metadata.create_all(eng)


def drop_db(url: Optional[str] = None) -> None:
    """Drop all tables (DANGER). Test helper."""
    eng = get_engine(url) if url else get_engine()
    Base.metadata.drop_all(eng)


__all__ = [
    "Base",
    "Wallet", "BillingOrder", "BillingSubscription",
    "get_engine", "get_session_factory", "reset_engine",
    "init_db", "drop_db",
]