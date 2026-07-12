"""CDP billing package — V5 Chapter 22 / §13.4 (CDP Advanced Billing).

Submodules:
    cdp_billing_schemas — Pydantic v2 schemas (UsageRecord, Invoice, LineItem, Tier)
    cdp_billing         — CDPBillingService (in-memory, async, multi-tier pricing)
    api                 — FastAPI router with 4 endpoints
"""
from __future__ import annotations

from .cdp_billing import (
    CDPBillingService,
    CdpBillingStore,
    InMemoryCdpBillingStore,
    default_pricing_rules,
    default_tiers,
)
from .cdp_billing_schemas import (
    BillingTier,
    Invoice,
    InvoiceLineItem,
    PricingRule,
    UsageRecord,
)

__all__ = [
    "CDPBillingService",
    "CdpBillingStore",
    "InMemoryCdpBillingStore",
    "default_pricing_rules",
    "default_tiers",
    "BillingTier",
    "Invoice",
    "InvoiceLineItem",
    "PricingRule",
    "UsageRecord",
]
