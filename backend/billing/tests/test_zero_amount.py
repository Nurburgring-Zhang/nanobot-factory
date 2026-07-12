"""P17-D1 Hidden #2: 0 amount explicit rejection tests.

Verify:
- attach_tax_to_order with amount_cents=0 raises ValueError
- Same for amount=0 (alias field)
- 100 calls with amount=0: all raise
- Non-zero amounts work as before
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.tax import attach_tax_to_order


class TestZeroAmountRejection:
    """Hidden #2 — Zero-amount orders must be rejected by attach_tax_to_order."""

    def test_001_zero_amount_raises(self):
        """Single zero-amount call raises ValueError."""
        with pytest.raises(ValueError, match="amount_cents must be > 0"):
            attach_tax_to_order({"amount_cents": 0})

    def test_002_zero_amount_alias_raises(self):
        """Same for the 'amount' alias field."""
        with pytest.raises(ValueError, match="amount_cents must be > 0"):
            attach_tax_to_order({"amount": 0})

    def test_003_missing_amount_raises(self):
        """No amount at all → also 0 → must raise."""
        with pytest.raises(ValueError, match="amount_cents must be > 0"):
            attach_tax_to_order({})

    def test_004_negative_amount_raises(self):
        """Negative amounts still rejected (existing behavior preserved)."""
        with pytest.raises(ValueError):
            attach_tax_to_order({"amount_cents": -1})

    def test_005_100_zero_amount_calls_all_raise(self):
        """Spec: 100 calls with amount=0, 全部 raise."""
        rejected_count = 0
        for i in range(100):
            try:
                attach_tax_to_order({"amount_cents": 0, "id": i})
            except ValueError as e:
                if "amount_cents must be > 0" in str(e):
                    rejected_count += 1
        assert rejected_count == 100, f"only {rejected_count}/100 rejected"

    def test_006_positive_amount_works(self):
        """Non-zero amount proceeds normally."""
        order = {"amount_cents": 10000, "country": "CN"}
        result = attach_tax_to_order(order)
        assert "tax_amount" in result
        assert result["total_amount"] > result["tax_amount"]
        assert result["total_amount"] >= 10000

    def test_007_positive_one_cent_works(self):
        """Smallest non-zero amount (1 cent) is OK."""
        order = {"amount_cents": 1}
        result = attach_tax_to_order(order)
        assert "tax_amount" in result

    def test_008_error_message_helpful(self):
        """Error message must clearly state the requirement."""
        try:
            attach_tax_to_order({"amount_cents": 0})
        except ValueError as e:
            msg = str(e)
            assert "amount_cents" in msg
            assert "must be > 0" in msg or "0" in msg

    def test_009_explicit_zero_with_country_raises(self):
        """Zero amount with country/category still raises."""
        with pytest.raises(ValueError):
            attach_tax_to_order(
                {"amount_cents": 0, "country": "US", "category": "standard"}
            )

    def test_010_calc_tax_zero_is_still_ok(self):
        """calc_tax itself still allows 0 (this rule applies to attach_tax_to_order)."""
        from billing.tax import calc_tax
        # calc_tax allows 0 (it's a low-level calculation)
        # Only attach_tax_to_order rejects 0 as a guard
        result = calc_tax(0, "CN", "standard")
        assert result.tax_cents == 0
        assert result.total_cents == 0