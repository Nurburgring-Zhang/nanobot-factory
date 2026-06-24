"""httpx-based async proxy with circuit-breaker integration.

The gateway itself does not call the downstream service directly — it
goes through ``ProxyClient.forward()`` so the circuit-breaker policy
and the access log live in one place.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import Request, Response
from starlette.responses import StreamingResponse

from .middleware.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError

log = logging.getLogger("gateway.proxy")


class ProxyClient:
    """Async proxy that forwards ``Request`` to a downstream service."""

    def __init__(
        self,
        *,
        breakers: CircuitBreakerRegistry,
        upstream_timeout: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.breakers = breakers
        self.upstream_timeout = upstream_timeout
        self._client = client or httpx.AsyncClient(timeout=upstream_timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def forward(
        self,
        request: Request,
        *,
        service_name: str,
        upstream_base: str,
        request_id: str,
    ) -> Response:
        """Forward ``request`` to ``upstream_base`` and return its response.

        ``service_name`` is used to look up the per-service circuit breaker.

        The ``request_id`` argument is the source of truth — if it is empty,
        we fall back to whatever AccessLogMiddleware already minted on
        ``request.state.rid`` (so the response header and the upstream
        header stay in sync).
        """
        if not request_id:
            request_id = (
                getattr(request.state, "rid", None)
                or self.make_request_id()
            )

        breaker = await self.breakers.get(service_name)
        if not await breaker.allow():
            raise CircuitOpenError(f"circuit_open:{service_name}")

        # Build upstream URL: prefix from gateway + remaining path + query
        # We rely on routes.yaml having prepended ``/internal`` to upstream
        # so that this method just appends the original path verbatim.
        target_path = request.url.path
        target_url = f"{upstream_base.rstrip('/')}{target_path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        # Headers — drop hop-by-hop, keep everything else.  We use the
        # header name as-supplied from the incoming request (request.headers
        # is case-insensitive in Starlette), but explicitly overwrite the
        # X-Request-ID slot with our canonical name to avoid sending two
        # variants of the same header.
        fwd_headers: Dict[str, str] = {}
        for k, v in request.headers.items():
            if k.lower() in ("host", "content-length", "connection"):
                continue
            fwd_headers[k] = v
        # Drop any incoming X-Request-ID under any case, then add ours.
        for k in list(fwd_headers.keys()):
            if k.lower() == "x-request-id":
                del fwd_headers[k]
        fwd_headers["X-Forwarded-Host"] = request.url.netloc
        fwd_headers["X-Request-ID"] = request_id
        fwd_headers["X-Forwarded-Proto"] = request.url.scheme

        body: Optional[bytes] = None
        if request.method not in ("GET", "HEAD", "DELETE"):
            body = await request.body()

        start = time.monotonic()
        try:
            upstream = await self._client.request(
                method=request.method,
                url=target_url,
                headers=fwd_headers,
                content=body,
            )
        except httpx.TimeoutException as exc:
            await breaker.record_failure()
            log.warning(
                "upstream timeout service=%s url=%s err=%s",
                service_name, target_url, exc,
            )
            return Response(
                content=f'{{"detail":"upstream_timeout","service":"{service_name}"}}',
                status_code=504,
                media_type="application/json",
                headers={"X-Request-ID": request_id},
            )
        except httpx.HTTPError as exc:
            await breaker.record_failure()
            log.warning(
                "upstream error service=%s url=%s err=%s",
                service_name, target_url, exc,
            )
            return Response(
                content=f'{{"detail":"upstream_unreachable","service":"{service_name}"}}',
                status_code=502,
                media_type="application/json",
                headers={"X-Request-ID": request_id},
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        # 5xx responses must count as upstream failures so the breaker can
        # trip — a 500 from the monolith is just as "down" as a connection
        # refusal.  4xx is the caller's fault and stays success.
        if upstream.status_code >= 500:
            await breaker.record_failure()
            log.info(
                "upstream 5xx service=%s status=%s — breaker failure recorded",
                service_name, upstream.status_code,
            )
        else:
            await breaker.record_success()
        log.info(
            "proxy %s %s service=%s status=%s elapsed_ms=%d request_id=%s",
            request.method, target_path, service_name,
            upstream.status_code, elapsed_ms, request_id,
        )

        # Build the response back to the client.  Stream large bodies.
        content_type = upstream.headers.get("content-type", "application/json")
        # Case-insensitive set of header names we already control, so
        # upstream copies cannot duplicate X-Request-ID / X-Upstream-*.
        _HOP_BY_HOP = frozenset(h.lower() for h in (
            "content-encoding", "transfer-encoding", "connection",
            "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailers", "upgrade", "content-length",
        ))
        _OUR_HEADERS = frozenset(h.lower() for h in (
            "x-request-id", "x-upstream-service", "x-upstream-elapsed-ms",
        ))
        headers = {
            "X-Request-ID": request_id,
            "X-Upstream-Service": service_name,
            "X-Upstream-Elapsed-Ms": str(elapsed_ms),
        }
        # Copy safe response headers (skip hop-by-hop and our own keys,
        # both case-insensitively — otherwise upstream's x-request-id would
        # duplicate our X-Request-ID with a `, ` separator in the response).
        for k, v in upstream.headers.items():
            kl = k.lower()
            if kl in _HOP_BY_HOP:
                continue
            if kl in _OUR_HEADERS:
                continue
            headers[k] = v

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=headers,
            media_type=content_type.split(";")[0].strip() or "application/json",
        )

    def make_request_id(self) -> str:
        return f"req_{uuid.uuid4().hex[:16]}"


__all__ = ["ProxyClient"]
