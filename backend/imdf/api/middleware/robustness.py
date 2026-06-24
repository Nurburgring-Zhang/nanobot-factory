"""
IMDF Robustness Middleware — 请求保护层
=========================================
- 请求队列保护: 最大并发数控制, 超出返回 503
- 请求超时: 每个请求30s超时自动取消
- 请求ID: 每个请求生成 X-Request-ID
- Panic Recovery: 全局异常捕获, 优雅返回500
"""

import asyncio
import uuid
import time
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from config.settings import (
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT_SECONDS,
    ENABLE_ROBUSTNESS_MIDDLEWARE,
)

logger = logging.getLogger("imdf.robustness")


class ConcurrencyLimiter:
    """Token-bucket style concurrency limiter using asyncio.Semaphore."""

    def __init__(self, max_concurrent: int = 100):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent

    @property
    def active(self) -> int:
        return self._max - self._semaphore._value

    @property
    def max_concurrent(self) -> int:
        return self._max

    async def acquire(self) -> bool:
        """Try to acquire a slot; returns False immediately if full."""
        # We use a non-blocking approach: try to acquire, else reject
        if self._semaphore.locked():
            return False
        # acquire() may still block briefly; wrap in a quick check
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.01)
            return True
        except asyncio.TimeoutError:
            return False

    def release(self):
        """Release a slot back to the pool."""
        try:
            self._semaphore.release()
        except ValueError:
            pass  # released more than acquired (shouldn't happen)


# Global concurrency limiter instance
_concurrency_limiter = ConcurrencyLimiter(max_concurrent=MAX_CONCURRENT_REQUESTS)


class RobustnessMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive robustness middleware for FastAPI/Starlette.

    Provides:
    - X-Request-ID injection
    - Concurrency limiting (503 when overloaded)
    - Request timeout enforcement
    - Panic recovery with graceful 500
    """

    def __init__(
        self,
        app: ASGIApp,
        max_concurrent: int = 100,
        timeout_seconds: int = 30,
        enabled: bool = True,
    ):
        super().__init__(app)
        self.limiter = _concurrency_limiter
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # ── Generate/forward Request ID ──────────────────────────────
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        start_time = time.monotonic()

        if not self.enabled:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # ── Concurrency check ────────────────────────────────────────
        acquired = await self.limiter.acquire()
        if not acquired:
            logger.warning(
                "request_rejected",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "active_requests": self.limiter.active,
                    "max_concurrent": self.limiter.max_concurrent,
                    "reason": "too_many_concurrent_requests",
                },
            )
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Service is overloaded. Please retry later.",
                    "request_id": request_id,
                },
                headers={
                    "X-Request-ID": request_id,
                    "Retry-After": "5",
                },
            )

        try:
            # ── Timeout enforcement ──────────────────────────────────
            try:
                response = await asyncio.wait_for(
                    call_next(request), timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "request_timeout",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "timeout_seconds": self.timeout_seconds,
                        "elapsed": round(elapsed, 3),
                    },
                )
                return JSONResponse(
                    status_code=504,
                    content={
                        "success": False,
                        "error": f"Request timed out after {self.timeout_seconds}s.",
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )

            # ── Inject Request ID ────────────────────────────────────
            response.headers["X-Request-ID"] = request_id

            # ── Log slow requests ────────────────────────────────────
            elapsed = time.monotonic() - start_time
            if elapsed > 5.0:
                logger.warning(
                    "slow_request",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "elapsed": round(elapsed, 3),
                    },
                )

            return response

        except Exception as exc:
            # ── Panic Recovery ──────────────────────────────────────
            elapsed = time.monotonic() - start_time
            logger.exception(
                "unhandled_exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)[:500],
                    "elapsed": round(elapsed, 3),
                },
            )
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "Internal server error.",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )

        finally:
            self.limiter.release()


def get_robustness_stats() -> dict:
    """Return current concurrency stats for monitoring."""
    return {
        "active_requests": _concurrency_limiter.active,
        "max_concurrent": _concurrency_limiter.max_concurrent,
        "utilization_pct": round(
            _concurrency_limiter.active / max(1, _concurrency_limiter.max_concurrent) * 100, 1
        ),
    }
