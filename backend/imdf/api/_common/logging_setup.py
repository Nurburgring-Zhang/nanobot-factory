"""
api._common.logging_setup
=========================

Centralised structlog configuration for the IMDF API.

R7-Worker-2 (Observability):
  - Single source of truth for structured logging setup (was inlined in
    canvas_web.py before; extracted so any module can reuse it).
  - Provides:
      * configure_logging() — idempotent root logger + structlog wiring
      * get_logger(name)    — structlog BoundLogger factory
      * ContextVar helpers  — set_trace_id / get_trace_id / clear_trace_id

Behaviour:
  * Writes to stderr (console) + rotating access.log / error.log under logs/.
  * JSON output from structlog; structured kwargs (key=value) → JSON fields.
  * No print() statements — emit structured events via logger.
  * Trace context is bound per-request by the trace_id middleware.
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import structlog

# ── Trace context (per-request) ──────────────────────────────────────────────
# ContextVar so trace_id flows across awaits without explicit threading.
_trace_id_var: ContextVar[Optional[str]] = ContextVar("imdf_trace_id", default=None)
_request_id_var: ContextVar[Optional[str]] = ContextVar("imdf_request_id", default=None)


def set_trace_id(trace_id: str) -> None:
    """Bind a trace_id to the current async context."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    return _trace_id_var.get()


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


def clear_trace_context() -> None:
    _trace_id_var.set(None)
    _request_id_var.set(None)


# ── Log directory resolution ─────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/imdf/.. → nanobot-factory
_IMDF_ROOT = Path(__file__).resolve().parent.parent.parent  # api/_common/.. → backend/imdf


def _resolve_log_dir() -> Path:
    """Pick a writable logs/ directory.

    Priority:
      1. $IMDF_LOGS_DIR  (set by tests / production)
      2. <imdf_root>/logs
    """
    env = os.environ.get("IMDF_LOGS_DIR")
    if env:
        return Path(env)
    log_dir = _IMDF_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# ── Configuration ────────────────────────────────────────────────────────────
_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_CONFIGURED = False


def _bind_trace(_logger, _method_name, event_dict):
    """structlog processor — inject current trace_id / request_id into every event."""
    tid = _trace_id_var.get()
    if tid and "trace_id" not in event_dict:
        event_dict["trace_id"] = tid
    rid = _request_id_var.get()
    if rid and "request_id" not in event_dict:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    force: bool = False,
) -> None:
    """Configure root stdlib logger + structlog.

    Idempotent unless ``force=True``. Safe to call from app startup AND tests.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    log_dir = Path(log_dir) if log_dir else _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    access_log_path = log_dir / "access.log"
    error_log_path = log_dir / "error.log"

    root = logging.getLogger()
    root.setLevel(level)

    if force:
        # wipe pre-existing handlers so reloads don't double-log
        for h in list(root.handlers):
            root.removeHandler(h)

    fmt = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT)

    # Console (stderr) — INFO+
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # access.log — INFO+ rotating
    access = RotatingFileHandler(
        str(access_log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    access.setLevel(logging.INFO)
    access.setFormatter(fmt)
    root.addHandler(access)

    # error.log — WARNING+ rotating
    error = RotatingFileHandler(
        str(error_log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error.setLevel(logging.WARNING)
    error.setFormatter(fmt)
    root.addHandler(error)

    # structlog → JSON, with per-event trace_id/request_id injection
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            _bind_trace,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str = "imdf"):
    """Return a structlog BoundLogger.

    Usage::

        from api._common.logging_setup import get_logger
        log = get_logger(__name__)
        log.info("event_name", foo="bar", count=3)
    """
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)


# ── Auto-configure on import ─────────────────────────────────────────────────
# Modules that import ``get_logger`` at the top of the file will be wired up.
# Calling configure_logging() here is safe: it is idempotent.
try:
    configure_logging()
except Exception:  # pragma: no cover — never fail import on log setup
    pass