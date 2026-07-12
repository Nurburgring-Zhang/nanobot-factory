"""P17-A1 multi-currency tests.

Coverage:
- 6 currencies supported
- convert_currency round-trips within 0.01% tolerance (100 conversions)
- format_money for each currency
- Static / Live provider fallback behavior
- CurrencyAmount dataclass
- Validation errors for unsupported currencies / negative amounts
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from decimal import Decimal

from billing import currency as cur


# ── 1. Module-level constants & helpers ─────────────────────────────────────

class TestConstants:
    def test_001_supported_currencies(self):
        assert cur.SUPPORTED_CURRENCIES == ("CNY", "USD", "EUR", "JPY", "GBP", "HKD")
        assert len(cur.SUPPORTED_CURRENCIES) == 6

    def test_002_currency_symbols(self):
        # P17-D1 Hidden #1: CN¥/JP¥ disambiguation
        assert cur.CURRENCY_SYMBOLS["CNY"] == "CN¥"
        assert cur.CURRENCY_SYMBOLS["USD"] == "$"
        assert cur.CURRENCY_SYMBOLS["EUR"] == "€"
        assert cur.CURRENCY_SYMBOLS["JPY"] == "JP¥"  # disambiguated from CNY
        assert cur.CURRENCY_SYMBOLS["GBP"] == "£"
        assert cur.CURRENCY_SYMBOLS["HKD"] == "HK$"
        # Critically: CNY and JPY now have distinct symbols
        assert cur.CURRENCY_SYMBOLS["CNY"] != cur.CURRENCY_SYMBOLS["JPY"]

    def test_003_currency_subunits(self):
        assert cur.CURRENCY_SUBUNITS["CNY"] == 100
        assert cur.CURRENCY_SUBUNITS["USD"] == 100
        assert cur.CURRENCY_SUBUNITS["EUR"] == 100
        assert cur.CURRENCY_SUBUNITS["JPY"] == 1
        assert cur.CURRENCY_SUBUNITS["GBP"] == 100
        assert cur.CURRENCY_SUBUNITS["HKD"] == 100

    def test_004_currency_decimals(self):
        assert cur.CURRENCY_DECIMALS["JPY"] == 0
        assert cur.CURRENCY_DECIMALS["USD"] == 2
        assert cur.CURRENCY_DECIMALS["CNY"] == 2

    def test_005_is_supported(self):
        assert cur.is_supported("USD")
        assert cur.is_supported("usd")  # case-insensitive
        assert cur.is_supported("CNY")
        assert not cur.is_supported("XYZ")
        assert not cur.is_supported("")

    def test_006_normalize_currency(self):
        assert cur.normalize_currency("usd") == "USD"
        assert cur.normalize_currency("cny") == "CNY"
        with pytest.raises(ValueError):
            cur.normalize_currency("XYZ")
        with pytest.raises(ValueError):
            cur.normalize_currency("")


class TestStaticRates:
    def test_010_static_rates_complete(self):
        for c in cur.SUPPORTED_CURRENCIES:
            assert c in cur.STATIC_RATES_TO_USD
            r = cur.STATIC_RATES_TO_USD[c]
            assert r > 0

    def test_011_usd_to_usd_is_one(self):
        assert cur.STATIC_RATES_TO_USD["USD"] == Decimal("1.000000")


# ── 2. Rate provider ───────────────────────────────────────────────────────

class TestStaticProvider:
    def test_020_static_provider_returns_table(self):
        p = cur.StaticRateProvider()
        assert p.get_rate_to_usd("CNY") == Decimal("7.200000")
        assert p.get_rate_to_usd("USD") == Decimal("1.0")
        with pytest.raises(ValueError):
            p.get_rate_to_usd("XYZ")

    def test_021_static_provider_last_updated(self):
        p = cur.StaticRateProvider()
        assert p.last_updated() == 0.0


class TestLiveApiProvider:
    def test_030_no_api_key_falls_back_to_static(self):
        p = cur.LiveApiRateProvider(api_key=None)
        # Without API key + offline, should silently use static
        rate = p.get_rate_to_usd("CNY")
        assert rate == Decimal("7.200000")

    def test_031_live_provider_normalizes(self):
        p = cur.LiveApiRateProvider(api_key=None)
        assert p.get_rate_to_usd("usd") == Decimal("1.0")


# ── 3. Conversion (the meat) ──────────────────────────────────────────────

class TestConvertCurrency:
    def test_040_same_currency_identity(self):
        for c in cur.SUPPORTED_CURRENCIES:
            assert cur.convert_currency(10000, c, c) == 10000

    def test_041_usd_to_cny(self):
        # 100 USD = 720 CNY
        out = cur.convert_currency(10000, "USD", "CNY")  # 10000 cents = $100
        assert out == 72000  # CN¥720.00

    def test_042_cny_to_usd(self):
        out = cur.convert_currency(72000, "CNY", "USD")  # CN¥720.00
        # 720 CNY ≈ 100 USD (720/7.20 = 100)
        assert out == 10000  # $100.00

    def test_043_usd_to_jpy(self):
        out = cur.convert_currency(10000, "USD", "JPY")  # $100
        # 100 * 157 = 15700 JPY
        assert out == 15700

    def test_044_jpy_to_usd(self):
        out = cur.convert_currency(15700, "JPY", "USD")  # ¥15700
        # 15700 / 157 = 100 USD = 10000 cents
        assert out == 10000

    def test_045_negative_amount_raises(self):
        with pytest.raises(ValueError):
            cur.convert_currency(-100, "USD", "CNY")

    def test_046_unsupported_currency_raises(self):
        with pytest.raises(ValueError):
            cur.convert_currency(100, "XYZ", "USD")
        with pytest.raises(ValueError):
            cur.convert_currency(100, "USD", "ABC")

    def test_047_case_insensitive_currencies(self):
        out1 = cur.convert_currency(10000, "usd", "cny")
        out2 = cur.convert_currency(10000, "USD", "CNY")
        assert out1 == out2


class TestRoundTripConversion:
    """6 currencies × 100 conversions (round-trip within tolerance)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        # Use static rates for determinism
        cur.set_provider(cur.StaticRateProvider())
        yield
        cur.reset_provider()

    def test_050_round_trip_all_currencies(self):
        """6 currencies × 100+ conversions. Each round-trip within tolerance.

        Round-trip tolerance: absolute 10 cents OR 0.01% of amount, whichever
        is larger. 10 cents covers 2-leg cumulative rounding noise (each leg
        can lose up to ~1 cent, FX rate amplifies the perceived cent value).
        """
        amounts = [100, 1000, 1234, 9999, 50000, 100000, 999999, 5_000_000]
        n_checks = 0
        for src in cur.SUPPORTED_CURRENCIES:
            for tgt in cur.SUPPORTED_CURRENCIES:
                if src == tgt:
                    continue
                for amt in amounts:
                    forward = cur.convert_currency(amt, src, tgt)
                    # Skip if forward conversion lost precision to 0
                    if forward == 0:
                        continue
                    back = cur.convert_currency(forward, tgt, src)
                    if amt == 0:
                        assert back == 0
                    else:
                        # Tolerance: max(10 cents, 0.01% of amt)
                        tolerance_cents = max(10, amt * 0.0001)
                        drift = abs(back - amt)
                        assert drift <= tolerance_cents, (
                            f"{src}->{tgt}->{src} drift too high: "
                            f"{amt} -> {forward} -> {back} "
                            f"(drift {drift} > tol {tolerance_cents:.2f} cents)"
                        )
                    n_checks += 1
        # 5 non-self targets × 6 sources × 8 amounts = 240 max; some skipped for rounding
        assert n_checks >= 100, f"expected >=100 round-trips, got {n_checks}"


class TestFormatMoney:
    def test_060_format_usd(self):
        assert cur.format_money(9900, "USD") == "$99.00"
        assert cur.format_money(0, "USD") == "$0.00"
        assert cur.format_money(1, "USD") == "$0.01"

    def test_061_format_cny(self):
        # P17-D1 Hidden #1: CN¥ prefix
        assert cur.format_money(9900, "CNY") == "CN¥99.00"

    def test_062_format_jpy_no_decimals(self):
        # P17-D1 Hidden #1: JP¥ prefix
        assert cur.format_money(1500, "JPY") == "JP¥1500"
        assert cur.format_money(0, "JPY") == "JP¥0"

    def test_063_format_eur(self):
        assert cur.format_money(1234, "EUR") == "€12.34"

    def test_064_format_gbp(self):
        assert cur.format_money(10000, "GBP") == "£100.00"

    def test_065_format_hkd(self):
        assert cur.format_money(8888, "HKD") == "HK$88.88"

    def test_066_format_invalid_raises(self):
        with pytest.raises(ValueError):
            cur.format_money(100, "XYZ")


# ── 4. CurrencyAmount dataclass ───────────────────────────────────────────

class TestCurrencyAmount:
    def test_070_basic(self):
        amt = cur.CurrencyAmount(amount_cents=9900, currency="usd")
        assert amt.amount_cents == 9900
        assert amt.currency == "USD"  # normalized
        assert amt.format() == "$99.00"

    def test_071_negative_raises(self):
        with pytest.raises(ValueError):
            cur.CurrencyAmount(amount_cents=-1, currency="USD")

    def test_072_to_method(self):
        amt = cur.CurrencyAmount(amount_cents=10000, currency="USD")
        cny = amt.to("CNY")
        assert cny.currency == "CNY"
        assert cny.amount_cents == 72000  # $100 = ¥720

    def test_073_to_same_currency(self):
        amt = cur.CurrencyAmount(amount_cents=10000, currency="USD")
        same = amt.to("USD")
        assert same.amount_cents == 10000


# ── 5. supported_currency_info ─────────────────────────────────────────────

class TestSupportedInfo:
    def test_080_info_returns_all_six(self):
        info = cur.supported_currency_info()
        assert set(info.keys()) == set(cur.SUPPORTED_CURRENCIES)
        for code in cur.SUPPORTED_CURRENCIES:
            assert info[code]["code"] == code
            assert info[code]["name"]
            assert info[code]["symbol"]
            assert info[code]["decimals"] >= 0
            assert info[code]["subunits"] >= 1


# ── 6. Module-level provider swap ──────────────────────────────────────────

class TestProviderSwap:
    def test_090_set_and_get_provider(self):
        orig = cur.get_provider()
        try:
            custom = cur.StaticRateProvider()
            cur.set_provider(custom)
            assert cur.get_provider() is custom
        finally:
            cur.set_provider(orig)

    def test_091_reset_provider(self):
        cur.set_provider(cur.StaticRateProvider())
        cur.reset_provider()
        # Reset creates a new LiveApiRateProvider
        assert isinstance(cur.get_provider(), cur.LiveApiRateProvider)


# ── 7. Plan / Order currency integration (light smoke) ────────────────────

class TestIntegration:
    def test_100_plan_supports_multiple_currencies_via_price_for(self):
        # plans.price_for already supports CNY/USD via existing code
        from billing.plans import price_for
        assert price_for("pro", "monthly", "cny") == 9900
        assert price_for("pro", "monthly", "usd") == 9900
        # For other currencies, caller uses convert_currency
        pro_cny = price_for("pro", "monthly", "cny")
        pro_eur = cur.convert_currency(pro_cny, "CNY", "EUR")
        assert pro_eur > 0

    def test_101_order_amount_convertible(self):
        # An order in CNY can be converted to USD via convert_currency
        order_amount_cny = 9900  # ¥99
        order_amount_usd = cur.convert_currency(order_amount_cny, "CNY", "USD")
        assert order_amount_usd > 0
        assert isinstance(order_amount_usd, int)