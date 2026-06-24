"""backend/common/responses — uniform JSON envelopes (P4-1-W1).

The 12 services used to return naked dicts (``{"foo": 1}``) or worse,
``{"code": 0, "data": {...}}`` shapes that don't agree across endpoints.
This module defines three helpers that produce a consistent envelope:

    success_response(data, ...)        →  {"success": true,  "data": {...}, "request_id": "..."}
    error_response(code, message, ...) →  {"success": false, "error": {"code": "...", ...}}
    paginated_response(items, total)   →  {"success": true, "data": {"items": [...], "total": N, ...}}

Each function also accepts an explicit ``status_code`` for the error case;
success defaults to 200, paginated to 200.

Routes can simply::

    @router.get("/api/v1/users")
    def list_users():
        return success_response({"users": [...]})
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


def _request_id_of(request: Optional[Request]) -> str:
    if request is None:
        return "-"
    return request.headers.get("X-Request-ID", "-")


def success_response(
    data: Any = None,
    *,
    message: Optional[str] = None,
    request: Optional[Request] = None,
    status_code: int = 200,
) -> JSONResponse:
    """Wrap *data* in a ``{success, data, message?, request_id}`` envelope."""
    body: Dict[str, Any] = {"success": True, "data": data, "request_id": _request_id_of(request)}
    if message:
        body["message"] = message
    return JSONResponse(status_code=status_code, content=body)


def error_response(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    details: Any = None,
    request: Optional[Request] = None,
) -> JSONResponse:
    """Build an error envelope with ``{success, error: {code, message, ...}}``."""
    err: Dict[str, Any] = {
        "code": code,
        "message": message,
        "status_code": status_code,
        "request_id": _request_id_of(request),
    }
    if details is not None:
        err["details"] = details
    return JSONResponse(status_code=status_code, content={"success": False, "error": err})


def paginated_response(
    items: List[Any],
    total: int,
    *,
    page: int = 1,
    page_size: int = 20,
    extra: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> JSONResponse:
    """Build a paginated envelope.

    Output::

        {
          "success": true,
          "data": {
            "items": [...],
            "total": 42,
            "page": 1,
            "page_size": 20,
            "total_pages": 3,
            ...extra
          },
          "request_id": "..."
        }
    """
    page = max(page, 1)
    page_size = max(page_size, 1)
    total_pages = max(1, math.ceil(total / page_size))
    data: Dict[str, Any] = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    if extra:
        data.update(extra)
    return JSONResponse(
        status_code=200,
        content={"success": True, "data": data, "request_id": _request_id_of(request)},
    )


__all__ = [
    "success_response",
    "error_response",
    "paginated_response",
]