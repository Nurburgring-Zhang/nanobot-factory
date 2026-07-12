"""CDP Advanced Billing service (V5 Chapter 22 / §13.4 — CDP Advanced Billing).

Public surface:
    CDPBillingService       — async billing engine (track_usage / calculate_invoice / generate_invoice_pdf / list_invoices)
    default_tiers()         — 3-tier volume-discount ladder (Tier 1 / 2 / 3)
    default_pricing_rules() — sensible default per-metric pricing (data / api / render)

Storage is in-memory by default, keyed by tenant_id. Use `InMemoryCdpBillingStore`
directly in tests. The service is stateless beyond a single `self.store` reference.

Design notes:
    * All amounts are `Decimal` (no float drift on rounding to cents).
    * `calculate_invoice` first groups UsageRecords by metric, then applies each
      metric's PricingRule (included_qty deducted from billable), then applies
      the matching BillingTier's discount_pct to the running subtotal.
    * PDF generation: tries reportlab, falls back to a plain HTML/UTF-8 bytes
      invoice (browsers / preview apps open it directly).
    * No global state; instantiate one CDPBillingService per process / tenant pool.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Protocol

from .cdp_billing_schemas import (
    BillingTier,
    Invoice,
    InvoiceLineItem,
    PricingRule,
    UsageRecord,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Storage protocol + default in-memory implementation
# ────────────────────────────────────────────────────────────────────────────


class CdpBillingStore(Protocol):
    async def record(self, rec: UsageRecord) -> None: ...
    async def list_usage(
        self, tenant_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[UsageRecord]: ...
    async def save_invoice(self, invoice: Invoice) -> None: ...
    async def list_invoices(self, tenant_id: str, limit: int = 20) -> List[Invoice]: ...


@dataclass
class InMemoryCdpBillingStore:
    """Thread-safe + asyncio-safe in-memory store.

    Suitable for tests + single-process dev. In production swap for SQL/SQLite/Postgres.
    """

    _usage: Dict[str, List[UsageRecord]] = field(default_factory=dict)
    _invoices: Dict[str, List[Invoice]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    async def record(self, rec: UsageRecord) -> None:
        with self._lock:
            self._usage.setdefault(rec.tenant_id, []).append(rec)

    async def list_usage(
        self, tenant_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[UsageRecord]:
        with self._lock:
            rows = list(self._usage.get(tenant_id, []))
        out: List[UsageRecord] = []
        for r in rows:
            ts = r.timestamp
            if start and ts < start:
                continue
            if end and ts >= end:
                continue
            out.append(r)
        return out

    async def save_invoice(self, invoice: Invoice) -> None:
        with self._lock:
            self._invoices.setdefault(invoice.tenant_id, []).append(invoice)

    async def list_invoices(self, tenant_id: str, limit: int = 20) -> List[Invoice]:
        with self._lock:
            rows = list(self._invoices.get(tenant_id, []))
        # chronological: earliest first; latest entries at the tail
        rows.sort(key=lambda inv: inv.generated_at)
        return rows[: max(limit, 0)]


# ────────────────────────────────────────────────────────────────────────────
# Default pricing — 3-tier volume discount ladder (Chapter 22 / §13.4)
# ────────────────────────────────────────────────────────────────────────────


def default_tiers() -> List[BillingTier]:
    """Return 3-tier discount ladder used by CDP billing (V5 §13.4 / Chapter 22).

    Tier resolution is driven by the **data_gb** metric specifically (the
    primary storage / data-volume indicator for the tenant): tier_1 covers
    0-100 GB, tier_2 covers 100-1000 GB, tier_3 covers 1000+ GB.  Other
    metrics (api_calls, render_minutes) contribute to the line-item
    subtotal but do NOT move the tenant between tiers — only data_gb does.
    """
    return [
        BillingTier(
            name="tier_1",
            min_units=Decimal("0"),
            discount_pct=Decimal("0"),
            description="Starter — 0-100 GB data, no volume discount",
        ),
        BillingTier(
            name="tier_2",
            min_units=Decimal("100"),
            discount_pct=Decimal("5"),
            description="Growth — 100-1000 GB data, 5% volume discount",
        ),
        BillingTier(
            name="tier_3",
            min_units=Decimal("1000"),
            discount_pct=Decimal("15"),
            description="Scale — 1000+ GB data, 15% volume discount",
        ),
    ]


def default_pricing_rules() -> Dict[str, PricingRule]:
    """Sensible default per-metric pricing rules used by CDP billing.

    Per V5 §13.4 / Chapter 22 spec the data_gb and api_calls metrics have
    NO included free tier — every GB / every API call is billable at the
    published unit price.  render_minutes keeps a small free tier (30 min)
    so renderer bursts are not punitive.
    """
    return {
        "data_gb": PricingRule(
            metric="data_gb",
            unit="GB",
            unit_price=Decimal("0.10"),
            included_qty=Decimal("0"),
            currency="USD",
            description="Data storage, $0.10/GB",
        ),
        "api_calls": PricingRule(
            metric="api_calls",
            unit="call",
            unit_price=Decimal("0.005"),
            included_qty=Decimal("0"),
            currency="USD",
            description="API requests, $0.005 per call",
        ),
        "render_minutes": PricingRule(
            metric="render_minutes",
            unit="minute",
            unit_price=Decimal("0.50"),
            included_qty=Decimal("30"),
            currency="USD",
            description="Rendering, $0.50/min beyond first 30 minutes",
        ),
    }


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _quantize(amount: Decimal, places: int = 2) -> Decimal:
    """Round to `places` decimal places using banker-safe HALF_UP."""
    q = Decimal("1") if places == 0 else Decimal(10) ** -places
    return amount.quantize(q, rounding=ROUND_HALF_UP)


def _resolve_tier(tiers: List[BillingTier], aggregate_units: Decimal) -> Optional[BillingTier]:
    """Find the best tier whose min_units threshold is satisfied.

    Tiers should be passed in any order; we sort by min_units asc and return the
    last qualifying one (highest discount).  Returns None if no tier qualifies.
    """
    sorted_tiers = sorted(tiers, key=lambda t: t.min_units)
    chosen: Optional[BillingTier] = None
    for t in sorted_tiers:
        if aggregate_units >= t.min_units:
            chosen = t
        else:
            break
    return chosen


# ────────────────────────────────────────────────────────────────────────────
# CDPBillingService — the main public service
# ────────────────────────────────────────────────────────────────────────────


class CDPBillingService:
    """Customer Data Platform advanced billing service.

    Async API for tenant usage tracking, multi-tier invoice calculation,
    PDF generation, and invoice history.
    """

    def __init__(
        self,
        store: Optional[CdpBillingStore] = None,
        pricing_rules: Optional[Dict[str, PricingRule]] = None,
        tiers: Optional[List[BillingTier]] = None,
    ) -> None:
        self.store: CdpBillingStore = store or InMemoryCdpBillingStore()
        self.pricing_rules: Dict[str, PricingRule] = (
            pricing_rules if pricing_rules is not None else default_pricing_rules()
        )
        self.tiers: List[BillingTier] = tiers if tiers is not None else default_tiers()

    # ─────────────────────────────────────────────────────────────────────
    # track_usage
    # ─────────────────────────────────────────────────────────────────────

    async def track_usage(
        self,
        tenant_id: str,
        metric: str,
        value: float,
        unit: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record a metered usage event for `tenant_id`.

        Args:
            tenant_id: Tenant identifier (non-empty).
            metric:    Metric name; should match one of `pricing_rules`.
            value:     Quantity consumed (>= 0).
            unit:      Optional unit override; defaults to rule's unit or "unit".
            timestamp: Optional event time (UTC). Defaults to `datetime.utcnow()`.
            metadata:  Optional free-form dict.

        Returns:
            The persisted UsageRecord.
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if not metric or not metric.strip():
            raise ValueError("metric must be non-empty")
        d_value = Decimal(str(value))
        if d_value < 0:
            raise ValueError("value must be >= 0")
        rule = self.pricing_rules.get(metric)
        eff_unit = unit or (rule.unit if rule else "unit")
        rec = UsageRecord(
            tenant_id=tenant_id.strip(),
            metric=metric.strip(),
            value=d_value,
            unit=eff_unit,
            timestamp=timestamp if timestamp is not None else datetime.utcnow(),
            metadata=dict(metadata or {}),
        )
        await self.store.record(rec)
        return rec

    # ─────────────────────────────────────────────────────────────────────
    # calculate_invoice
    # ─────────────────────────────────────────────────────────────────────

    async def calculate_invoice(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
    ) -> Invoice:
        """Build (and persist) an Invoice covering `[period_start, period_end)`.

        Steps:
            1. pull UsageRecord list (filtered by tenant + period)
            2. group by metric, sum value per metric
            3. for each known metric: deduct included_qty, compute billable * unit_price
            4. aggregate subtotal; pick BillingTier by total qty; apply tier discount
            5. persist Invoice; return it
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if period_end <= period_start:
            raise ValueError("period_end must be after period_start")

        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.min.time())

        records = await self.store.list_usage(tenant_id, start=start_dt, end=end_dt)

        # 1) aggregate per-metric qty
        qty_by_metric: Dict[str, Decimal] = {}
        for r in records:
            qty_by_metric[r.metric] = qty_by_metric.get(r.metric, Decimal("0")) + r.value

        # 2) build line items per known pricing rule (skip unknown metrics)
        line_items: List[InvoiceLineItem] = []
        subtotal = Decimal("0")
        for metric, qty in qty_by_metric.items():
            rule = self.pricing_rules.get(metric)
            if rule is None:
                # unknown metric — skip from billing (recorded but not charged)
                continue
            included_qty = rule.included_qty
            billable_qty = max(qty - included_qty, Decimal("0"))
            base_amount = _quantize(billable_qty * rule.unit_price, 4)
            line_items.append(
                InvoiceLineItem(
                    metric=metric,
                    description=rule.description,
                    qty=_quantize(qty, 4),
                    included_qty=_quantize(included_qty, 4),
                    billable_qty=_quantize(billable_qty, 4),
                    unit_price=rule.unit_price,
                    base_amount=base_amount,
                    tier_discount=Decimal("0"),  # filled in after tier resolution
                    amount=base_amount,  # placeholder
                )
            )
            subtotal += base_amount

        subtotal = _quantize(subtotal, 2)

        # 3) tier resolution based on **data_gb** qty (per V5 §13.4 spec).
        #    Other metrics contribute to the subtotal but do not move the tenant
        #    between tiers — only data_gb does.
        tier_metric_qty = qty_by_metric.get("data_gb", Decimal("0"))
        aggregate_units = sum(qty_by_metric.values(), Decimal("0"))
        tier = _resolve_tier(self.tiers, tier_metric_qty)

        tier_discount_total = Decimal("0")
        if tier and tier.discount_pct > 0:
            # distribute tier discount proportionally across lines
            for li in line_items:
                if subtotal > 0:
                    share = (li.base_amount / subtotal) * (subtotal * tier.discount_pct / Decimal("100"))
                else:
                    share = Decimal("0")
                li.tier_discount = _quantize(share, 2)
                li.amount = _quantize(li.base_amount - li.tier_discount, 2)
                tier_discount_total += li.tier_discount
            tier_discount_total = _quantize(tier_discount_total, 2)
        else:
            # no tier discount — but still quantity-discount the line itself
            for li in line_items:
                li.tier_discount = Decimal("0")
                li.amount = li.base_amount

        # 4) finalize totals (model's tax slot stays 0 for now)
        total = _quantize(subtotal - tier_discount_total, 2)

        invoice = Invoice(
            tenant_id=tenant_id.strip(),
            period_start=period_start,
            period_end=period_end,
            currency="USD",
            line_items=line_items,
            subtotal=subtotal,
            tier_discount_total=tier_discount_total,
            tax=Decimal("0"),
            total=total,
            tier_applied=tier.name if tier else None,
            generated_at=datetime.utcnow(),
            metadata={"aggregate_units": str(_quantize(aggregate_units, 4))},
        )
        await self.store.save_invoice(invoice)
        return invoice

    # ─────────────────────────────────────────────────────────────────────
    # generate_invoice_pdf
    # ─────────────────────────────────────────────────────────────────────

    async def generate_invoice_pdf(self, invoice: Invoice) -> bytes:
        """Render the invoice as PDF bytes (reportlab) or HTML fallback.

        Both formats return non-empty bytes; reportlab outputs real `%PDF-`
        while the HTML fallback is rendered with an HTML5 doctype + CSS so it
        previews nicely in a browser.
        """
        # Try reportlab first — the canonical PDF generator.
        try:
            from reportlab.lib.pagesizes import LETTER  # type: ignore
            from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
            from reportlab.platypus import (  # type: ignore
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
            from reportlab.lib import colors  # type: ignore

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=LETTER)
            styles = getSampleStyleSheet()
            story: List[Any] = []

            story.append(Paragraph(f"<b>CDP Invoice {invoice.id}</b>", styles["Title"]))
            story.append(Spacer(1, 12))
            story.append(
                Paragraph(
                    f"Tenant: <b>{invoice.tenant_id}</b>  &nbsp;&nbsp; "
                    f"Period: {invoice.period_start.isoformat()} → {invoice.period_end.isoformat()}",
                    styles["Normal"],
                )
            )
            story.append(
                Paragraph(
                    f"Generated: {invoice.generated_at.isoformat()}  &nbsp;&nbsp; "
                    f"Tier: {invoice.tier_applied or 'none'}",
                    styles["Normal"],
                )
            )
            story.append(Spacer(1, 12))

            data = [["Metric", "Qty", "Included", "Billable", "Unit Price", "Base", "Tier Disc.", "Amount"]]
            for li in invoice.line_items:
                data.append([
                    li.metric,
                    f"{li.qty}",
                    f"{li.included_qty}",
                    f"{li.billable_qty}",
                    f"{li.unit_price}",
                    f"{li.base_amount}",
                    f"{li.tier_discount}",
                    f"{li.amount}",
                ])
            if not invoice.line_items:
                data.append(["(no usage)", "", "", "", "", "", "", ""])

            table = Table(data, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 18))
            story.append(Paragraph(f"Subtotal: <b>${invoice.subtotal}</b>", styles["Normal"]))
            story.append(Paragraph(f"Tier Discount: ${invoice.tier_discount_total}", styles["Normal"]))
            story.append(Paragraph(f"Tax: ${invoice.tax}", styles["Normal"]))
            story.append(Paragraph(f"<b>Total: ${invoice.total}</b>", styles["Heading2"]))

            doc.build(story)
            return buf.getvalue()
        except ImportError:
            logger.warning("reportlab not available; falling back to HTML invoice")

        # HTML fallback — valid HTML5 document with inline CSS
        rows_html = "".join(
            f"<tr><td>{li.metric}</td><td>{li.qty}</td><td>{li.included_qty}</td>"
            f"<td>{li.billable_qty}</td><td>${li.unit_price}</td><td>${li.base_amount}</td>"
            f"<td>${li.tier_discount}</td><td>${li.amount}</td></tr>"
            for li in invoice.line_items
        ) or '<tr><td colspan="8" style="text-align:center;color:#888">No usage</td></tr>'

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>CDP Invoice {invoice.id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           margin: 32px; color: #1f2937; }}
    h1   {{ margin-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 18px 0; font-size: 13px; }}
    th, td {{ padding: 6px 8px; border: 1px solid #cbd5e1; text-align: left; }}
    th {{ background: #e5e7eb; font-weight: 600; }}
    .totals p {{ margin: 4px 0; }}
    .totals strong {{ font-size: 16px; }}
    .meta {{ color: #6b7280; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>CDP Invoice {invoice.id}</h1>
  <p class="meta">Tenant <b>{invoice.tenant_id}</b> &middot; Period
     {invoice.period_start.isoformat()} &rarr; {invoice.period_end.isoformat()}
     &middot; Generated {invoice.generated_at.isoformat()}</p>
  <p class="meta">Tier applied: <b>{invoice.tier_applied or 'none'}</b></p>
  <table>
    <thead><tr>
      <th>Metric</th><th>Qty</th><th>Included</th><th>Billable</th>
      <th>Unit Price</th><th>Base</th><th>Tier Disc.</th><th>Amount</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div class="totals">
    <p>Subtotal: ${invoice.subtotal}</p>
    <p>Tier discount: ${invoice.tier_discount_total}</p>
    <p>Tax: ${invoice.tax}</p>
    <p><strong>Total: ${invoice.total}</strong></p>
  </div>
</body>
</html>
"""
        return html.encode("utf-8")

    # ─────────────────────────────────────────────────────────────────────
    # list_invoices
    # ─────────────────────────────────────────────────────────────────────

    async def list_invoices(self, tenant_id: str, limit: int = 20) -> List[Invoice]:
        """Return all persisted invoices for `tenant_id`, sorted by generated_at ASC."""
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        return await self.store.list_invoices(tenant_id.strip(), limit=limit)


__all__ = [
    "CDPBillingService",
    "CdpBillingStore",
    "InMemoryCdpBillingStore",
    "default_tiers",
    "default_pricing_rules",
]
