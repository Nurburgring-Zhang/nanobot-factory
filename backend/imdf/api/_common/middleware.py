"""
api._common.middleware
======================

R7-Worker-2: Observability middleware.

Provides two Starlette / FastAPI middleware classes:

  1. TraceIDMiddleware
     - Reads ``X-Trace-Id`` from the incoming request; if absent, generates a
       new UUID4 hex.
     - Binds the trace_id (and request_id) into the logging ContextVar so all
       structlog events emitted during the request are auto-tagged.
     - Echoes ``X-Trace-Id`` (and ``X-Request-Id``) back on the response.

  2. RequestLoggingMiddleware
     - Emits one structured "request completed" event with method, path,
       status_code, elapsed_ms, trace_id, request_id.
     - Slow-request warning (>1s).
     - Forwards to ``engines.metrics.record_request`` for Prometheus.

Both middlewares are designed to be registered in canvas_web.py (and any
future FastAPI app) — kept here so they can be reused and unit-tested in
isolation without the full app context.
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from api._common.logging_setup import (
    clear_trace_context,
    configure_logging,
    get_logger,
    set_request_id,
    set_trace_id,
)

# initialise on import — idempotent
configure_logging()
logger = get_logger("imdf.middleware")

# Header names (lowercase canonical form per RFC 7230)
TRACE_ID_HEADER = "x-trace-id"
REQUEST_ID_HEADER = "x-request-id"

# Path normalization helpers (for metrics aggregation) ────────────────────────
_UUID_RE = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_DIGITS_RE = re.compile(r"/\d{4,}")


def _normalize_path(path: str) -> str:
    """Replace UUIDs and long digit runs with placeholders for metric aggregation."""
    path = _UUID_RE.sub("/{uuid}", path)
    path = _DIGITS_RE.sub("/{id}", path)
    return path


# ── Trace-ID Middleware ───────────────────────────────────────────────────────
class TraceIDMiddleware(BaseHTTPMiddleware):
    """Bind trace_id / request_id from headers (or generate new) into logging context.

    The X-Trace-Id header is *propagated* — if upstream (gateway / another
    service) sent one, we honour it; otherwise we mint a fresh UUID4. The same
    trace_id is echoed back to the client so end-to-end correlation works.

    The X-Request-Id is always a server-minted UUID4 (per-request, never
    shared) so logs can be cross-referenced even if no upstream trace was
    provided.
    """

    def __init__(self, app: ASGIApp, header_name: str = TRACE_ID_HEADER):
        super().__init__(app)
        self.header_name = header_name.lower()

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_trace = request.headers.get(self.header_name)
        if incoming_trace:
            # accept upstream trace, but sanitise: cap length, strip control chars
            trace_id = _sanitize_header(incoming_trace)
            if not trace_id:
                trace_id = uuid.uuid4().hex
        else:
            trace_id = uuid.uuid4().hex

        request_id = uuid.uuid4().hex
        set_trace_id(trace_id)
        set_request_id(request_id)

        try:
            response = await call_next(request)
        finally:
            # context is per-task; safest to clear after dispatch returns
            clear_trace_context()

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Request-Id"] = request_id
        return response


def _sanitize_header(value: str, max_len: int = 128) -> Optional[str]:
    """Trim & validate an incoming trace-id header. Returns None if invalid."""
    if not value:
        return None
    v = value.strip()
    if not v or len(v) > max_len:
        return None
    # only allow URL-safe + uuid-safe chars (defensive against header injection)
    if not re.fullmatch(r"[A-Za-z0-9._\-:]+", v):
        return None
    return v


# ── Request-logging Middleware ────────────────────────────────────────────────
SLOW_THRESHOLD_SEC = 1.0


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured log event per HTTP request, with timing.

    Logs at INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx. Slow requests
    (>1s by default) get an additional WARNING. Metrics are forwarded to
    ``engines.metrics.record_request`` so /metrics stays consistent.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        start_iso = datetime.now(timezone.utc).isoformat()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # let the outer FastAPI exception handler render the 500 response
            logger.exception(
                "request failed",
                method=request.method,
                path=request.url.path,
                exc_info=True,
            )
            raise
        finally:
            elapsed_sec = time.perf_counter() - start
            elapsed_ms = round(elapsed_sec * 1000, 1)
            event = {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "client": request.client.host if request.client else None,
                "started_at": start_iso,
            }
            if status_code >= 500:
                logger.error("request completed", **event)
            elif status_code >= 400:
                logger.warning("request completed", **event)
            else:
                logger.info("request completed", **event)

            if elapsed_sec > SLOW_THRESHOLD_SEC:
                logger.warning(
                    "slow request detected",
                    **event,
                    slow_threshold_s=SLOW_THRESHOLD_SEC,
                )

            # Forward to Prometheus metrics (best-effort)
            try:
                from engines.metrics import record_request as metrics_record
                metrics_record(
                    request.method,
                    _normalize_path(request.url.path),
                    status_code,
                    elapsed_sec,
                )
            except Exception as e:  # pragma: no cover
                logger.warning("metrics recording failed", error=str(e)[:120])


__all__ = [
    "TraceIDMiddleware",
    "RequestLoggingMiddleware",
    "TRACE_ID_HEADER",
    "REQUEST_ID_HEADER",
    "_normalize_path",
    "SLOW_THRESHOLD_SEC",
]