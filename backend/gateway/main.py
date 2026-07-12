"""Nanobot Factory API Gateway.

Run with::

    uvicorn backend.gateway.main:app --port 8000

Configuration is loaded from ``backend/gateway/routes.yaml`` (relative
to the project root).  The gateway can be reached on port 8000 and
forwards to the monolith (default ``http://127.0.0.1:8765``).

The gateway exposes a few control endpoints of its own (under ``/_gw/``)
plus a transparent reverse-proxy for the upstream service tree.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure ``backend`` is on sys.path so we can run as ``backend.gateway.main``
_BACKEND = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml  # PyYAML
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .proxy import ProxyClient
from .middleware.rate_limit import TokenBucketRateLimiter
from .middleware.circuit_breaker import (
    BreakerState,
    CircuitBreakerRegistry,
    CircuitOpenError,
)

# New P17-A2 modules: replace hard-coded CORS,RateLimit,add API version + cache
from .cors import CorsConfig, CorsMiddleware
from .api_version import ApiVersionConfig, ApiVersionMiddleware
from .cache import CacheConfig, CacheClient, CacheMiddleware
from .rate_limit_config import RateLimitConfig, PerEndpointRateLimiter

log = logging.getLogger("gateway")
logging.basicConfig(
    level=os.environ.get("GATEWAY_LOG_LEVEL", "INFO"),
    format='%(asctime)s [%(name)s] %(levelname)s %(message)s',
)


# ---------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------

DEFAULT_ROUTES_PATH = Path(__file__).resolve().parent / "routes.yaml"


def _load_routes(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"routes config not found: {path}")
    with path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def _compile_routes(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn yaml services into compiled, sorted (longest prefix first) routes."""
    out: List[Dict[str, Any]] = []
    for svc in cfg.get("services", []) or []:
        prefix = svc.get("prefix", "").rstrip("/")
        upstream = svc.get("upstream", "").rstrip("/")
        if not prefix or not upstream:
            log.warning("skipping incomplete route entry: %s", svc)
            continue
        out.append(
            {
                "name": svc["name"],
                "prefix": prefix,
                "upstream": upstream,
                "require_auth": bool(svc.get("require_auth", True)),
                "description": svc.get("description", ""),
            }
        )
    out.sort(key=lambda r: len(r["prefix"]), reverse=True)
    return out


# ---------------------------------------------------------------------
# JWT validation (lightweight — verify signature only; upstream does
# the rest).  The secret is shared with the monolith via env.
# ---------------------------------------------------------------------

try:
    from jose import jwt as _jose_jwt  # type: ignore
    from jose.exceptions import JWTError as _JoseJWTError  # type: ignore
except Exception:  # pragma: no cover - optional dep
    _jose_jwt = None
    _JoseJWTError = Exception  # type: ignore


def _jwt_secret() -> str:
    return os.environ.get(
        "JWT_SECRET_KEY",
        os.environ.get("JWT_SECRET", "imdf_secret_change_me"),
    )


def _validate_jwt(token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    if _jose_jwt is None:
        # We still need to gracefully handle absence of PyJWT in tests.
        return True, {"raw": token[:32]}
    try:
        payload = _jose_jwt.decode(
            token,
            _jwt_secret(),
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return True, payload
    except _JoseJWTError:  # type: ignore[misc]
        return False, None


# ---------------------------------------------------------------------
# Access log middleware — emits one JSON line per request and assigns
# X-Request-ID for tracing.
# ---------------------------------------------------------------------

class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or f"req_{os.urandom(8).hex()}"
        # Expose the rid so the inner proxy.forward() can re-use it —
        # otherwise the upstream header and the response header would
        # carry two independently-minted ids.
        try:
            request.state.rid = rid
        except Exception:  # pragma: no cover - defensive
            pass
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - propagate
            log.exception(
                "unhandled request_id=%s method=%s path=%s",
                rid, request.method, request.url.path,
            )
            raise
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "%s - \"%s %s\" %d %dms rid=%s",
            request.client.host if request.client else "-",
            request.method, request.url.path,
            response.status_code, elapsed_ms, rid,
        )
        response.headers["X-Request-ID"] = rid
        return response


# ---------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("gateway starting; routes=%s", len(app.state.routes))
    yield
    # Shutdown
    log.info("gateway shutting down")
    proxy: ProxyClient = app.state.proxy
    await proxy.aclose()


def create_app(routes_path: Optional[Path] = None) -> FastAPI:
    cfg = _load_routes(routes_path or DEFAULT_ROUTES_PATH)
    gw_cfg = cfg.get("gateway", {}) or {}
    rl_cfg = gw_cfg.get("rate_limit", {}) or {}
    cb_cfg = gw_cfg.get("circuit_breaker", {}) or {}

    app = FastAPI(
        title="Nanobot Factory API Gateway",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ----- state -----
    app.state.routes = _compile_routes(cfg)
    app.state.default_route = cfg.get("default", {}) or {}
    app.state.breakers = CircuitBreakerRegistry(
        failure_threshold=int(cb_cfg.get("failure_threshold", 5)),
        reset_timeout=float(cb_cfg.get("reset_timeout_seconds", 30.0)),
    )
    app.state.proxy = ProxyClient(
        breakers=app.state.breakers,
        upstream_timeout=float(gw_cfg.get("upstream_timeout_seconds", 30.0)),
    )

    # ----- P17-A2: load configs (YAML preferred, ENV fallback) -----
    backend_root = Path(__file__).resolve().parent
    cors_config = CorsConfig.from_yaml(backend_root / "cors_config.yaml")
    if not cors_config.enabled or not cors_config.origins:
        cors_config = CorsConfig.from_env_legacy()
    api_version_config = ApiVersionConfig.from_yaml(
        backend_root / "api_version_config.yaml",
    )
    cache_config = CacheConfig.from_yaml(backend_root / "cache_config.yaml")

    rate_limit_yaml = backend_root / "rate_limits.yaml"
    if rate_limit_yaml.exists():
        rate_limit_config = RateLimitConfig.from_yaml(rate_limit_yaml)
    else:
        rate_limit_config = RateLimitConfig.from_env()
        if not rate_limit_config.endpoints:
            rate_limit_config = RateLimitConfig.from_dict({
                "rate_limits": {
                    "defaults": {
                        "capacity": int(rl_cfg.get("capacity", 100)),
                        "refill_per_second": float(rl_cfg.get("refill_per_second", 50.0)),
                    },
                },
            })

    app.state.cors_config = cors_config
    app.state.api_version_config = api_version_config
    app.state.cache_config = cache_config
    app.state.rate_limit_config = rate_limit_config

    # ----- middleware order matters (outermost first) -----
    # Per-origin CORS with preflight caching
    app.add_middleware(CorsMiddleware, config=cors_config)

    # API version header injection + deprecation warnings
    app.add_middleware(ApiVersionMiddleware, config=api_version_config)

    # Cache middleware (GET responses only)
    app.add_middleware(CacheMiddleware, config=cache_config)

    # Access log middleware (X-Request-ID + JSON line)
    app.add_middleware(AccessLogMiddleware)

    # Per-endpoint rate limiter
    app.add_middleware(PerEndpointRateLimiter, config=rate_limit_config)

    # ----- control endpoints -----

    @app.get("/")
    async def root():
        return {
            "service": "nanobot-factory-gateway",
            "version": "0.1.0",
            "routes": [r["prefix"] for r in app.state.routes],
        }

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "service": "gateway"}

    @app.get("/readyz")
    async def readyz():
        return {
            "status": "ready",
            "routes_loaded": len(app.state.routes),
            "breakers": app.state.breakers.snapshot(),
        }

    @app.get("/_gw/routes")
    async def list_routes():
        return {
            "routes": [
                {
                    "name": r["name"],
                    "prefix": r["prefix"],
                    "upstream": r["upstream"],
                    "require_auth": r["require_auth"],
                }
                for r in app.state.routes
            ],
            "default": app.state.default_route,
        }

    @app.get("/_gw/breakers")
    async def list_breakers():
        return {"breakers": app.state.breakers.snapshot()}

    # ----- P17-A2: diagnostic endpoints for new modules -----

    @app.get("/_gw/cors")
    async def cors_diag():
        cfg: CorsConfig = app.state.cors_config
        return {
            "enabled": cfg.enabled,
            "default": {
                "origin": cfg.default.origin,
                "methods": cfg.default.methods,
                "headers": cfg.default.headers,
                "credentials": cfg.default.credentials,
                "max_age": cfg.default.max_age,
            },
            "origins": [
                {
                    "origin": pol.origin,
                    "methods": pol.methods,
                    "headers": pol.headers,
                    "credentials": pol.credentials,
                    "max_age": pol.max_age,
                }
                for pol in cfg.origins
            ],
        }

    @app.get("/_gw/api-version")
    async def api_version_diag():
        cfg: ApiVersionConfig = app.state.api_version_config
        return {
            "supported_versions": cfg.supported_versions,
            "default_version": cfg.default_version,
            "deprecation": {
                "deprecated_versions": cfg.deprecation.deprecated_versions,
                "sunset_date": cfg.deprecation.sunset_date,
                "successor_version": cfg.deprecation.successor_version,
            },
        }

    @app.get("/_gw/cache")
    async def cache_diag():
        from . import cache as _cache_mod  # noqa: WPS433
        cfg: CacheConfig = app.state.cache_config
        return {
            "config": {
                "backend": cfg.backend,
                "redis_url": cfg.redis_url,
                "prefix": cfg.prefix,
                "default_ttl_seconds": cfg.default_ttl_seconds,
            },
            "stats": _cache_mod.cache_stats(),
        }

    @app.get("/_gw/rate-limit")
    async def rate_limit_diag():
        cfg: RateLimitConfig = app.state.rate_limit_config
        return {"stats": cfg.stats()}

    # ----- main proxy endpoint -----

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def gateway_route(full_path: str, request: Request):
        # /healthz / /readyz / /_gw/* are handled above (FastAPI matches
        # them first by exact path).  Anything else falls through here.
        return await _proxy(request, full_path, app)

    return app


def _match_route(app: FastAPI, path: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Find the longest-prefix match.  Returns (service, default)."""
    for r in app.state.routes:
        if path == r["prefix"] or path.startswith(r["prefix"] + "/") or path == r["prefix"].rstrip("/"):
            return r, None
    default = app.state.default_route
    return None, default if default else None


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


async def _proxy(request: Request, full_path: str, app: FastAPI) -> Response:
    svc, default = _match_route(app, "/" + full_path)
    if svc is None and default is None:
        raise HTTPException(status_code=404, detail="route_not_found")

    # Auth gate
    require_auth = bool((svc or default).get("require_auth", True))
    if require_auth:
        token = _extract_bearer(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing_bearer_token"},
            )
        ok, payload = _validate_jwt(token)
        if not ok:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid_or_expired_token"},
            )
        request.state.jwt_payload = payload
    else:
        request.state.jwt_payload = None

    target = svc if svc is not None else default
    service_name = (svc or {}).get("name", "default")

    # Build upstream base.  routes.yaml has the upstream already
    # prefixed with /internal; we keep things simple by trusting that.
    upstream_base = target["upstream"]

    proxy: ProxyClient = app.state.proxy
    # Prefer the rid already minted by AccessLogMiddleware (request.state.rid)
    # so the response header and the upstream-forwarded header agree.
    request_id = (
        getattr(request.state, "rid", None)
        or request.headers.get("X-Request-ID")
        or proxy.make_request_id()
    )
    try:
        return await proxy.forward(
            request,
            service_name=service_name,
            upstream_base=upstream_base,
            request_id=request_id,
        )
    except CircuitOpenError:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "circuit_open",
                "service": service_name,
            },
            headers={"X-Request-ID": request_id},
        )


# Module-level ASGI app for ``uvicorn backend.gateway.main:app``
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    cfg = _load_routes(DEFAULT_ROUTES_PATH).get("gateway", {})
    uvicorn.run(
        "backend.gateway.main:app",
        host=cfg.get("host", "0.0.0.0"),
        port=int(os.environ.get("PORT", cfg.get("port", 8000))),
        log_level=os.environ.get("UVICORN_LOG_LEVEL", "info"),
    )
