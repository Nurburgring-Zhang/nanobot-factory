"""P17-D1 Hidden #3: refresh_rates_from_api real implementation tests.

Verify:
- refresh_rates_from_api returns >= 6 currencies
- Returns Dict[str, Decimal]
- Falls back to last successful / static on network failure
- Side effect: updates _last_successful_rates cache
- Module-level function (not class method)
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing import currency as cur


class TestRefreshRatesFromAPI:
    """Hidden #3 — Real implementation of refresh_rates_from_api."""

    def test_001_returns_dict_of_decimals(self):
        """refresh_rates_from_api returns Dict[str, Decimal]."""
        rates = cur.refresh_rates_from_api()
        assert isinstance(rates, dict)
        assert len(rates) >= len(cur.SUPPORTED_CURRENCIES)
        for code, rate in rates.items():
            assert isinstance(rate, Decimal)

    def test_002_at_least_six_currencies(self):
        """Spec: 调用 1 次, rates dict 至少 6 币种."""
        rates = cur.refresh_rates_from_api()
        assert len(rates) >= 6
        # All 6 supported currencies present
        for code in cur.SUPPORTED_CURRENCIES:
            assert code in rates

    def test_003_usd_is_one(self):
        """USD must always be 1."""
        rates = cur.refresh_rates_from_api()
        assert rates["USD"] == Decimal("1.0")

    def test_004_rates_are_positive(self):
        rates = cur.refresh_rates_from_api()
        for code, rate in rates.items():
            assert rate > 0, f"{code} rate must be positive, got {rate}"

    def test_005_fallback_rates_persisted(self):
        """After a successful refresh, get_fallback_rates returns the data."""
        cur.refresh_rates_from_api()
        fb = cur.get_fallback_rates()
        assert isinstance(fb, dict)
        assert len(fb) >= 6
        assert fb["USD"] == Decimal("1.0")

    def test_006_last_refresh_timestamp_updated(self):
        """After refresh, get_last_refresh_timestamp > 0."""
        cur.refresh_rates_from_api()
        ts = cur.get_last_refresh_timestamp()
        assert ts > 0
        import time
        # Within the last 60s
        assert abs(time.time() - ts) < 60

    def test_007_module_level_function(self):
        """refresh_rates_from_api is at module level (not class)."""
        # Must be callable as currency.refresh_rates_from_api()
        assert hasattr(cur, "refresh_rates_from_api")
        assert callable(cur.refresh_rates_from_api)

    def test_008_uses_exchangerate_api_or_fallback(self):
        """Either live API succeeds OR fallback is used. Never raises."""
        # Should never raise under any circumstance
        try:
            rates = cur.refresh_rates_from_api(timeout=3.0)
            assert rates is not None
            assert len(rates) >= 6
        except Exception as e:
            pytest.fail(f"refresh_rates_from_api raised unexpectedly: {e}")

    def test_009_short_timeout_still_works(self):
        """Even with 1s timeout, must not raise."""
        rates = cur.refresh_rates_from_api(timeout=1.0)
        assert len(rates) >= 6

    def test_010_currency_amount_uses_refreshed_rates(self):
        """After refresh, conversions use the new rates (USD->CNY)."""
        cur.refresh_rates_from_api()
        # USD 100 cents = $1 = some amount of CNY
        result = cur.convert_currency(100, "USD", "CNY")
        assert result > 0  # any positive amount