"""P17-A1 tax calculation tests.

Coverage:
- 3 tax regimes (CN / US / EU)
- 4 categories (standard / reduced / low / exempt) per regime
- 12 country/category combinations
- calc_tax single-shot
- compute_order_totals multi-line
- attach_tax_to_order integration
- Country code normalization (CN / CHN / DE / DEU)
- Validation errors
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from decimal import Decimal

from billing import tax as tx


# ── 1. Tax category constants ──────────────────────────────────────────────

class TestCategories:
    def test_001_all_categories(self):
        assert set(tx.ALL_CATEGORIES) == {"standard", "reduced", "low", "exempt"}
        assert len(tx.ALL_CATEGORIES) == 4


# ── 2. Tax regimes ─────────────────────────────────────────────────────────

class TestRegimes:
    def test_010_cn_regime(self):
        r = tx.CN_TAX_REGIME
        assert r.country_code == "CN"
        assert r.regime_type == "cn_vat"
        assert r.rates["standard"] == Decimal("0.13")
        assert r.rates["reduced"] == Decimal("0.06")
        assert r.rates["low"] == Decimal("0.03")
        assert r.rates["exempt"] == Decimal("0.00")

    def test_011_us_regime(self):
        r = tx.US_TAX_REGIME
        assert r.country_code == "US"
        assert r.regime_type == "us_sales"
        assert r.rates["standard"] == Decimal("0.07")
        assert r.rates["reduced"] == Decimal("0.05")
        assert r.rates["low"] == Decimal("0.02")
        assert r.rates["exempt"] == Decimal("0.00")

    def test_012_eu_regime(self):
        r = tx.EU_TAX_REGIME
        assert r.country_code == "EU"
        assert r.regime_type == "eu_vat"
        assert r.rates["standard"] == Decimal("0.21")
        assert r.rates["reduced"] == Decimal("0.09")
        assert r.rates["low"] == Decimal("0.05")
        assert r.rates["exempt"] == Decimal("0.00")

    def test_013_country_lookup(self):
        assert tx.get_regime("CN") is tx.CN_TAX_REGIME
        assert tx.get_regime("cn") is tx.CN_TAX_REGIME  # case-insensitive
        assert tx.get_regime("CHN") is tx.CN_TAX_REGIME
        assert tx.get_regime("US") is tx.US_TAX_REGIME
        assert tx.get_regime("USA") is tx.US_TAX_REGIME
        assert tx.get_regime("DE") is tx.EU_TAX_REGIME
        assert tx.get_regime("FRA") is tx.EU_TAX_REGIME
        assert tx.get_regime("GB") is tx.EU_TAX_REGIME

    def test_014_country_lookup_invalid(self):
        with pytest.raises(ValueError):
            tx.get_regime("XX")
        with pytest.raises(ValueError):
            tx.get_regime("")


# ── 3. calc_tax — single call ─────────────────────────────────────────────

class TestCalcTax:
    def test_020_cn_standard(self):
        # ¥1000.00, 13% VAT → ¥130.00 tax → ¥1130.00 total
        r = tx.calc_tax(100000, "CN", "standard")
        assert r.subtotal_cents == 100000
        assert r.rate == Decimal("0.13")
        assert r.tax_cents == 13000
        assert r.total_cents == 113000
        assert r.country == "CN"
        assert r.regime_type == "cn_vat"

    def test_021_cn_reduced(self):
        r = tx.calc_tax(100000, "CN", "reduced")
        assert r.rate == Decimal("0.06")
        assert r.tax_cents == 6000
        assert r.total_cents == 106000

    def test_022_cn_low(self):
        r = tx.calc_tax(100000, "CN", "low")
        assert r.rate == Decimal("0.03")
        assert r.tax_cents == 3000
        assert r.total_cents == 103000

    def test_023_cn_exempt(self):
        r = tx.calc_tax(100000, "CN", "exempt")
        assert r.rate == Decimal("0.00")
        assert r.tax_cents == 0
        assert r.total_cents == 100000

    def test_024_us_standard(self):
        r = tx.calc_tax(10000, "US", "standard")  # $100
        assert r.rate == Decimal("0.07")
        assert r.tax_cents == 700  # $7
        assert r.total_cents == 10700  # $107

    def test_025_us_low(self):
        r = tx.calc_tax(10000, "US", "low")
        assert r.tax_cents == 200
        assert r.total_cents == 10200

    def test_026_eu_standard(self):
        r = tx.calc_tax(10000, "DE", "standard")
        assert r.rate == Decimal("0.21")
        assert r.tax_cents == 2100
        assert r.total_cents == 12100

    def test_027_eu_reduced(self):
        r = tx.calc_tax(10000, "FR", "reduced")
        assert r.rate == Decimal("0.09")
        assert r.tax_cents == 900
        assert r.total_cents == 10900

    def test_028_zero_subtotal(self):
        r = tx.calc_tax(0, "CN", "standard")
        assert r.subtotal_cents == 0
        assert r.tax_cents == 0
        assert r.total_cents == 0

    def test_029_negative_subtotal_raises(self):
        with pytest.raises(ValueError):
            tx.calc_tax(-1, "CN", "standard")

    def test_030_unknown_category_raises(self):
        with pytest.raises(ValueError):
            tx.calc_tax(1000, "CN", "bogus_category")

    def test_031_unknown_country_raises(self):
        with pytest.raises(ValueError):
            tx.calc_tax(1000, "XX", "standard")


class TestTwelveCombinations:
    """3 countries × 4 categories = 12 combinations (spec required)."""

    @pytest.mark.parametrize("country,category,expected_rate", [
        ("CN", "standard", Decimal("0.13")),
        ("CN", "reduced",  Decimal("0.06")),
        ("CN", "low",      Decimal("0.03")),
        ("CN", "exempt",   Decimal("0.00")),
        ("US", "standard", Decimal("0.07")),
        ("US", "reduced",  Decimal("0.05")),
        ("US", "low",      Decimal("0.02")),
        ("US", "exempt",   Decimal("0.00")),
        ("DE", "standard", Decimal("0.21")),
        ("DE", "reduced",  Decimal("0.09")),
        ("DE", "low",      Decimal("0.05")),
        ("DE", "exempt",   Decimal("0.00")),
    ])
    def test_040_all_combinations(self, country, category, expected_rate):
        r = tx.calc_tax(100000, country, category)
        assert r.rate == expected_rate
        assert r.tax_cents == int(100000 * expected_rate)
        assert r.total_cents == 100000 + r.tax_cents


# ── 4. Order totals (multi-line) ──────────────────────────────────────────

class TestOrderTotals:
    def test_050_mixed_categories(self):
        lines = [
            tx.LineItem("SaaS Pro plan", 9900, "standard"),  # $99 standard 7%
            tx.LineItem("Training service", 5000, "reduced"),  # $50 reduced 5%
            tx.LineItem("Add-on storage", 1000, "low"),  # $10 low 2%
        ]
        totals = tx.compute_order_totals(lines, "US")
        assert totals.subtotal_cents == 15900
        # 693 + 250 + 20 = 963
        assert totals.tax_cents == 963
        assert totals.total_cents == 16863
        assert len(totals.breakdown) == 3

    def test_051_eu_mixed(self):
        lines = [
            tx.LineItem("Service A", 10000, "standard"),
            tx.LineItem("Service B", 5000, "reduced"),
        ]
        totals = tx.compute_order_totals(lines, "DE")
        # 10000 * 0.21 + 5000 * 0.09 = 2100 + 450 = 2550
        assert totals.tax_cents == 2550
        assert totals.total_cents == 17550

    def test_052_all_exempt(self):
        lines = [tx.LineItem("Free", 1000, "exempt")]
        totals = tx.compute_order_totals(lines, "CN")
        assert totals.tax_cents == 0
        assert totals.total_cents == 1000

    def test_053_empty_lines_raises(self):
        with pytest.raises(ValueError):
            tx.compute_order_totals([], "CN")

    def test_054_negative_amount_raises(self):
        with pytest.raises(ValueError):
            tx.compute_order_totals(
                [tx.LineItem("Bad", -100, "standard")], "CN"
            )

    def test_055_to_dict(self):
        lines = [tx.LineItem("A", 1000, "standard")]
        totals = tx.compute_order_totals(lines, "CN")
        d = totals.to_dict()
        assert d["country"] == "CN"
        assert d["subtotal_cents"] == 1000
        assert d["tax_cents"] == 130
        assert d["total_cents"] == 1130
        assert len(d["breakdown"]) == 1


# ── 5. attach_tax_to_order ────────────────────────────────────────────────

class TestAttachTax:
    def test_060_attach_explicit_country(self):
        order = {"order_id": "ord_001", "amount_cents": 10000}
        out = tx.attach_tax_to_order(order, country="CN", category="standard")
        assert out["country"] == "CN"
        assert out["category"] == "standard"
        assert out["tax_rate"] == 0.13
        assert out["tax_amount"] == 1300
        assert out["total_amount"] == 11300
        assert out["regime_type"] == "cn_vat"

    def test_061_attach_from_order(self):
        order = {"order_id": "ord_001", "amount_cents": 10000, "country": "US"}
        out = tx.attach_tax_to_order(order)
        assert out["country"] == "US"
        assert out["tax_rate"] == 0.07
        assert out["tax_amount"] == 700
        assert out["total_amount"] == 10700

    def test_062_attach_default_country(self):
        order = {"amount_cents": 1000}
        out = tx.attach_tax_to_order(order)
        # Default country is CN
        assert out["country"] == "CN"
        assert out["tax_amount"] == 130  # 1000 * 0.13

    def test_063_attach_accepts_amount_key(self):
        # Some callers use 'amount' (cents) instead of 'amount_cents'
        order = {"amount": 1000}
        out = tx.attach_tax_to_order(order)
        assert out["tax_amount"] == 130