"""backend/common/logging — structlog + request-id middleware (P4-1-W1).

Each service should call :func:`setup_logging` exactly once from ``main.py``;
that wires:
  * structlog config (JSON in prod, console-pretty in dev)
  * ``RequestIdMiddleware`` (issues/propagates ``X-Request-ID``)
  * A handler that stamps ``request_id`` on every log record

The request-id is also stashed in ``contextvars`` so any nested call can
call :func:`get_logger` and have it automatically bound.
"""
from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from typing import Any, Optional

try:  # structlog is optional — fall back to stdlib if missing
    import structlog
    _HAS_STRUCTLOG = True
except Exception:  # pragma: no cover
    _HAS_STRUCTLOG = False


# ── Context var ─────────────────────────────────────────────────────────────
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
_service_name_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "service_name", default="unknown"
)


def bind_request_id(request_id: Optional[str] = None) -> str:
    """Set the current request-id (random UUID4 if ``None``) and return it."""
    rid = request_id or uuid.uuid4().hex
    _request_id_var.set(rid)
    return rid


def current_request_id() -> str:
    return _request_id_var.get()


def current_service_name() -> str:
    return _service_name_var.get()


# ── structlog wiring ────────────────────────────────────────────────────────
def _configure_structlog(level: str) -> None:
    if not _HAS_STRUCTLOG:
        return

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.KeyValueRenderer(
                key_order=["timestamp", "level", "service", "request_id", "event"],
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def _configure_stdlib_logging(level: str, service_name: str) -> None:
    """Fallback when structlog isn't installed."""
    root = logging.getLogger()
    # Drop existing handlers so we don't double-log
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    fmt = f"%(asctime)s [{service_name}] [%(levelname)s] [req=%(request_id)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Inject a default ``request_id`` so the formatter never crashes
    old_factory = logging.getLogRecordFactory()

    def _factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return record

    logging.setLogRecordFactory(_factory)


# ── Public API ──────────────────────────────────────────────────────────────
def configure_logging(level: str = "INFO", service_name: str = "unknown") -> None:
    """Configure logging once per process. Safe to call multiple times."""
    _service_name_var.set(service_name)
    if _HAS_STRUCTLOG:
        _configure_structlog(level)
    _configure_stdlib_logging(level, service_name)


def get_logger(name: Optional[str] = None) -> Any:
    """Return a structlog logger when available, else a stdlib logger."""
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)


def setup_logging(app: Any, service_name: str, level: Optional[str] = None) -> None:
    """Wire structlog + request-id middleware on *app*.

    * Sets the service name in the contextvar.
    * Adds :class:`RequestIdMiddleware` (see ``middleware.py``) so every
      request gets a ``X-Request-ID`` header (echoed back to the client).
    """
    from .config import get_service_config

    cfg = get_service_config(service_name)
    configure_logging(level=level or cfg.log_level, service_name=service_name)

    # Late import: avoid circular dep with middleware
    from .middleware import RequestIdMiddleware

    # Insert at the top so it wraps every other middleware (CORS, etc.)
    app.add_middleware(RequestIdMiddleware)


__all__ = [
    "configure_logging",
    "setup_logging",
    "bind_request_id",
    "current_request_id",
    "current_service_name",
    "get_logger",
    "_HAS_STRUCTLOG",
]