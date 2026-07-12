"""Pydantic v2 schemas for CDP Advanced Billing (V5 Chapter 22 / §13.4).

Schemas (no business logic; pure data containers):
    BillingTier       — single tier (name / base_fee / included_units / overage_rate / discount)
    PricingRule       — per-metric pricing rule (metric / unit / included / unit_price / overage)
    UsageRecord       — single tracked usage event (tenant / metric / value / ts / metadata)
    InvoiceLineItem   — one row on an invoice (metric / qty / unit_price / tier_discount / amount)
    Invoice           — full invoice (id / tenant / period / line_items / subtotal / discount / tax / total)

Used by:
    backend/imdf/billing/cdp_billing.py — CDPBillingService
    backend/imdf/billing/api.py          — FastAPI HTTP surface
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BillingTier(BaseModel):
    """A pricing tier in the volume-discount ladder.

    Higher `min_units` thresholds get progressively larger `discount_pct`
    discounts applied to the per-metric sub-total.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Tier name (e.g. 'starter', 'growth', 'scale')")
    min_units: Decimal = Field(
        Decimal("0"), description="Lower bound of monthly aggregate usage (sum of qty across metrics)"
    )
    discount_pct: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Volume discount percent (0-100) applied to the entire invoice",
    )
    description: str = Field("", description="Human-readable tier description")

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()


class PricingRule(BaseModel):
    """Per-metric pricing — `qty * unit_price` is base, then a tier discount is applied.

    `included_qty` lets us give a metered allowance per metric (e.g. first 100 GB free).
    """

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., description="Metric identifier (e.g. 'storage_gb', 'api_calls')")
    unit: str = Field("unit", description="Unit label (e.g. 'GB', 'call')")
    unit_price: Decimal = Field(
        Decimal("0"), ge=Decimal("0"), description="Price per unit (in invoice currency)"
    )
    included_qty: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Quantity included free of charge per billing period",
    )
    currency: str = Field("USD", min_length=3, max_length=3, description="ISO 4217 3-letter code")
    description: str = Field("", description="Human-readable rule description")


class UsageRecord(BaseModel):
    """Single metered usage event for a tenant."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"ur_{int(datetime.utcnow().timestamp() * 1000)}")
    tenant_id: str = Field(..., min_length=1, description="Tenant/customer identifier")
    metric: str = Field(..., min_length=1, description="Metric identifier matching PricingRule.metric")
    value: Decimal = Field(Decimal("0"), ge=Decimal("0"), description="Quantity consumed")
    unit: str = Field("unit", description="Unit label matching PricingRule.unit")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When usage occurred (UTC)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Free-form context")

    @field_validator("tenant_id", "metric")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v.strip()


class InvoiceLineItem(BaseModel):
    """One line item on an invoice — per metric, after tier discount."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    description: str = ""
    qty: Decimal = Field(Decimal("0"), ge=Decimal("0"), description="Total quantity for the period")
    included_qty: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    billable_qty: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    unit_price: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    base_amount: Decimal = Field(
        Decimal("0"), ge=Decimal("0"), description="billable_qty * unit_price, before discount"
    )
    tier_discount: Decimal = Field(
        Decimal("0"), ge=Decimal("0"), description="Volume-tier discount applied to this line"
    )
    amount: Decimal = Field(Decimal("0"), description="Final line amount = base_amount - tier_discount")


class Invoice(BaseModel):
    """Full monthly invoice — subtotal, discount, tax, total."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"inv_{int(datetime.utcnow().timestamp() * 1000)}")
    tenant_id: str
    period_start: date
    period_end: date
    currency: str = Field("USD", min_length=3, max_length=3)
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    subtotal: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    tier_discount_total: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    tax: Decimal = Field(Decimal("0"), ge=Decimal("0"), description="Tax amount (currently 0 for the simple model)")
    total: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    tier_applied: Optional[str] = Field(None, description="Which BillingTier name was applied (if any)")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    paid: bool = Field(False, description="Whether this invoice has been settled")
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "BillingTier",
    "PricingRule",
    "UsageRecord",
    "InvoiceLineItem",
    "Invoice",
]
