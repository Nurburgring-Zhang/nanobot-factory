"""Payment provider factory — register / lookup providers at runtime."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import PaymentProvider


_REGISTRY: Dict[str, PaymentProvider] = {}


def register_provider(provider: PaymentProvider) -> None:
    """Register a provider (overwrites by name)."""
    _REGISTRY[provider.name] = provider


def get_provider(name: str) -> PaymentProvider:
    """Lookup a provider by name (e.g. "stripe"). Raises KeyError if not found."""
    if name not in _REGISTRY:
        raise KeyError(
            f"payment provider not registered: {name!r}. "
            f"available: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def get_providers() -> List[PaymentProvider]:
    """Return list of all registered providers."""
    return list(_REGISTRY.values())


def reset_providers() -> None:
    """Clear registry (test helper)."""
    _REGISTRY.clear()


def register_defaults() -> None:
    """Register the 3 default providers (Stripe/Alipay/WeChat) in mock mode."""
    from .stripe_provider import StripeProvider
    from .alipay_provider import AlipayProvider
    from .wechat_provider import WeChatPayProvider
    register_provider(StripeProvider())
    register_provider(AlipayProvider())
    register_provider(WeChatPayProvider())


# Eager-register defaults on import
register_defaults()


__all__ = [
    "register_provider", "get_provider", "get_providers", "reset_providers",
    "register_defaults",
]
