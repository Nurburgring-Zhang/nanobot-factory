"""Tax calculation for billing.

Supports 3 tax regimes:
- CN: 增值税 (VAT) — 13% / 6% / 3% categories
- US: 销售税 (Sales tax) — 0-10% (state-dependent, configurable)
- EU: 增值税 (VAT) — 0-25% (country-dependent, configurable)

Public surface:
- TaxCategory: enum for tax categories (standard / reduced / low / exempt)
- TaxRegime: per-country tax rates (CN/US/EU)
- calc_tax(subtotal_cents, country, category) -> TaxResult
- compute_order_totals(order) -> Totals (subtotal + tax + grand_total)
- Country to regime mapping (CN → cn, US → us, DE → eu, etc.)

Design:
- Pure functions, no DB / no I/O.
- All amounts in sub-units (cents / 分).
- Tax rate applied to subtotal BEFORE discounts (standard convention).
- For multi-line orders: each line can have its own category.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple


# ============================================================================
# 1. Tax categories — used to look up rate in regime table
# ============================================================================

class TaxCategory(str):
    """Tax category codes.

    CN uses 13% / 6% / 3% (3 VAT brackets).
    US uses 0-10% (varies by state, here we use 4 standard buckets).
    EU uses 0-25% (varies by country; here 4 standard buckets).
    """
    STANDARD = "standard"   # CN: 13%, US: 7%, EU: 21%
    REDUCED = "reduced"     # CN: 6%,  US: 5%, EU: 9%
    LOW = "low"             # CN: 3%,  US: 2%, EU: 5%
    EXEMPT = "exempt"       # 0% in all regimes


ALL_CATEGORIES: Tuple[str, ...] = ("standard", "reduced", "low", "exempt")


# ============================================================================
# 2. Tax regimes — per-country rate tables
# ============================================================================

@dataclass(frozen=True)
class TaxRegime:
    """Tax regime for a country."""
    country_code: str       # "CN" / "US" / "DE"
    country_name: str
    regime_type: str        # "cn_vat" / "us_sales" / "eu_vat"
    rates: Dict[str, Decimal]  # category -> rate (e.g. "standard" -> Decimal("0.13"))
    display_name: str       # 中文名


# CN: 增值税 (VAT)
CN_TAX_REGIME = TaxRegime(
    country_code="CN",
    country_name="China",
    regime_type="cn_vat",
    rates={
        "standard": Decimal("0.13"),  # 一般纳税人 13%
        "reduced":  Decimal("0.06"),  # 现代服务业 6%
        "low":      Decimal("0.03"),  # 小规模纳税人 3%
        "exempt":   Decimal("0.00"),
    },
    display_name="中国增值税",
)

# US: Sales tax (representative — real implementation would key off state)
# 0-10% across states; here we use 4 buckets for testing.
US_TAX_REGIME = TaxRegime(
    country_code="US",
    country_name="United States",
    regime_type="us_sales",
    rates={
        "standard": Decimal("0.07"),  # 多数州约 7% (CA ~7.25%, TX 6.25%, etc.)
        "reduced":  Decimal("0.05"),  # 食品 / 处方药等减税品类
        "low":      Decimal("0.02"),  # 部分州低税率 (如 AK 某些情况)
        "exempt":   Decimal("0.00"),  # 非应税品类 (rare)
    },
    display_name="美国销售税",
)

# EU: VAT — varies by country (DE 19%, FR 20%, UK 20%, etc.)
# Here we use 4 buckets representing the range.
EU_TAX_REGIME = TaxRegime(
    country_code="EU",
    country_name="European Union",
    regime_type="eu_vat",
    rates={
        "standard": Decimal("0.21"),  # 中位水平 (DE 19%, NL 21%, BE 21%)
        "reduced":  Decimal("0.09"),  # 减税率 (书籍 / 食品)
        "low":      Decimal("0.05"),  # 低税率 (FR 5.5% 部分品类)
        "exempt":   Decimal("0.00"),
    },
    display_name="欧盟增值税",
)


# Country code -> regime
COUNTRY_TO_REGIME: Dict[str, TaxRegime] = {
    # CN
    "CN": CN_TAX_REGIME,
    "CHN": CN_TAX_REGIME,
    # US
    "US": US_TAX_REGIME,
    "USA": US_TAX_REGIME,
    # EU member states
    "DE": EU_TAX_REGIME, "DEU": EU_TAX_REGIME,
    "FR": EU_TAX_REGIME, "FRA": EU_TAX_REGIME,
    "NL": EU_TAX_REGIME, "NLD": EU_TAX_REGIME,
    "BE": EU_TAX_REGIME, "BEL": EU_TAX_REGIME,
    "IT": EU_TAX_REGIME, "ITA": EU_TAX_REGIME,
    "ES": EU_TAX_REGIME, "ESP": EU_TAX_REGIME,
    "GB": EU_TAX_REGIME, "GBR": EU_TAX_REGIME, "UK": EU_TAX_REGIME,
    "IE": EU_TAX_REGIME, "IRL": EU_TAX_REGIME,
    "AT": EU_TAX_REGIME, "AUT": EU_TAX_REGIME,
    "PL": EU_TAX_REGIME, "POL": EU_TAX_REGIME,
    "SE": EU_TAX_REGIME, "SWE": EU_TAX_REGIME,
}

SUPPORTED_COUNTRIES: Tuple[str, ...] = tuple(COUNTRY_TO_REGIME.keys())


def get_regime(country: str) -> TaxRegime:
    """Lookup tax regime by country code. Raises ValueError if unknown."""
    code = country.upper()
    if code not in COUNTRY_TO_REGIME:
        raise ValueError(
            f"unsupported country for tax: {country!r} "
            f"(supported: {sorted(COUNTRY_TO_REGIME.keys())})"
        )
    return COUNTRY_TO_REGIME[code]


# ============================================================================
# 3. Calculation result
# ============================================================================

@dataclass(frozen=True)
class TaxResult:
    """Result of tax calculation."""
    subtotal_cents: int          # base amount
    country: str
    category: str
    rate: Decimal                # applied rate (e.g. Decimal("0.13"))
    tax_cents: int               # tax amount in sub-units
    total_cents: int             # subtotal + tax
    regime_type: str             # "cn_vat" / "us_sales" / "eu_vat"

    def to_dict(self) -> Dict[str, object]:
        return {
            "subtotal_cents": self.subtotal_cents,
            "country": self.country,
            "category": self.category,
            "rate": float(self.rate),
            "tax_cents": self.tax_cents,
            "total_cents": self.total_cents,
            "regime_type": self.regime_type,
        }


# ============================================================================
# 4. Core calculation
# ============================================================================

def calc_tax(subtotal_cents: int, country: str,
             category: str = "standard") -> TaxResult:
    """Calculate tax for a given subtotal + country + category.

    Args:
        subtotal_cents: amount in sub-units (cents / 分)
        country: ISO-2 / ISO-3 country code (e.g. "CN", "US", "DE")
        category: one of "standard" / "reduced" / "low" / "exempt"

    Returns:
        TaxResult with subtotal, rate, tax, total

    Raises:
        ValueError: negative subtotal, unknown country, or unknown category
    """
    if subtotal_cents < 0:
        raise ValueError(f"subtotal_cents must be >= 0, got {subtotal_cents}")

    cat = category.lower()
    if cat not in ALL_CATEGORIES:
        raise ValueError(
            f"unknown tax category: {category!r} "
            f"(valid: {ALL_CATEGORIES})"
        )

    regime = get_regime(country)
    rate = regime.rates[cat]
    # tax = subtotal * rate, rounded to nearest sub-unit
    tax_decimal = (Decimal(int(subtotal_cents)) * rate).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    tax_cents = int(tax_decimal)
    return TaxResult(
        subtotal_cents=int(subtotal_cents),
        country=country.upper(),
        category=cat,
        rate=rate,
        tax_cents=tax_cents,
        total_cents=int(subtotal_cents) + tax_cents,
        regime_type=regime.regime_type,
    )


# ============================================================================
# 5. Multi-line order totals
# ============================================================================

@dataclass(frozen=True)
class LineItem:
    """A single order line with its own tax category."""
    description: str
    amount_cents: int
    category: str = "standard"


@dataclass(frozen=True)
class OrderTotals:
    """Aggregate totals for an order with mixed categories."""
    lines: List[LineItem]
    country: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    breakdown: List[TaxResult]  # per-line breakdown

    def to_dict(self) -> Dict[str, object]:
        return {
            "country": self.country,
            "subtotal_cents": self.subtotal_cents,
            "tax_cents": self.tax_cents,
            "total_cents": self.total_cents,
            "lines": [
                {
                    "description": l.description,
                    "amount_cents": l.amount_cents,
                    "category": l.category,
                }
                for l in self.lines
            ],
            "breakdown": [r.to_dict() for r in self.breakdown],
        }


def compute_order_totals(lines: List[LineItem], country: str) -> OrderTotals:
    """Compute aggregate subtotal + tax + total for an order with mixed categories.

    Args:
        lines: list of LineItem(amount, category)
        country: ISO country code (all lines use same country's regime)

    Returns:
        OrderTotals with full breakdown.

    Raises:
        ValueError: any line has negative amount, or country unknown.
    """
    if not lines:
        raise ValueError("lines must not be empty")
    for i, line in enumerate(lines):
        if line.amount_cents < 0:
            raise ValueError(f"line {i}: amount_cents must be >= 0, got {line.amount_cents}")
    # Validate country
    get_regime(country)

    breakdown: List[TaxResult] = []
    subtotal = 0
    tax_total = 0
    for line in lines:
        r = calc_tax(line.amount_cents, country, line.category)
        breakdown.append(r)
        subtotal += r.subtotal_cents
        tax_total += r.tax_cents
    return OrderTotals(
        lines=list(lines),
        country=country.upper(),
        subtotal_cents=subtotal,
        tax_cents=tax_total,
        total_cents=subtotal + tax_total,
        breakdown=breakdown,
    )


# ============================================================================
# 6. Order integration helpers
# ============================================================================

def attach_tax_to_order(order_dict: Dict[str, object],
                        country: Optional[str] = None,
                        category: Optional[str] = None) -> Dict[str, object]:
    """Compute and attach tax fields to an order dict.

    Mutates and returns a dict with:
      - country
      - category
      - tax_rate (Decimal as float)
      - tax_amount (int cents)
      - total_amount (int cents)

    Args:
        order_dict: must contain 'amount_cents' (or 'amount'); optional 'country'
        country: override order's country (else read from dict)
        category: override category (else 'standard')

    Raises:
        ValueError: if amount_cents == 0 (P17-D1 Hidden #2).
            Zero-amount orders should not be taxed; this guards against
            accidental tax_application to refunds/credits/cancelled orders.
    """
    country = country or order_dict.get("country") or "CN"
    category = category or order_dict.get("category") or "standard"
    # Accept either 'amount_cents' or 'amount' (cents)
    subtotal = int(order_dict.get("amount_cents") or order_dict.get("amount") or 0)
    # P17-D1 Hidden #2: explicit rejection of zero-amount orders.
    # Zero-amount means no taxable event — apply no tax, raise clearly.
    if subtotal == 0:
        raise ValueError(
            "amount_cents must be > 0 (got 0); "
            "zero-amount orders are not taxable"
        )
    result = calc_tax(subtotal, country, category)
    order_dict["country"] = result.country
    order_dict["category"] = result.category
    order_dict["tax_rate"] = float(result.rate)
    order_dict["tax_amount"] = result.tax_cents
    order_dict["total_amount"] = result.total_cents
    order_dict["regime_type"] = result.regime_type
    return order_dict


__all__ = [
    "TaxCategory", "ALL_CATEGORIES",
    "TaxRegime", "CN_TAX_REGIME", "US_TAX_REGIME", "EU_TAX_REGIME",
    "COUNTRY_TO_REGIME", "SUPPORTED_COUNTRIES",
    "get_regime",
    "TaxResult", "LineItem", "OrderTotals",
    "calc_tax", "compute_order_totals",
    "attach_tax_to_order",
]