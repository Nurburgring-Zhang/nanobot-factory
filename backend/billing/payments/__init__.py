"""Payment provider package.

3 providers:
- stripe_provider.StripeProvider
- alipay_provider.AlipayProvider
- wechat_provider.WeChatPayProvider

All 3 implement the ``PaymentProvider`` ABC (base.py) and support:
- ``create_payment(order)`` — returns redirect URL / QR code URL
- ``verify_webhook(payload, signature)`` — HMAC verify
- ``refund(order)`` — initiate refund
- ``query(order)`` — poll status

Mock vs real mode is env-controlled per provider (BILLING_PROVIDER_<name>_MODE).
"""
from .base import (
    PaymentProvider, PaymentResult, WebhookEvent, PaymentStatus,
    ProviderNotConfiguredError, WebhookVerificationError,
)
from .factory import (
    get_providers, get_provider, register_provider, reset_providers,
)

__all__ = [
    "PaymentProvider", "PaymentResult", "WebhookEvent", "PaymentStatus",
    "ProviderNotConfiguredError", "WebhookVerificationError",
    "get_providers", "get_provider", "register_provider", "reset_providers",
]
