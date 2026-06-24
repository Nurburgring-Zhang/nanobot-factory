"""Billing system — usage metering + monthly invoices + tiered pricing (R10.5-Worker-2)

商用计费核心:
- UsageMeter:    in-memory + JSONL persistence usage events per tenant
- TieredPricing: 阶梯定价 (Free / Pro / Enterprise + 用量超额阶梯)
- InvoiceEngine: 月度发票生成 + 多币种 + tax 字段

设计原则:
- 纯 Python + stdlib (无外部依赖)
- 不连数据库 — 通过 UsageStore 接口抽象 (默认 JSONL 文件, 测试可换内存实现)
- 货币用最小单位 cents (整数) 避免浮点误差, 输出时才转为元

Usage (作为库):
    from business.billing import (
        UsageMeter, UsageEvent, TieredPricing, InvoiceEngine,
    )
    meter = UsageMeter(store=JsonlUsageStore("data/usage.jsonl"))
    meter.record(UsageEvent(tenant_id="acme", metric="api_calls", qty=1, ts=...))
    invoice = InvoiceEngine(pricing=TieredPricing.default()).build(
        tenant_id="acme", period="2026-05", events=meter.events_for("acme", "2026-05"),
    )
    print(invoice.total_cents)

Usage (HTTP):
    POST /api/v1/business/billing/usage       记录用量
    POST /api/v1/business/billing/invoice     生成月度发票
    GET  /api/v1/business/billing/usage/{tenant}  查询用量
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Tuple


# ============================================================================
# 1. 用量事件 & 存储抽象
# ============================================================================

@dataclass(frozen=True)
class UsageEvent:
    """单条用量事件 (immutable)."""
    tenant_id: str
    metric: str           # 例: "api_calls" / "storage_gb_hour" / "render_minutes"
    qty: Decimal          # 用量 (Decimal 避免 float 误差)
    unit: str             # 例: "call" / "gb_hour" / "minute"
    ts: float             # unix timestamp (秒)
    event_id: str = field(default_factory=lambda: f"ue_{uuid.uuid4().hex[:16]}")
    metadata: Dict[str, str] = field(default_factory=dict)


class UsageStore(Protocol):
    """用量存储抽象 — 默认 JSONL 文件实现 + 内存实现."""
    def append(self, event: UsageEvent) -> None: ...
    def query(self, tenant_id: str, start_ts: float, end_ts: float) -> List[UsageEvent]: ...


class JsonlUsageStore:
    """JSONL 文件持久化 — 每行一条 JSON, append-only.

    Thread-safe (单进程). 多进程需外部 flock — 商用场景建议迁 Postgres.
    """
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def append(self, event: UsageEvent) -> None:
        line = json.dumps(
            {
                "event_id": event.event_id,
                "tenant_id": event.tenant_id,
                "metric": event.metric,
                "qty": str(event.qty),
                "unit": event.unit,
                "ts": event.ts,
                "metadata": dict(event.metadata),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def query(self, tenant_id: str, start_ts: float, end_ts: float) -> List[UsageEvent]:
        if not self.path.exists():
            return []
        out: List[UsageEvent] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("tenant_id") != tenant_id:
                    continue
                ts = float(rec.get("ts", 0))
                if ts < start_ts or ts >= end_ts:
                    continue
                out.append(UsageEvent(
                    event_id=rec["event_id"],
                    tenant_id=rec["tenant_id"],
                    metric=rec["metric"],
                    qty=Decimal(str(rec["qty"])),
                    unit=rec["unit"],
                    ts=ts,
                    metadata=dict(rec.get("metadata") or {}),
                ))
        return out


class InMemoryUsageStore:
    """测试用内存实现."""
    def __init__(self) -> None:
        self._events: List[UsageEvent] = []

    def append(self, event: UsageEvent) -> None:
        self._events.append(event)

    def query(self, tenant_id: str, start_ts: float, end_ts: float) -> List[UsageEvent]:
        return [
            e for e in self._events
            if e.tenant_id == tenant_id and start_ts <= e.ts < end_ts
        ]


class UsageMeter:
    """用量计门面."""
    def __init__(self, store: UsageStore):
        self.store = store

    def record(self, tenant_id: str, metric: str, qty: Decimal | float | int,
               unit: str = "unit", ts: Optional[float] = None,
               metadata: Optional[Dict[str, str]] = None) -> UsageEvent:
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be non-empty string")
        if not metric:
            raise ValueError("metric must be non-empty")
        qty_d = qty if isinstance(qty, Decimal) else Decimal(str(qty))
        if qty_d < 0:
            raise ValueError("qty must be >= 0")
        evt = UsageEvent(
            tenant_id=tenant_id,
            metric=metric,
            qty=qty_d,
            unit=unit,
            ts=ts if ts is not None else time.time(),
            metadata=dict(metadata or {}),
        )
        self.store.append(evt)
        return evt

    def events_for(self, tenant_id: str, period: str) -> List[UsageEvent]:
        """period = "YYYY-MM"  返回该自然月所有事件 (UTC)."""
        start, end = _month_range(period)
        return self.store.query(tenant_id, start, end)


# ============================================================================
# 2. 阶梯定价
# ============================================================================

@dataclass(frozen=True)
class PricingTier:
    """单个计费档位."""
    name: str               # "free" / "pro" / "enterprise"
    base_fee_cents: int     # 月费 (cents)
    included: Dict[str, Decimal]  # 包含的免费额度 (metric -> qty)
    overage: Dict[str, Tuple[Decimal, int]] = field(default_factory=dict)
    # metric -> (unit_qty, unit_price_cents) 超出 included 后的单价
    # 例: api_calls: (Decimal("100"), 1) = 每 100 次 1 cent
    currency: str = "USD"


@dataclass(frozen=True)
class TieredPricing:
    """多档位定价表."""
    tiers: Dict[str, PricingTier]

    @classmethod
    def default(cls) -> "TieredPricing":
        return cls(tiers={
            "free": PricingTier(
                name="free",
                base_fee_cents=0,
                included={"api_calls": Decimal("1000"),
                         "storage_gb_hour": Decimal("10"),
                         "render_minutes": Decimal("5")},
                overage={},
            ),
            "pro": PricingTier(
                name="pro",
                base_fee_cents=2900,   # $29.00
                included={"api_calls": Decimal("100000"),
                         "storage_gb_hour": Decimal("500"),
                         "render_minutes": Decimal("60")},
                overage={
                    "api_calls": (Decimal("1000"), 5),       # 每 1000 次 5 cents
                    "storage_gb_hour": (Decimal("1"), 10),   # 每 GB·hour 10 cents
                    "render_minutes": (Decimal("1"), 50),    # 每分钟 50 cents
                },
            ),
            "enterprise": PricingTier(
                name="enterprise",
                base_fee_cents=29900,  # $299.00
                included={"api_calls": Decimal("1000000"),
                         "storage_gb_hour": Decimal("5000"),
                         "render_minutes": Decimal("600")},
                overage={
                    "api_calls": (Decimal("10000"), 30),
                    "storage_gb_hour": (Decimal("1"), 5),
                    "render_minutes": (Decimal("1"), 30),
                },
            ),
        })

    def tier(self, name: str) -> PricingTier:
        if name not in self.tiers:
            raise KeyError(f"unknown tier: {name}")
        return self.tiers[name]


# ============================================================================
# 3. 月度发票
# ============================================================================

@dataclass
class LineItem:
    """发票上一行."""
    metric: str
    qty: Decimal
    unit: str
    included_qty: Decimal
    billable_qty: Decimal
    unit_price_cents: int        # 0 表示纯 free
    amount_cents: int            # billable_qty * unit_price_cents (整数)
    description: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "metric": self.metric,
            "qty": str(self.qty),
            "unit": self.unit,
            "included_qty": str(self.included_qty),
            "billable_qty": str(self.billable_qty),
            "unit_price_cents": self.unit_price_cents,
            "amount_cents": self.amount_cents,
            "description": self.description,
        }


@dataclass
class Invoice:
    invoice_id: str
    tenant_id: str
    period: str                  # "YYYY-MM"
    tier: str
    currency: str
    line_items: List[LineItem]
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    issued_at: str               # ISO8601 UTC
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "invoice_id": self.invoice_id,
            "tenant_id": self.tenant_id,
            "period": self.period,
            "tier": self.tier,
            "currency": self.currency,
            "line_items": [li.to_dict() for li in self.line_items],
            "subtotal_cents": self.subtotal_cents,
            "tax_cents": self.tax_cents,
            "total_cents": self.total_cents,
            "issued_at": self.issued_at,
            "metadata": dict(self.metadata),
        }


class InvoiceEngine:
    """发票生成器 — 把 UsageEvent list 按 tier 定价折算成 Invoice."""
    def __init__(self, pricing: TieredPricing, tax_rate: Decimal = Decimal("0.0")):
        self.pricing = pricing
        self.tax_rate = tax_rate  # 0.0 - 1.0

    def build(self, tenant_id: str, period: str, tier: str,
              events: Iterable[UsageEvent],
              currency: Optional[str] = None,
              metadata: Optional[Dict[str, str]] = None) -> Invoice:
        t = self.pricing.tier(tier)
        # 聚合: metric -> (qty, unit)
        agg: Dict[str, Tuple[Decimal, str]] = {}
        for e in events:
            q, u = agg.get(e.metric, (Decimal("0"), e.unit))
            agg[e.metric] = (q + e.qty, u)

        line_items: List[LineItem] = []
        subtotal = int(t.base_fee_cents)

        for metric, (qty, unit) in sorted(agg.items()):
            included = t.included.get(metric, Decimal("0"))
            overage = t.overage.get(metric)
            billable = max(Decimal("0"), qty - included)
            unit_price = 0
            amount = 0
            if overage and billable > 0:
                unit_qty, unit_price_cents = overage
                # billable 按 unit_qty 向上取整计费
                units_consumed = _ceil_div(billable, unit_qty)
                amount = int(units_consumed) * int(unit_price_cents)
                unit_price = int(unit_price_cents)
            line_items.append(LineItem(
                metric=metric,
                qty=qty,
                unit=unit,
                included_qty=included,
                billable_qty=billable,
                unit_price_cents=unit_price,
                amount_cents=amount,
                description=f"{metric}: included={included}{unit}, billable={billable}{unit}",
            ))
            subtotal += amount

        # tax 用 Decimal 计算, 再 round 到 cents
        tax_dec = (Decimal(subtotal) * self.tax_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        tax_cents = int(tax_dec)
        total_cents = subtotal + tax_cents
        currency = currency or t.currency

        return Invoice(
            invoice_id=f"inv_{period}_{tenant_id}_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            period=period,
            tier=tier,
            currency=currency,
            line_items=line_items,
            subtotal_cents=subtotal,
            tax_cents=tax_cents,
            total_cents=total_cents,
            issued_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )

    def export_csv(self, invoice: Invoice) -> str:
        """发票 CSV 序列化 — 用于导出."""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["metric", "qty", "unit", "included_qty", "billable_qty",
                    "unit_price_cents", "amount_cents", "description"])
        for li in invoice.line_items:
            w.writerow([
                li.metric, str(li.qty), li.unit,
                str(li.included_qty), str(li.billable_qty),
                li.unit_price_cents, li.amount_cents, li.description,
            ])
        return buf.getvalue()


# ============================================================================
# 工具函数
# ============================================================================

def _month_range(period: str) -> Tuple[float, float]:
    """period = "YYYY-MM"  -> (start_ts, end_ts) UTC."""
    try:
        dt = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(f"invalid period {period!r}: expected YYYY-MM") from e
    if dt.month == 12:
        nxt = dt.replace(year=dt.year + 1, month=1)
    else:
        nxt = dt.replace(month=dt.month + 1)
    return dt.timestamp(), nxt.timestamp()


def _ceil_div(a: Decimal, b: Decimal) -> Decimal:
    """向上取整除法 — a/b 向上."""
    if b <= 0:
        raise ValueError("divisor must be > 0")
    q = a / b
    return int(q) + (1 if q > int(q) else 0) if isinstance(q, Decimal) else q


def utc_now_period() -> str:
    """返回当前 UTC 时间的 "YYYY-MM" 期间字符串."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


__all__ = [
    "UsageEvent", "UsageStore", "JsonlUsageStore", "InMemoryUsageStore",
    "UsageMeter",
    "PricingTier", "TieredPricing",
    "LineItem", "Invoice", "InvoiceEngine",
    "utc_now_period",
]