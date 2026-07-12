"""P17-D1 Hidden #1: CNY/JPY ¥ symbol disambiguation tests.

Verify:
- CURRENCY_SYMBOLS["CNY"] == "CN¥"
- CURRENCY_SYMBOLS["JPY"] == "JP¥"
- format_currency(CNY) = "CN¥100"
- format_currency(JPY) = "JP¥100"
- The two currencies no longer share the same symbol
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing import currency as cur


class TestCNYJPYSymbolDisambiguation:
    """Hidden #1 — CN¥ vs JP¥ must be distinct."""

    def test_001_cny_uses_cn_prefix(self):
        assert cur.CURRENCY_SYMBOLS["CNY"] == "CN¥"

    def test_002_jpy_uses_jp_prefix(self):
        assert cur.CURRENCY_SYMBOLS["JPY"] == "JP¥"

    def test_003_cny_and_jpy_are_distinct(self):
        """Critical: the bug was that they both used '¥'."""
        assert cur.CURRENCY_SYMBOLS["CNY"] != cur.CURRENCY_SYMBOLS["JPY"]

    def test_004_format_money_cny(self):
        assert cur.format_money(10000, "CNY") == "CN¥100.00"

    def test_005_format_money_jpy(self):
        assert cur.format_money(10000, "JPY") == "JP¥10000"

    def test_006_format_money_small_cny(self):
        assert cur.format_money(100, "CNY") == "CN¥1.00"

    def test_007_format_money_zero_cny(self):
        assert cur.format_money(0, "CNY") == "CN¥0.00"

    def test_008_format_money_zero_jpy(self):
        assert cur.format_money(0, "JPY") == "JP¥0"

    def test_009_format_money_jpy_no_decimals(self):
        # JPY should still have no decimals
        result = cur.format_money(1500, "JPY")
        assert result == "JP¥1500"
        assert "." not in result  # no decimal point

    def test_010_other_currencies_unchanged(self):
        # Sanity: USD/EUR/GBP/HKD unchanged
        assert cur.CURRENCY_SYMBOLS["USD"] == "$"
        assert cur.CURRENCY_SYMBOLS["EUR"] == "€"
        assert cur.CURRENCY_SYMBOLS["GBP"] == "£"
        assert cur.CURRENCY_SYMBOLS["HKD"] == "HK$"

    def test_011_currency_amount_format_uses_new_symbol(self):
        amt = cur.CurrencyAmount(amount_cents=9900, currency="CNY")
        assert amt.format() == "CN¥99.00"

    def test_012_currency_amount_jpy_format(self):
        amt = cur.CurrencyAmount(amount_cents=1500, currency="JPY")
        assert amt.format() == "JP¥1500"

    def test_013_supported_currency_info_uses_new_symbols(self):
        info = cur.supported_currency_info()
        assert info["CNY"]["symbol"] == "CN¥"
        assert info["JPY"]["symbol"] == "JP¥"

    def test_014_format_cny_100(self):
        """Spec: format_currency(CNY) = "CN¥100"."""
        # 10000 cents = 100 CNY major units
        result = cur.format_money(10000, "CNY")
        assert result == "CN¥100.00"

    def test_015_format_jpy_100(self):
        """Spec: format_currency(JPY) = "JP¥100"."""
        # 100 yen (JPY has 1 subunit)
        result = cur.format_money(100, "JPY")
        assert result == "JP¥100"


class TestInvoiceTemplateIntegration:
    """The invoice template should also use the new symbols."""

    def test_020_invoice_template_uses_cny_symbol(self):
        from billing.invoice_templates import _format_money
        assert _format_money(9900, "CNY") == "CN¥99.00"

    def test_021_invoice_template_uses_jpy_symbol(self):
        from billing.invoice_templates import _format_money
        assert _format_money(1500, "JPY") == "JP¥1500"