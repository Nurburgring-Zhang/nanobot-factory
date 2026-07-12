"""backend/common/middleware — CORS + request-id + CSRF middleware.

Three middlewares, each small enough to live in its own file:

  * ``RequestIdMiddleware``   — issues / propagates ``X-Request-ID``
  * ``mount_cors``            — convenience wrapper for FastAPI ``CORSMiddleware``
  * ``CSRFMiddleware``        — Origin-header allow-list for unsafe methods
                                (R2-NEW-03 / R2-NEW-07 fix, P21 P2 P2)

Why split out from ``logging.py``? ``logging.py`` needs the request-id
middleware too, but it imports from here; to avoid the circular import
``middleware`` doesn't import ``logging``.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Iterable, List, Optional, Union

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


# P21 P2 P2 (R2-NEW-07): default CORS allow-list no longer contains ``*``.
# Production deployers must set ``CORS_ALLOW_ORIGINS`` to the comma-separated
# list of allowed origins; the localhost dev defaults are only used as a
# last-resort fallback when the env var is unset / empty.
DEFAULT_CORS_ALLOW_ORIGINS: tuple = (
    "http://localhost:5173",
    "http://localhost:8765",
)


def _read_cors_origins(explicit: Optional[Iterable[str]] = None) -> List[str]:
    """Resolve the effective CORS allow-list.

    Precedence (highest first):
      1. ``explicit`` argument (caller-supplied list)
      2. ``CORS_ALLOW_ORIGINS`` env var (comma-separated)
      3. ``DEFAULT_CORS_ALLOW_ORIGINS`` (localhost dev origins)

    The legacy fallback to ``["*"]`` is **removed** — it caused R2-NEW-07
    (CORS misconfiguration with credentials).
    """
    if explicit is not None:
        parsed = [o.strip() for o in explicit if o and o.strip()]
        if parsed:
            return parsed
    env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if env:
        parsed = [o.strip() for o in env.split(",") if o.strip()]
        if parsed:
            return parsed
    return list(DEFAULT_CORS_ALLOW_ORIGINS)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Per-request id middleware.

    Behaviour:
      * On entry, look for an inbound ``X-Request-ID`` header. If absent,
        generate a random UUID4 hex string.
      * Bind it to the logging contextvar so all log lines during the
        request carry the same id.
      * Echo it back on the response as ``X-Request-ID``.
      * Stamp the request latency on the response as ``X-Response-Time-Ms``.
    """

    HEADER_IN = "X-Request-ID"
    HEADER_OUT = "X-Request-ID"
    HEADER_LATENCY = "X-Response-Time-Ms"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Late import to break the import cycle (logging → middleware → logging)
        from .logging import bind_request_id

        incoming = request.headers.get(self.HEADER_IN)
        rid = bind_request_id(incoming or uuid.uuid4().hex)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # We still want the header on error responses (FastAPI's default
            # 500 handler builds the response). We re-raise and let the
            # exception handler chain add the headers.
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0

        # ``Response`` here may be a streaming response; setting headers
        # after the body is sent is a no-op for some types — that's fine.
        try:
            response.headers[self.HEADER_OUT] = rid
            response.headers[self.HEADER_LATENCY] = f"{elapsed_ms:.2f}"
        except Exception:  # pragma: no cover
            pass
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Origin-header allow-list check for state-changing requests.

    P21 P2 P2 — R2-NEW-03 (CWE-352) fix.

    Rationale
    ---------
    The previous ``mount_cors`` defaulted to ``allow_origins="*"`` with
    ``allow_credentials=True``; Starlette then echoes the request origin
    while keeping ``Access-Control-Allow-Credentials: true``, which lets a
    cross-site attacker ride the user's cookies. Combined with the
    unauthenticated ``POST /api/v2/users`` route (R2-09), this was a
    full tenant takeover via drive-by CSRF.

    This middleware is a *defence-in-depth* layer that rejects unsafe
    requests whose ``Origin`` header is missing or not in the allow-list
    before the route ever runs. The allow-list is read from
    ``CORS_ALLOW_ORIGINS`` (same source as ``CORSMiddleware``) so the two
    layers stay in sync.

    Behaviour
    ---------
    * Safe methods (``GET``, ``HEAD``, ``OPTIONS``) and CORS preflight are
      always allowed through — the CORS layer is responsible for those.
    * Unsafe methods (``POST``, ``PUT``, ``PATCH``, ``DELETE``) MUST have
      an ``Origin`` header that matches an entry in the allow-list.
    * Missing ``Origin`` → 403 ``{"error": "CSRF: invalid or missing Origin"}``.
    * ``Origin`` not in allow-list → 403 with the same body.
    * Allow-list comparison is case-insensitive on the host part
      (``Http://Localhost:5173`` matches ``http://localhost:5173``) and
      tolerates a trailing slash.

    Escape hatches
    --------------
    * ``CSRF_ENABLED=false`` disables the middleware entirely (test mode).
    * ``allowed_origins`` constructor arg overrides the env-driven list
      (used by tests for hermetic origins).
    """

    #: HTTP methods that can mutate server state and therefore MUST
    #: pass the Origin check.  Per RFC 7231 §4.2.1 these are the
    #: "unsafe" methods; CORS preflight is always ``OPTIONS`` which is
    #: in the safe set and is short-circuited below.
    UNSAFE_METHODS: frozenset = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(
        self,
        app,
        *,
        allowed_origins: Optional[Iterable[str]] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        super().__init__(app)
        origins = _read_cors_origins(allowed_origins)
        # Wildcard explicitly disables the Origin check — the deployer
        # has opted out of the protection. We log a warning so a stray
        # ``CORS_ALLOW_ORIGINS=*`` doesn't silently re-introduce R2-NEW-03.
        self._allow_wildcard: bool = "*" in origins
        # Normalise for case-insensitive compare and tolerate trailing
        # slashes (``http://x/`` vs ``http://x``).
        self.allowed_origins: frozenset = frozenset(
            o.rstrip("/").lower() for o in origins if o != "*"
        )
        if enabled is None:
            enabled = os.environ.get("CSRF_ENABLED", "true").lower() not in (
                "0", "false", "no", "",
            )
        self.enabled: bool = bool(enabled)
        if self.enabled and self._allow_wildcard:
            logger.warning(
                "CSRFMiddleware: CORS allow-list contains '*'; CSRF Origin "
                "check is effectively disabled. Set CORS_ALLOW_ORIGINS to "
                "specific origins (R2-NEW-03 mitigation)."
            )

    async def dispatch(self, request: Request, call_next) -> Response:
        # ── Bypass paths ─────────────────────────────────────────────────
        if not self.enabled or self._allow_wildcard:
            return await call_next(request)
        # Safe methods (GET/HEAD/OPTIONS) are exempt — the CORS layer
        # handles preflight (which is always OPTIONS + the
        # ``Access-Control-Request-Method`` header).
        if request.method not in self.UNSAFE_METHODS:
            return await call_next(request)
        # Belt-and-braces: never run the Origin check on a preflight.
        if (
            request.method == "OPTIONS"
            and request.headers.get("Access-Control-Request-Method")
        ):
            return await call_next(request)

        # ── Origin allow-list check ──────────────────────────────────────
        origin = (request.headers.get("Origin") or "").strip()
        if not origin:
            return _csrf_block(
                request,
                reason="missing Origin header",
            )
        if origin.rstrip("/").lower() not in self.allowed_origins:
            return _csrf_block(
                request,
                reason=f"untrusted origin: {origin}",
            )
        return await call_next(request)


def _csrf_block(request: Request, *, reason: str) -> JSONResponse:
    """Build the 403 JSON body.  Single source of truth so all rejection
    paths return byte-identical responses.
    """
    logger.warning(
        "CSRF: rejected %s %s — %s",
        request.method,
        request.url.path,
        reason,
    )
    return JSONResponse(
        {"error": "CSRF: invalid or missing Origin"},
        status_code=403,
    )


def mount_cors(
    app: FastAPI,
    *,
    allow_origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> None:
    """Add CORS middleware. Reads ``CORS_ALLOW_ORIGINS`` env when *allow_origins* is None.

    P21 P2 P2 (R2-NEW-07): the legacy ``["*"]`` default is gone.  The
    fallback is now :data:`DEFAULT_CORS_ALLOW_ORIGINS` (localhost dev
    origins); production deployers must set ``CORS_ALLOW_ORIGINS`` to a
    comma-separated list of trusted origins.
    """
    origins = _read_cors_origins(allow_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods or ["*"],
        allow_headers=allow_headers or ["*"],
    )


def mount_middleware(
    app: FastAPI,
    *,
    service_name: Optional[str] = None,
    enable_request_id: bool = True,
    cors_origins: Optional[List[str]] = None,
    enable_csrf: bool = True,
    csrf_allowed_origins: Optional[Union[List[str], Iterable[str]]] = None,
    csrf_enabled: Optional[bool] = None,
) -> None:
    """One-call helper: install request-id + CORS + CSRF in the right order.

    Middleware ordering (Starlette last-added = outermost):

      * ``CORS``        — added first, runs **innermost**
      * ``CSRFMiddleware`` — added second, runs in the middle
      * ``RequestIdMiddleware`` — added last, runs **outermost**

    Request flow for an unsafe method::

        Request → RequestIdMiddleware → CSRFMiddleware → CORSMiddleware → endpoint

    Why this order?
      * ``RequestIdMiddleware`` outermost so the request id is stamped
        on every response, even when CORS short-circuits a preflight or
        CSRF rejects a cross-origin POST.
      * ``CSRFMiddleware`` runs AFTER CORS so the CORS preflight
        short-circuit (an OPTIONS with ``Access-Control-Request-Method``)
        is handled by CORS first; CSRF then only sees real state-changing
        requests. CSRF also has a belt-and-braces check for the
        preflight header to be safe.
      * ``CORSMiddleware`` innermost so preflight is handled as close
        to the endpoint as possible (and so the existing
        ``Access-Control-Allow-*`` headers are set on the actual
        response from the route).

    Parameters
    ----------
    csrf_enabled:
        Explicit override for the ``CSRF_ENABLED`` env var.  Useful for
        tests that want to verify the helper actually wires CSRF in
        without relying on env state.  ``None`` (default) means "read
        ``CSRF_ENABLED`` env var".
    """
    # CORS — innermost
    mount_cors(app, allow_origins=cors_origins)
    # CSRF — middle
    if enable_csrf:
        csrf_kwargs = {
            "allowed_origins": (
                csrf_allowed_origins
                if csrf_allowed_origins is not None
                else cors_origins
            ),
        }
        if csrf_enabled is not None:
            csrf_kwargs["enabled"] = csrf_enabled
        app.add_middleware(CSRFMiddleware, **csrf_kwargs)
    # RequestId — outermost
    if enable_request_id:
        app.add_middleware(RequestIdMiddleware)


__all__ = [
    "CSRFMiddleware",
    "DEFAULT_CORS_ALLOW_ORIGINS",
    "RequestIdMiddleware",
    "mount_cors",
    "mount_middleware",
]
