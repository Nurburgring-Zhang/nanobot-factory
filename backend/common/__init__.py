"""Common module — shared utilities for all backend services.

P1-8: Public Webhooks (公开 webhook 订阅 + 推送) — added to the public surface.
"""
# Re-export the original public surface used by the 12 service main.py files
from .factory import create_app
from .health import mount_health, register_metrics
from .error_handler import register_exception_handlers, BusinessError
from .responses import success_response, error_response, paginated_response
from .db import setup_db, get_db, get_engine, get_session_factory, ping, init_db
from .config import get_service_config, load_config, ServiceConfig
from .auth import get_current_user, require_role, require_role_dep, issue_access_token
from .logging import setup_logging, get_logger, configure_logging
from .middleware import mount_cors, mount_middleware, RequestIdMiddleware

# P1-8: Public webhooks
from .webhooks import (
    SUPPORTED_EVENTS, SIGNATURE_HEADER, WebhookSubscription, EmitRecord,
    register_webhook, list_webhooks, get_webhook, delete_webhook, update_webhook,
    emit, list_emits, _reset_webhooks,
)
from .webhooks_routes import router as webhooks_router

# P10-E: Field-level AES-256-GCM encryption for sensitive fields
# (API keys, PII, payment cards) — see common/encryption.py
from .encryption import FieldEncryption, EncryptionError


__all__ = [
    # Original surface
    "create_app", "mount_health", "register_exception_handlers", "BusinessError",
    "success_response", "error_response", "paginated_response",
    "setup_db", "get_db", "get_engine", "get_session_factory", "ping", "init_db",
    "get_service_config", "load_config", "ServiceConfig",
    "get_current_user", "require_role", "require_role_dep", "issue_access_token",
    "setup_logging", "get_logger", "configure_logging",
    "mount_cors", "mount_middleware", "RequestIdMiddleware",
    "register_metrics",
    # P1-8 webhooks
    "SUPPORTED_EVENTS", "SIGNATURE_HEADER", "WebhookSubscription", "EmitRecord",
    "register_webhook", "list_webhooks", "get_webhook", "delete_webhook", "update_webhook",
    "emit", "list_emits", "_reset_webhooks", "webhooks_router",
    # P10-E encryption
    "FieldEncryption", "EncryptionError",
]
