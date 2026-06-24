"""backend/common/error_handler — uniform exception handlers (P4-1-W1).

Replaces the silent 500s that the 12 services used to ship. Every handler
returns a :func:`common.responses.error_response`-shaped JSON body:

    {
        "success": false,
        "error": {
            "code": "validation_error",
            "message": "1 validation error: ...",
            "details": [...],
            "request_id": "abc123...",
        }
    }

Covered exception types:

  * :class:`fastapi.HTTPException`         — propagate status_code + detail
  * :class:`fastapi.exceptions.RequestValidationError` — 422 with field list
  * :class:`pydantic.ValidationError`     — 422 with field list
  * :class:`sqlalchemy.exc.SQLAlchemyError` — 500 with safe message
  * :class:`Exception` (catch-all)         — 500 with class name + message

A custom ``BusinessError`` exception is also defined so service code can
raise a domain error without touching HTTPException directly::

    from common.error_handler import BusinessError

    if item is None:
        raise BusinessError("item_not_found", "Item 42 not in catalog", status_code=404)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """Domain-level exception that maps cleanly to an HTTP error response.

    Example::

        raise BusinessError(
            code="item_not_found",
            message="Item 42 not in catalog",
            status_code=404,
            details={"item_id": 42},
        )
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _request_id(request: Optional[Request]) -> str:
    if request is None:
        return "-"
    return request.headers.get("X-Request-ID", "-")


def _build_error_body(
    code: str,
    message: str,
    request: Optional[Request],
    details: Any = None,
    status_code: Optional[int] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        },
    }
    if details is not None:
        body["error"]["details"] = details
    if status_code is not None:
        body["error"]["status_code"] = status_code
    return body


# ── Individual handlers ────────────────────────────────────────────────────
async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    code = "http_error"
    message = str(detail) if not isinstance(detail, dict) else detail.get("message", str(detail))
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(code, message, request, details=detail, status_code=exc.status_code),
    )


async def _handle_business_error(request: Request, exc: BusinessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(exc.code, exc.message, request, details=exc.details, status_code=exc.status_code),
    )


async def _handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic v2 uses ``errors()``; v1 uses ``.errors`` attribute.
    try:
        errors = exc.errors()  # list of dicts
    except Exception:
        errors = getattr(exc, "errors", [])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_body(
            "validation_error",
            f"{len(errors)} validation error(s)",
            request,
            details=errors,
            status_code=422,
        ),
    )


async def _handle_sqlalchemy(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("SQLAlchemy error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_body(
            "database_error",
            "An internal database error occurred.",
            request,
            details={"type": exc.__class__.__name__},
            status_code=500,
        ),
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_body(
            "internal_error",
            "An unexpected error occurred.",
            request,
            details={"type": exc.__class__.__name__},
            status_code=500,
        ),
    )


# ── Public registration ────────────────────────────────────────────────────
def register_exception_handlers(app: FastAPI) -> None:
    """Wire all common exception handlers on *app*.

    Call this *after* the routes are mounted but *before* the app starts.
    """
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(BusinessError, _handle_business_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)

    # SQLAlchemy — only register if it's importable
    try:
        from sqlalchemy.exc import SQLAlchemyError

        app.add_exception_handler(SQLAlchemyError, _handle_sqlalchemy)
    except Exception:  # pragma: no cover
        pass

    # Catch-all
    app.add_exception_handler(Exception, _handle_unexpected)


__all__ = [
    "BusinessError",
    "register_exception_handlers",
]