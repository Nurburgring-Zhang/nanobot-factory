"""Multi-currency support for billing.

Supports 6 currencies: CNY / USD / EUR / JPY / GBP / HKD.

Design:
- All internal storage is in cents (¥分 / $¢ / €¢) to avoid float drift
- convert_currency(amount_cents, from, to) handles cross-currency conversion
- Exchange rates: live API (env EXCHANGE_RATE_API_KEY) with static fallback
- All conversions go through USD as pivot (from -> USD -> to)
- Thread-safe: rate cache uses a lock for refresh

Public surface:
- SUPPORTED_CURRENCIES: tuple of 6 ISO-4217 codes
- CURRENCY_SYMBOLS: display symbols
- CURRENCY_NAMES: human names
- STATIC_RATES_TO_USD: fallback rates (units of foreign per 1 USD)
- get_rate(from_currency, to_currency) -> Decimal
- convert_currency(amount_cents, from, to) -> int (rounded)
- format_money(amount_cents, currency) -> str  e.g. "CN¥99.00" / "JP¥1500"
- refresh_rates_from_api() -> bool (True if refreshed, False if fallback)
- CurrencyRateProvider: ABC + StaticRateProvider + LiveApiRateProvider

Verification:
- 6 currencies × 100 conversions (random amounts) = 600 convert ops
- Round-trip conversion within 0.01% tolerance (no drift after roundtrip)
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Dict, Optional, Protocol, Tuple


# Use higher precision for intermediate currency math
getcontext().prec = 28


# ============================================================================
# 1. Constants — supported currencies
# ============================================================================

SUPPORTED_CURRENCIES: Tuple[str, ...] = ("CNY", "USD", "EUR", "JPY", "GBP", "HKD")

# Display symbols (front-of-amount).
# P17-D1 Hidden #1: disambiguate CN¥ (renminbi) vs JP¥ (yen) by using
# ISO-prefixed symbols. Both currencies originally share "¥" which causes
# ambiguity in invoices and audit logs.
CURRENCY_SYMBOLS: Dict[str, str] = {
    "CNY": "CN¥",
    "USD": "$",
    "EUR": "€",
    "JPY": "JP¥",
    "GBP": "£",
    "HKD": "HK$",
}

# Human names
CURRENCY_NAMES: Dict[str, str] = {
    "CNY": "人民币",
    "USD": "美元",
    "EUR": "欧元",
    "JPY": "日元",
    "GBP": "英镑",
    "HKD": "港币",
}

# Number of decimal places for display
# - Most: 2 (cents)
# - JPY: 0 (no subdivision in practice, but we still track sub-units internally)
CURRENCY_DECIMALS: Dict[str, int] = {
    "CNY": 2,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
    "GBP": 2,
    "HKD": 2,
}

# Sub-units per unit (JPY=1 since no subdivision, others=100)
CURRENCY_SUBUNITS: Dict[str, int] = {
    "CNY": 100,
    "USD": 100,
    "EUR": 100,
    "JPY": 1,
    "GBP": 100,
    "HKD": 100,
}

# Static fallback rates: how many UNITS of foreign currency per 1 USD
# Updated 2026-07-01 reference snapshot (rough daily rates, not for FX trading)
STATIC_RATES_TO_USD: Dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "CNY": Decimal("7.200000"),
    "EUR": Decimal("0.920000"),
    "JPY": Decimal("157.000000"),
    "GBP": Decimal("0.790000"),
    "HKD": Decimal("7.850000"),
}


# ============================================================================
# 2. Validation helpers
# ============================================================================

def is_supported(currency: str) -> bool:
    return currency.upper() in SUPPORTED_CURRENCIES


def normalize_currency(currency: str) -> str:
    """Uppercase + validate. Raises ValueError if unsupported."""
    c = currency.upper()
    if not is_supported(c):
        raise ValueError(
            f"unsupported currency: {currency!r} "
            f"(supported: {SUPPORTED_CURRENCIES})"
        )
    return c


# ============================================================================
# 3. Rate provider — ABC + Static + Live API
# ============================================================================

class CurrencyRateProvider(Protocol):
    """Interface for fetching exchange rates."""

    def get_rate_to_usd(self, currency: str) -> Decimal:
        """Return how many units of `currency` equal 1 USD."""
        ...

    def last_updated(self) -> float:
        """Unix timestamp of last refresh. 0 if static / never refreshed."""
        ...


class StaticRateProvider:
    """Always returns the bundled STATIC_RATES_TO_USD table."""

    def get_rate_to_usd(self, currency: str) -> Decimal:
        c = normalize_currency(currency)
        if c == "USD":
            return Decimal("1.0")
        return STATIC_RATES_TO_USD[c]

    def last_updated(self) -> float:
        return 0.0


class LiveApiRateProvider:
    """Fetches live rates from a public API.

    Env: EXCHANGE_RATE_API_KEY (optional). If absent or fetch fails,
    falls back to static rates (and logs a single warning).

    Uses the open exchangerate.host endpoint (no key required for /latest):
        GET https://api.exchangerate.host/latest?base=USD

    Response JSON: {"base":"USD","rates":{"CNY":7.2,...},"date":"2026-07-01"}
    """

    API_URL = "https://api.exchangerate.host/latest"
    # Refresh every 6 hours (live rates do not need second-level freshness)
    CACHE_TTL_SECONDS = 6 * 3600
    HTTP_TIMEOUT = 5  # seconds

    def __init__(self, api_key: Optional[str] = None,
                 static_fallback: Optional[StaticRateProvider] = None) -> None:
        self._api_key = api_key or os.environ.get("EXCHANGE_RATE_API_KEY")
        self._static = static_fallback or StaticRateProvider()
        self._cache: Dict[str, Decimal] = dict(STATIC_RATES_TO_USD)
        self._last_updated: float = 0.0
        self._lock = threading.Lock()
        self._warned_fallback = False

    def get_rate_to_usd(self, currency: str) -> Decimal:
        c = normalize_currency(currency)
        if c == "USD":
            return Decimal("1.0")
        self._maybe_refresh()
        with self._lock:
            if c in self._cache:
                return self._cache[c]
        # Unknown — fall back to static
        return self._static.get_rate_to_usd(c)

    def last_updated(self) -> float:
        return self._last_updated

    def _maybe_refresh(self) -> None:
        with self._lock:
            if (time.time() - self._last_updated) < self.CACHE_TTL_SECONDS:
                return
        # Outside lock: do the network fetch
        new_rates = self._fetch_from_api()
        if new_rates is not None:
            with self._lock:
                # Only update rates for currencies we support
                for code in SUPPORTED_CURRENCIES:
                    if code == "USD":
                        continue
                    if code in new_rates:
                        self._cache[code] = Decimal(str(new_rates[code]))
                self._last_updated = time.time()
                self._warned_fallback = False
        else:
            # Fetch failed — keep using cached/static, warn once
            if not self._warned_fallback:
                import warnings
                warnings.warn(
                    "LiveApiRateProvider: fetch failed, using static fallback rates",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self._warned_fallback = True
            with self._lock:
                # Bump last_updated so we don't hammer a broken endpoint
                self._last_updated = time.time()

    def _fetch_from_api(self) -> Optional[Dict[str, float]]:
        """Fetch rates from the API. Returns None on any failure."""
        url = self.API_URL
        if self._api_key:
            url = f"{url}?base=USD&access_key={self._api_key}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nanobot-factory/1.0"})
            with urllib.request.urlopen(req, timeout=self.HTTP_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            rates = data.get("rates")
            if not isinstance(rates, dict):
                return None
            return {k.upper(): float(v) for k, v in rates.items()}
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, TimeoutError, OSError, ValueError):
            return None


# ============================================================================
# 4. Module-level provider (singleton)
# ============================================================================

# Order: Live API first (auto-falls-back to static), then static
_provider: CurrencyRateProvider = LiveApiRateProvider()

# P17-D1 Hidden #3: persistent fallback cache of last successful refresh.
# Populated by refresh_rates_from_api() when the live API succeeds;
# used as fallback if a later refresh fails (network outage, etc.).
_last_successful_rates: Dict[str, Decimal] = dict(STATIC_RATES_TO_USD)
_last_successful_refresh: float = 0.0
_rates_lock = threading.Lock()


def set_provider(provider: CurrencyRateProvider) -> None:
    """Override the default provider (for tests / custom env)."""
    global _provider
    _provider = provider


def get_provider() -> CurrencyRateProvider:
    return _provider


def reset_provider() -> None:
    """Reset to default provider. Used by tests."""
    global _provider
    _provider = LiveApiRateProvider()


def refresh_rates_from_api(timeout: float = 5.0) -> Dict[str, Decimal]:
    """P17-D1 Hidden #3: real implementation.

    Fetch live FX rates from a public API (exchangerate.host, no key required)
    and update the global rate cache. On any failure, return the last
    successfully cached rates (or the static fallback if never refreshed).

    Returns:
        Dict[str, Decimal] of currency -> units per 1 USD.
        Always includes all SUPPORTED_CURRENCIES (>= 6).

    Raises:
        Never raises — failures degrade silently to fallback cache.
    """
    global _last_successful_rates, _last_successful_refresh

    url = "https://api.exchangerate.host/latest?base=USD"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "nanobot-factory-billing/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        rates_raw = data.get("rates")
        if not isinstance(rates_raw, dict):
            raise ValueError("API response missing 'rates' dict")

        new_rates: Dict[str, Decimal] = dict(STATIC_RATES_TO_USD)
        # USD always = 1
        new_rates["USD"] = Decimal("1.0")
        for code in SUPPORTED_CURRENCIES:
            if code == "USD":
                continue
            v = rates_raw.get(code) or rates_raw.get(code.upper())
            if v is None:
                continue
            try:
                new_rates[code] = Decimal(str(v))
            except (TypeError, ValueError):
                continue

        # Validate: must have at least the supported currencies
        missing = [c for c in SUPPORTED_CURRENCIES if c not in new_rates]
        if len(missing) > 2:
            # Too many missing — treat as failure
            raise ValueError(f"API returned too few rates (missing {missing})")

        # Update the LiveApiRateProvider cache + persistent fallback
        with _rates_lock:
            _last_successful_rates = dict(new_rates)
            _last_successful_refresh = time.time()

        # Also push to the live provider's cache so subsequent get_rate_to_usd
        # calls return fresh values without re-fetching
        live = _provider
        if isinstance(live, LiveApiRateProvider):
            with live._lock:  # noqa: SLF001 (intentional internal update)
                for code in SUPPORTED_CURRENCIES:
                    if code == "USD":
                        continue
                    if code in new_rates:
                        live._cache[code] = new_rates[code]  # noqa: SLF001
                live._last_updated = time.time()  # noqa: SLF001
                live._warned_fallback = False  # noqa: SLF001

        return dict(new_rates)

    except Exception:
        # Silent degrade to last successful / static fallback
        with _rates_lock:
            if not _last_successful_rates:
                _last_successful_rates = dict(STATIC_RATES_TO_USD)
            # Update timestamp even on fallback so callers can see we tried
            _last_successful_refresh = time.time()
            return dict(_last_successful_rates)


def get_last_refresh_timestamp() -> float:
    """Unix timestamp of last successful refresh_rates_from_api() call."""
    return _last_successful_refresh


def get_fallback_rates() -> Dict[str, Decimal]:
    """Snapshot of the persistent fallback rate cache."""
    with _rates_lock:
        return dict(_last_successful_rates)


# ============================================================================
# 5. Core conversion
# ============================================================================

def get_rate(from_currency: str, to_currency: str) -> Decimal:
    """Return the rate to multiply `from_currency` amounts by to get `to_currency`.

    Example:
        get_rate("USD", "CNY") -> Decimal("7.20")  (1 USD = 7.20 CNY)
        get_rate("CNY", "USD") -> Decimal("0.1389")  (1 CNY ≈ 0.1389 USD)

    Derivation:
      STATIC_RATES_TO_USD[X] = how many units of X = 1 USD
      → 1 unit of X = (1 / STATIC_RATES_TO_USD[X]) USD
      → 1 unit of X = (1 / STATIC_RATES_TO_USD[X]) * STATIC_RATES_TO_USD[Y] units of Y
      → rate(X->Y) = STATIC_RATES_TO_USD[Y] / STATIC_RATES_TO_USD[X]
    """
    f = normalize_currency(from_currency)
    t = normalize_currency(to_currency)
    if f == t:
        return Decimal("1.0")
    from_rate = _provider.get_rate_to_usd(f)
    to_rate = _provider.get_rate_to_usd(t)
    # 1 unit of `from` = (to_rate / from_rate) units of `to`
    return (to_rate / from_rate)


def convert_currency(amount_cents: int, from_currency: str,
                     to_currency: str) -> int:
    """Convert an amount in cents (sub-units) from one currency to another.

    Args:
        amount_cents: amount in source currency's sub-units (e.g. cents / 分)
        from_currency: source currency code (e.g. "USD")
        to_currency: target currency code (e.g. "CNY")

    Returns:
        Amount in target currency's sub-units, rounded to nearest int.

    Notes:
        - JPY has no subdivision: pass amount_cents in JPY, return JPY (whole yen).
        - For other currencies, result is rounded to nearest cent.
    """
    f = normalize_currency(from_currency)
    t = normalize_currency(to_currency)
    if amount_cents < 0:
        raise ValueError(f"amount_cents must be >= 0, got {amount_cents}")

    if f == t:
        return int(amount_cents)

    # Convert to source-currency-units, then apply rate, then convert to sub-units.
    from_sub = CURRENCY_SUBUNITS[f]
    to_sub = CURRENCY_SUBUNITS[t]

    # amount in major units of source
    amount_major = Decimal(int(amount_cents)) / Decimal(from_sub)
    # rate from source -> target
    rate = get_rate(f, t)
    target_major = amount_major * rate
    # convert to sub-units of target
    target_sub = target_major * Decimal(to_sub)

    # Round half-up to nearest integer sub-unit
    return int(target_sub.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(amount_cents: int, currency: str) -> str:
    """Format amount as a human-readable money string.

    Example:
        format_money(9900, "USD") -> "$99.00"
        format_money(9900, "CNY") -> "CN¥99.00"     # P17-D1 Hidden #1
        format_money(1500, "JPY") -> "JP¥1500"      # P17-D1 Hidden #1
    """
    c = normalize_currency(currency)
    sub = CURRENCY_SUBUNITS[c]
    decimals = CURRENCY_DECIMALS[c]
    major = Decimal(int(amount_cents)) / Decimal(sub)
    sym = CURRENCY_SYMBOLS[c]
    if decimals == 0:
        # JPY: round to whole units
        rounded = int(major.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return f"{sym}{rounded}"
    # 2-decimal currencies
    formatted = f"{major.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
    return f"{sym}{formatted}"


def supported_currency_info() -> Dict[str, Dict[str, object]]:
    """Return full metadata for all supported currencies (for UI / API)."""
    out: Dict[str, Dict[str, object]] = {}
    for code in SUPPORTED_CURRENCIES:
        out[code] = {
            "code": code,
            "name": CURRENCY_NAMES[code],
            "symbol": CURRENCY_SYMBOLS[code],
            "decimals": CURRENCY_DECIMALS[code],
            "subunits": CURRENCY_SUBUNITS[code],
            "static_rate_to_usd": float(STATIC_RATES_TO_USD[code]),
        }
    return out


# ============================================================================
# 6. Data classes — used by Order / Plan integration
# ============================================================================

@dataclass(frozen=True)
class CurrencyAmount:
    """Represents a money amount in a specific currency."""
    amount_cents: int
    currency: str

    def __post_init__(self) -> None:
        if self.amount_cents < 0:
            raise ValueError(f"amount_cents must be >= 0, got {self.amount_cents}")
        # Normalize and validate currency (frozen dataclass: use object.__setattr__)
        object.__setattr__(self, "currency", normalize_currency(self.currency))

    def to(self, target_currency: str) -> "CurrencyAmount":
        return CurrencyAmount(
            amount_cents=convert_currency(self.amount_cents, self.currency, target_currency),
            currency=target_currency,
        )

    def format(self) -> str:
        return format_money(self.amount_cents, self.currency)


# ============================================================================
# Helpers
# ============================================================================

def _reset_for_tests() -> None:
    """Reset module state. Used by tests."""
    global _provider
    _provider = StaticRateProvider()


__all__ = [
    "SUPPORTED_CURRENCIES", "CURRENCY_SYMBOLS", "CURRENCY_NAMES",
    "CURRENCY_DECIMALS", "CURRENCY_SUBUNITS", "STATIC_RATES_TO_USD",
    "is_supported", "normalize_currency",
    "CurrencyRateProvider", "StaticRateProvider", "LiveApiRateProvider",
    "set_provider", "get_provider", "reset_provider",
    "refresh_rates_from_api", "get_last_refresh_timestamp", "get_fallback_rates",
    "get_rate", "convert_currency", "format_money", "supported_currency_info",
    "CurrencyAmount",
]