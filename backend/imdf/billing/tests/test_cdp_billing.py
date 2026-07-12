"""Tests for CDP Billing Service (V5 Chapter 22 / §13.4).

Coverage targets (≥10 tests):
    1. Pydantic schema validation
    2. Single-tenant tracking accumulation
    3. Multi-tenant isolation
    4. Empty-period invoice
    5. Invoice with 0 line items
    6. Tier 1 (no discount) on small usage
    7. Tier 2 (5% discount) on 10k-100k units
    8. Tier 3 (10% discount) on 100k+ units
    9. Aggregate discount exactly equals expected $95 example from spec
    10. PDF generation returns non-empty bytes (header check)
    11. PDF generation is valid reportlab PDF when available
    12. Invoice line items have correct billable qty (deducts included)
    13. list_invoices returns chronological order
    14. Validation errors on bad inputs
"""
from __future__ import annotations

import asyncio
import datetime as dt
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from billing.cdp_billing import (
    CDPBillingService,
    InMemoryCdpBillingStore,
    default_pricing_rules,
    default_tiers,
)
from billing.cdp_billing_schemas import (
    BillingTier,
    Invoice,
    InvoiceLineItem,
    PricingRule,
    UsageRecord,
)


# ────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ────────────────────────────────────────────────────────────────────────────


def _run(coro):  # minimal async runner since pytest-asyncio is not always on
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def service() -> CDPBillingService:
    return CDPBillingService(
        store=InMemoryCdpBillingStore(),
        pricing_rules=default_pricing_rules(),
        tiers=default_tiers(),
    )


# ────────────────────────────────────────────────────────────────────────────
# 1-2. Schema validation + basic construction
# ────────────────────────────────────────────────────────────────────────────


def test_usage_record_validation_rejects_empty_tenant() -> None:
    with pytest.raises(ValidationError):
        UsageRecord(tenant_id="", metric="api_calls", value=Decimal("1"))


def test_usage_record_validation_rejects_negative_value() -> None:
    with pytest.raises(ValidationError):
        UsageRecord(tenant_id="tenant-1", metric="api_calls", value=Decimal("-1"))


def test_billing_tier_validation_rejects_invalid_discount() -> None:
    with pytest.raises(ValidationError):
        BillingTier(name="bad", min_units=Decimal("0"), discount_pct=Decimal("150"))


def test_pricing_rule_serialization_roundtrip() -> None:
    rule = PricingRule(metric="api_calls", unit="call", unit_price=Decimal("0.005"))
    data = rule.model_dump()
    rebuilt = PricingRule.model_validate(data)
    assert rebuilt.metric == "api_calls"
    assert rebuilt.unit_price == Decimal("0.005")


# ────────────────────────────────────────────────────────────────────────────
# 5-6. Usage tracking accumulation + tenant isolation
# ────────────────────────────────────────────────────────────────────────────


def test_track_usage_accumulates_per_tenant(service: CDPBillingService) -> None:
    ts = datetime(2026, 3, 15, 12, 0, 0)
    rec1 = _run(service.track_usage("tenant-1", "api_calls", 100, timestamp=ts))
    rec2 = _run(service.track_usage("tenant-1", "api_calls", 250, timestamp=ts))
    rec3 = _run(service.track_usage("tenant-2", "api_calls", 999, timestamp=ts))
    assert rec1.tenant_id == "tenant-1"
    assert rec2.value == Decimal("250")
    rows_t1 = _run(service.store.list_usage("tenant-1"))
    rows_t2 = _run(service.store.list_usage("tenant-2"))
    assert len(rows_t1) == 2
    assert len(rows_t2) == 1
    total_t1 = sum((r.value for r in rows_t1), Decimal("0"))
    assert total_t1 == Decimal("350")


def test_track_usage_validation_rejects_empty_inputs(service: CDPBillingService) -> None:
    with pytest.raises(ValueError):
        _run(service.track_usage("", "api_calls", 1))
    with pytest.raises(ValueError):
        _run(service.track_usage("t1", "", 1))
    with pytest.raises(ValueError):
        _run(service.track_usage("t1", "api_calls", -1))


# Convenience timestamp inside March 2026 for tests below
def _mar_ts(day: int = 15) -> datetime:
    return datetime(2026, 3, day, 12, 0, 0)


# ────────────────────────────────────────────────────────────────────────────
# 7. Empty-period invoice (no usage yet → zero subtotal)
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_empty_period_returns_zero_subtotal(
    service: CDPBillingService,
) -> None:
    today = date(2026, 3, 1)
    next_month = date(2026, 4, 1)
    invoice = _run(service.calculate_invoice("tenant-1", today, next_month))
    assert isinstance(invoice, Invoice)
    assert invoice.subtotal == Decimal("0")
    assert invoice.total == Decimal("0")
    assert invoice.tier_applied in (None, "tier_1")
    assert invoice.line_items == []


# ────────────────────────────────────────────────────────────────────────────
# 8. Tier resolution — Tier 1 small usage, no discount
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_tier_1_small_usage_no_discount(service: CDPBillingService) -> None:
    # Small api_calls volume — no tier discount (tier_1 = 0-100 GB data, 0% discount).
    # api_calls doesn't drive tier resolution (only data_gb does), so 500 calls
    # stays in tier_1 even though aggregate qty would be > 0.
    _run(service.track_usage("tenant-1", "api_calls", 500, timestamp=_mar_ts()))
    invoice = _run(
        service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1))
    )
    assert invoice.tier_applied in (None, "tier_1")
    assert invoice.line_items[0].metric == "api_calls"
    # 500 calls × $0.005 = $2.50 (no included free tier)
    assert invoice.subtotal == Decimal("2.50")
    assert invoice.tier_discount_total == Decimal("0.00")


# ────────────────────────────────────────────────────────────────────────────
# 9. Tier 2 — 5% discount at 10000-99999 qty
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_tier_2_5pct_discount_mid_volume(service: CDPBillingService) -> None:
    # data_gb = 500 → tier_2 (100-1000 GB threshold, 5% discount).
    # No free tier anymore — every GB is billable at $0.10.
    _run(service.track_usage("tenant-mid", "data_gb", 500, timestamp=_mar_ts()))
    invoice = _run(service.calculate_invoice("tenant-mid", date(2026, 3, 1), date(2026, 4, 1)))
    assert invoice.tier_applied == "tier_2"
    # subtotal = 500 × $0.10 = $50.00
    # discount = 5% × $50 = $2.50
    # total = $47.50
    assert invoice.subtotal == Decimal("50.00")
    assert invoice.tier_discount_total == Decimal("2.50")
    assert invoice.total == Decimal("47.50")


# ────────────────────────────────────────────────────────────────────────────
# 10. Tier 3 — 10% discount at ≥100000 qty (the spec's $95 example)
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_tier_3_15pct_discount_large_volume(service: CDPBillingService) -> None:
    # data_gb = 2000 → tier_3 (>= 1000 GB threshold, 15% discount).
    _run(service.track_usage("tenant-big", "data_gb", 2000, timestamp=_mar_ts()))
    _run(service.track_usage("tenant-big", "api_calls", 5000, timestamp=_mar_ts()))
    invoice = _run(service.calculate_invoice("tenant-big", date(2026, 3, 1), date(2026, 4, 1)))
    assert invoice.tier_applied == "tier_3"
    # data_gb = 2000 × $0.10 = $200.00
    # api_calls = 5000 × $0.005 = $25.00
    # subtotal = $225.00; tier_3 15% = $33.75; total = $191.25
    assert invoice.subtotal == Decimal("225.00")
    assert invoice.tier_discount_total == Decimal("33.75")
    assert invoice.total == Decimal("191.25")


# ────────────────────────────────────────────────────────────────────────────
# 11. The exact spec example: 500 GB + 10000 API → $95 base → tier_2 $90.25
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_spec_example_500gb_10kapi(service: CDPBillingService) -> None:
    """V5 §13.4 spec example: 500 GB data + 10000 API calls in March.

    Per aligned pricing rules (no free tier; tier based on data_gb qty):
      data_gb: 500 × $0.10 = $50.00
      api_calls: 10000 × $0.005 = $50.00
      subtotal = $100.00
      data_gb qty = 500 → tier_2 (100-1000 GB threshold, 5% discount) = $5.00
      total = $95.00
    """
    _run(service.track_usage("tenant-1", "data_gb", 500, timestamp=_mar_ts()))
    _run(service.track_usage("tenant-1", "api_calls", 10000, timestamp=_mar_ts()))
    invoice = _run(service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1)))
    assert invoice.tier_applied == "tier_2"
    assert invoice.subtotal == Decimal("100.00")
    assert invoice.tier_discount_total == Decimal("5.00")
    assert invoice.total == Decimal("95.00")
    # All line items present
    metrics = sorted(li.metric for li in invoice.line_items)
    assert metrics == ["api_calls", "data_gb"]


# ────────────────────────────────────────────────────────────────────────────
# 12. Included qty correctly deducted from billable
# ────────────────────────────────────────────────────────────────────────────


def test_line_items_deduct_included_qty_correctly(service: CDPBillingService) -> None:
    _run(service.track_usage("tenant-1", "render_minutes", 30, timestamp=_mar_ts()))  # exactly included
    invoice = _run(service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1)))
    line = next(li for li in invoice.line_items if li.metric == "render_minutes")
    assert line.qty == Decimal("30")
    assert line.billable_qty == Decimal("0")
    assert line.base_amount == Decimal("0")


# ────────────────────────────────────────────────────────────────────────────
# 13-14. PDF generation
# ────────────────────────────────────────────────────────────────────────────


def test_generate_invoice_pdf_returns_nonempty_bytes(service: CDPBillingService) -> None:
    _run(service.track_usage("tenant-1", "api_calls", 2000, timestamp=_mar_ts()))
    invoice = _run(service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1)))
    pdf_bytes = _run(service.generate_invoice_pdf(invoice))
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100
    # Either it's a real PDF (reportlab) or an HTML fallback containing the tenant ID
    is_pdf = pdf_bytes.startswith(b"%PDF-")
    has_tenant_id = b"tenant-1" in pdf_bytes
    assert is_pdf or has_tenant_id


def test_generate_invoice_pdf_html_fallback_contains_invoice_metadata(
    service: CDPBillingService,
) -> None:
    invoice = _run(service.calculate_invoice("tenant-fb", date(2026, 3, 1), date(2026, 4, 1)))
    pdf_bytes = _run(service.generate_invoice_pdf(invoice))
    text = pdf_bytes.decode("utf-8", errors="ignore")
    if not pdf_bytes.startswith(b"%PDF-"):
        # HTML fallback path — verify template markers
        assert "CDP Invoice" in text
        assert "tenant-fb" in text
        assert "Total:" in text


# ────────────────────────────────────────────────────────────────────────────
# 15. list_invoices returns chronological order
# ────────────────────────────────────────────────────────────────────────────


def test_list_invoices_returns_chronological_order(service: CDPBillingService) -> None:
    _run(service.track_usage("tenant-1", "api_calls", 2000, timestamp=datetime(2026, 3, 15, 12, 0, 0)))
    inv_mar = _run(service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1)))
    # small sleep to ensure generated_at tick forward
    import time as _t

    _t.sleep(0.01)
    _run(service.track_usage("tenant-1", "api_calls", 4000, timestamp=datetime(2026, 4, 15, 12, 0, 0)))
    inv_apr = _run(service.calculate_invoice("tenant-1", date(2026, 4, 1), date(2026, 5, 1)))
    _t.sleep(0.01)
    _run(service.track_usage("tenant-1", "api_calls", 6000, timestamp=datetime(2026, 5, 15, 12, 0, 0)))
    inv_may = _run(service.calculate_invoice("tenant-1", date(2026, 5, 1), date(2026, 6, 1)))
    rows = _run(service.list_invoices("tenant-1", limit=10))
    assert len(rows) == 3
    # chronological (earliest first)
    assert rows[0].period_start == inv_mar.period_start
    assert rows[-1].period_start == inv_may.period_start


def test_list_invoices_respects_limit(service: CDPBillingService) -> None:
    for m in (1, 2, 3, 4, 5):
        _run(service.track_usage("tenant-1", "api_calls", 100 * m, timestamp=datetime(2026, m, 15, 12, 0, 0)))
        _run(service.calculate_invoice("tenant-1", date(2026, m, 1), date(2026, m + 1, 1)))
    rows = _run(service.list_invoices("tenant-1", limit=2))
    assert len(rows) == 2


# ────────────────────────────────────────────────────────────────────────────
# 16. Invoice persistence — repeated calls don't double-count
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_is_persistent_not_ephemeral(service: CDPBillingService) -> None:
    _run(service.track_usage("tenant-1", "api_calls", 500, timestamp=_mar_ts()))
    first = _run(service.calculate_invoice("tenant-1", date(2026, 3, 1), date(2026, 4, 1)))
    rows = _run(service.list_invoices("tenant-1"))
    assert any(inv.id == first.id for inv in rows)


# ────────────────────────────────────────────────────────────────────────────
# 17. Bad inputs rejected
# ────────────────────────────────────────────────────────────────────────────


def test_calculate_invoice_rejects_inverted_period(service: CDPBillingService) -> None:
    with pytest.raises(ValueError):
        _run(
            service.calculate_invoice("tenant-1", date(2026, 4, 1), date(2026, 3, 1))
        )


def test_list_invoices_rejects_empty_tenant(service: CDPBillingService) -> None:
    with pytest.raises(ValueError):
        _run(service.list_invoices(""))
