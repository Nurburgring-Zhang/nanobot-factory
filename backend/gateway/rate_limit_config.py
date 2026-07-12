"""Per-endpoint rate-limit configuration loader + applier.

Why this module exists
======================
The original ``TokenBucketRateLimiter`` middleware used **hard-coded**
``capacity=100 / refill_per_second=50`` values.  That was fine for
anonymous traffic but routinely over- or under-throttled real endpoints:

* ``/api/v1/auth/login`` needs a **low** rate (anti-bruteforce)
* ``/api/v1/search`` needs a **high** rate (latency-sensitive UX)
* internal ``/_gw/*`` and ``/healthz`` should be **bypassed** entirely

This module loads a YAML/ENV config like::

    rate_limits:
      defaults:
        capacity: 100
        refill_per_second: 50.0
      endpoints:
        - pattern: "/api/v1/auth/login"
          capacity: 10
          refill_per_second: 1.0
          burst: 20
          trust_proxy: true
        - pattern: "/api/v1/search"
          capacity: 500
          refill_per_second: 200.0
        - pattern: "/_gw/*"
          bypass: true
        - pattern: "/healthz"
          bypass: true
        - pattern: "/readyz"
          bypass: true

A new :class:`PerEndpointRateLimiter` middleware wraps
:class:`~backend.gateway.middleware.rate_limit.TokenBucketRateLimiter`
so we can swap them in ``main.py`` without breaking the existing single
instance.

Compatibility
-------------
* ``RateLimitConfig.from_yaml(path)`` — load config from a YAML file
* ``RateLimitConfig.from_env()`` — load from env-var JSON (12-factor)
* ``RateLimitConfig.from_dict(d)`` — programmatic / test injection
* ``apply_to_middleware(middleware, config)`` — push the per-endpoint
  policies into an already-constructed middleware so the same in-memory
  bucket registry is reused (no extra asyncio.Lock churn).

Notes
-----
* ``pattern`` is a literal prefix by default; ``**`` / ``*`` wildcards
  supported (``fnmatch`` style).
* ``bypass: true`` means requests matching this pattern skip the
  limiter entirely (handled by the middleware ``dispatch`` method).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

log = logging.getLogger("gateway.rate_limit_config")

# RFC 1918 / RFC 4193 / loopback / link-local — sane defaults for
# "trusted proxies we deployed in front of us".  Override via
# ``RateLimitConfig(trusted_proxies=...)`` for non-cloud deployments.
_DEFAULT_TRUSTED_PROXIES: List[str] = [
    "127.0.0.1/32",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
    "fe80::/10",
]


def _ip_in_trusted(ip_str: str, trusted_networks: List["ipaddress._BaseNetwork"]) -> bool:
    """Return True if ``ip_str`` is inside any of the trusted networks.

    Invalid / non-IP strings return ``False`` so the caller falls back
    to the direct connection.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for net in trusted_networks:
        try:
            if addr in net:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _parse_trusted(raw: Iterable[str]) -> List["ipaddress._BaseNetwork"]:
    """Parse a list of CIDR / exact-IP strings into ``ip_network`` objects."""
    out: List["ipaddress._BaseNetwork"] = []
    for entry in raw or []:
        if not entry:
            continue
        s = str(entry).strip()
        if not s:
            continue
        # Bare IP → wrap as /32 or /128
        if "/" not in s:
            try:
                ipaddress.ip_address(s)
                s = s + ("/32" if ":" not in s else "/128")
            except ValueError:
                log.warning("trusted_proxies: invalid IP %r — skipping", s)
                continue
        try:
            out.append(ipaddress.ip_network(s, strict=False))
        except ValueError as exc:
            log.warning("trusted_proxies: invalid CIDR %r — %s", s, exc)
    return out


@dataclass
class EndpointPolicy:
    """Per-endpoint rate-limit policy."""

    pattern: str
    capacity: int = 100
    refill_per_second: float = 50.0
    burst: Optional[int] = None
    trust_proxy: bool = False
    bypass: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        # Normalise: ``pattern`` never ends in /, always begins with /
        p = (self.pattern or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        self.pattern = p.rstrip("/") or "/"
        # If refill_per_second is zero/negative, fall back to capacity/2
        if self.refill_per_second <= 0:
            self.refill_per_second = float(self.capacity) / 2.0
        # burst defaults to capacity if not provided
        if self.burst is None or self.burst <= 0:
            self.burst = self.capacity

    def matches(self, path: str) -> bool:
        """Return True if this policy applies to ``path``.

        Wildcards (``*``, ``**``) are honoured via :func:`fnmatch.fnmatch`.
        Literal patterns (no wildcards) match by **exact equality** or
        as a path segment boundary prefix — i.e. ``/api/v1/auth`` does
        NOT match ``/api/v1/authorization``.  We translate ``**`` to
        ``*`` for fnmatch consistency.  The lone ``/`` pattern only
        matches the root path.
        """
        pat = self.pattern.replace("**", "*")
        if "*" in pat or "?" in pat or "[" in pat:
            return fnmatch(path, pat)
        # Special case: the root pattern ``/`` only matches ``/``
        if pat in ("", "/"):
            return path == "/"
        # Literal pattern: exact or path-segment prefix
        if path == pat:
            return True
        if path.startswith(pat.rstrip("/") + "/"):
            return True
        return False


@dataclass
class RateLimitConfig:
    """The whole rate-limit configuration tree.

    Use one of the classmethods to construct::

        cfg = RateLimitConfig.from_yaml("backend/gateway/rate_limits.yaml")
        cfg.apply_to_middleware(middleware)
    """

    defaults: EndpointPolicy = field(
        default_factory=lambda: EndpointPolicy(
            pattern="*", capacity=100, refill_per_second=50.0, burst=200,
        )
    )
    endpoints: List[EndpointPolicy] = field(default_factory=list)
    # ----- Proxy-trust controls (P0 #1 hardening) -----
    # When ``trust_proxy=True`` on a policy, we need to know WHICH
    # proxies we trust to set X-Forwarded-For; otherwise any client can
    # spoof their IP by adding ``X-Forwarded-For: <random>`` and bypass
    # the per-client bucket.  Default to loopback + RFC1918.
    trusted_proxies: List[str] = field(
        default_factory=lambda: list(_DEFAULT_TRUSTED_PROXIES),
    )
    # Number of trusted hops to walk back from the XFF chain.  Each
    # proxy appends to the chain on the LEFT, so the rightmost entries
    # are closest to us.  ``proxy_chain_depth=1`` means we only trust
    # the *last* proxy that appended to XFF.
    proxy_chain_depth: int = 1

    # ---------------------------------------------------------------
    # Constructors
    # ---------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RateLimitConfig":
        """Load from a YAML file.  Missing file → fallback defaults."""
        p = Path(path)
        if not p.exists():
            log.warning("rate_limit yaml not found: %s — using defaults", p)
            return cls()
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return cls.from_dict(data)

    @classmethod
    def from_env(cls, env_var: str = "RATE_LIMIT_CONFIG") -> "RateLimitConfig":
        """Load from env var (JSON string).  Empty/missing → defaults."""
        raw = os.environ.get(env_var, "")
        if not raw.strip():
            return cls()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(f"{env_var} must be a JSON object")
            return cls.from_dict(data)
        except Exception as exc:
            log.warning("invalid %s json: %s — using defaults", env_var, exc)
            return cls()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RateLimitConfig":
        rl = data.get("rate_limits") or data  # tolerate {"rate_limits": ...}
        rl = rl if isinstance(rl, dict) else {}
        defaults = EndpointPolicy(pattern="*", **{
            k: v for k, v in (rl.get("defaults") or {}).items()
            if k in EndpointPolicy.__dataclass_fields__
        })
        eps: List[EndpointPolicy] = []
        for entry in rl.get("endpoints") or []:
            if not isinstance(entry, dict):
                continue
            valid = {k: v for k, v in entry.items()
                     if k in EndpointPolicy.__dataclass_fields__}
            if not valid.get("pattern"):
                continue
            eps.append(EndpointPolicy(**valid))
        # P0 #1 — proxy-trust controls (top-level under rate_limits)
        tp_raw = rl.get("trusted_proxies")
        tp: Optional[List[str]] = None
        if tp_raw is None:
            tp = list(_DEFAULT_TRUSTED_PROXIES)
        elif isinstance(tp_raw, list):
            tp = [str(x) for x in tp_raw]
        depth_raw = rl.get("proxy_chain_depth")
        depth: int = 1
        if depth_raw is not None:
            try:
                depth = max(0, int(depth_raw))
            except (TypeError, ValueError):
                log.warning("invalid proxy_chain_depth=%r — using 1", depth_raw)
                depth = 1
        cfg = cls(
            defaults=defaults,
            endpoints=eps,
            trusted_proxies=tp or list(_DEFAULT_TRUSTED_PROXIES),
            proxy_chain_depth=depth,
        )
        cfg._validate()
        return cfg

    # ---------------------------------------------------------------
    # Look-up
    # ---------------------------------------------------------------

    def match(self, path: str) -> EndpointPolicy:
        """Find the first endpoint that matches ``path``.

        Falls back to ``self.defaults``.  Order in ``endpoints`` matters
        because callers can override more specific patterns first.
        """
        for ep in self.endpoints:
            if ep.matches(path):
                return ep
        return self.defaults

    def is_bypass(self, path: str) -> bool:
        return bool(self.match(path).bypass)

    def policy_for(self, path: str) -> EndpointPolicy:
        return self.match(path)

    # ---------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------

    def _validate(self) -> None:
        seen: Dict[str, int] = {}
        for i, ep in enumerate(self.endpoints):
            n = seen.get(ep.pattern, 0)
            if n >= 1:
                log.warning("rate_limit duplicate pattern: %s", ep.pattern)
            seen[ep.pattern] = n + 1
            if ep.capacity < 1 or ep.refill_per_second <= 0:
                log.warning(
                    "rate_limit invalid policy for %s "
                    "(capacity=%s, refill=%s) — skipping",
                    ep.pattern, ep.capacity, ep.refill_per_second,
                )

    # ---------------------------------------------------------------
    # Stats for observability
    # ---------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "default_policy": _ep_stats(self.defaults),
            "endpoint_count": len(self.endpoints),
            "endpoints": [_ep_stats(ep) for ep in self.endpoints],
            "trusted_proxies": list(self.trusted_proxies),
            "proxy_chain_depth": int(self.proxy_chain_depth),
        }

    # ---------------------------------------------------------------
    # Apply to a TokenBucketRateLimiter instance
    # ---------------------------------------------------------------

    def apply_to_middleware(self, middleware) -> None:
        """Push per-endpoint policies into an existing middleware.

        Stores the config on ``middleware._config`` and rebuilds a
        per-policy ``_Bucket`` registry.  Existing buckets are dropped.
        """
        middleware._config = self  # type: ignore[attr-defined]
        middleware._policies = {
            ep.pattern: ep for ep in self.endpoints if not ep.bypass
        }
        # Default policy also lives in the policy dict under "_default"
        middleware._policies["_default"] = self.defaults  # type: ignore[attr-defined]
        middleware._buckets.clear()  # type: ignore[attr-defined]
        log.info(
            "rate_limit_config applied: %d endpoint overrides (default capacity=%s, refill=%s/s, "
            "trusted_proxies=%d, proxy_chain_depth=%d)",
            len(self.endpoints), self.defaults.capacity, self.defaults.refill_per_second,
            len(self.trusted_proxies), int(self.proxy_chain_depth),
        )


def _ep_stats(ep: EndpointPolicy) -> Dict[str, Any]:
    return {
        "pattern": ep.pattern,
        "capacity": ep.capacity,
        "refill_per_second": ep.refill_per_second,
        "burst": ep.burst,
        "bypass": ep.bypass,
        "trust_proxy": ep.trust_proxy,
    }


# ---------------------------------------------------------------------
# Per-endpoint middleware — keeps the original dispatch wiring but
# switches bucket per pattern.
# ---------------------------------------------------------------------

class PerEndpointRateLimiter:
    """Per-endpoint rate-limit middleware.

    Wraps the same in-memory token-bucket concept as
    :class:`TokenBucketRateLimiter` but resolves ``capacity`` and
    ``refill_per_second`` on a per-pattern basis via
    :class:`RateLimitConfig`.

    This is intentionally **NOT** a ``BaseHTTPMiddleware`` subclass —
    ``__init__`` accepts the FastAPI ``app`` but ``dispatch`` is called
    manually by the FastAPI middleware stack.
    """

    def __init__(
        self,
        app,
        *,
        config: Optional[RateLimitConfig] = None,
        **kwargs: Any,
    ) -> None:
        self.app = app
        # Defaults applied if config is missing or matches nothing
        self.defaults = {
            "capacity": int(kwargs.get("capacity", 100)),
            "refill_per_second": float(kwargs.get("refill_per_second", 50.0)),
        }
        self._config: RateLimitConfig = config or RateLimitConfig()
        # Lazy import to avoid circular import at module load
        from .middleware.rate_limit import _Bucket  # noqa: WPS433
        self._Bucket = _Bucket
        import asyncio as _asyncio
        self._asyncio = _asyncio
        self._buckets: Dict[Tuple[str, str], Any] = {}
        self._buckets_lock = _asyncio.Lock()
        # P0 #1: pre-compute trusted proxy networks for the ASGI hot path
        self._trusted_networks: List["ipaddress._BaseNetwork"] = _parse_trusted(
            self._config.trusted_proxies,
        )

    def configure(self, config: RateLimitConfig) -> None:
        """Hot-swap config (used by tests and during config reload)."""
        self._config = config
        # Refresh pre-computed trusted networks when config changes
        self._trusted_networks = _parse_trusted(config.trusted_proxies)

    @staticmethod
    def _client_key(
        request,
        trust_proxy: bool = False,
        trusted_proxies: Optional[List[str]] = None,
        proxy_chain_depth: int = 1,
    ) -> str:
        """Resolve a stable per-client identifier for bucketing.

        **P0 #1 hardening**: when ``trust_proxy=True``, the XFF header
        is *only* honoured if the immediate upstream (i.e. the
        ``request.client.host``) is in ``trusted_proxies``.  We then
        walk ``proxy_chain_depth`` hops back from the right side of
        the XFF chain, skipping each trusted hop, and return the
        first non-trusted IP we find.  This prevents clients from
        spoofing their bucket key by setting ``X-Forwarded-For`` to
        any random IP.

        If the XFF chain is shorter than expected, or every entry is
        trusted, we fall back to ``request.client.host``.
        """
        direct_ip = request.client.host if request.client else "unknown"
        if not trust_proxy:
            return direct_ip
        # Parse trusted networks once per call (cheap; cache-able later)
        trusted_networks = _parse_trusted(trusted_proxies or _DEFAULT_TRUSTED_PROXIES)
        # Sanity-check that the direct connection itself comes from a
        # trusted proxy.  Without this, any client could set the header.
        if not _ip_in_trusted(direct_ip, trusted_networks):
            log.debug(
                "rate_limit XFF ignored: direct client %s not in trusted_proxies",
                direct_ip,
            )
            return direct_ip
        fwd = request.headers.get("x-forwarded-for")
        if not fwd:
            return direct_ip
        # XFF chain: "client, proxy1, proxy2" — leftmost is original
        # client, rightmost is closest to us.  Walk from the right by
        # ``proxy_chain_depth``, skipping trusted hops, returning the
        # first non-trusted IP encountered.
        chain = [p.strip() for p in fwd.split(",") if p.strip()]
        if not chain:
            return direct_ip
        depth = max(0, int(proxy_chain_depth or 0))
        # Start index: how far back from the right to look.  If the
        # chain is shorter than depth, default to the leftmost (chain[0]).
        start = max(0, len(chain) - depth)
        for i in range(start, -1, -1):
            candidate = chain[i]
            if not _ip_in_trusted(candidate, trusted_networks):
                return candidate
        # Whole chain is trusted (very unusual) → fall back to leftmost
        return chain[0]

    async def _get_bucket(self, key: Tuple[str, str]) -> Any:
        bucket = self._buckets.get(key)
        if bucket is not None:
            return bucket
        async with self._buckets_lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                pattern, client_ip = key
                ep = self._config.policy_for(pattern)
                bucket = self._Bucket(
                    capacity=float(ep.capacity),
                    refill_rate=float(ep.refill_per_second),
                )
                self._buckets[key] = bucket
            return bucket

    async def dispatch(self, request, call_next):
        path = request.url.path
        policy = self._config.policy_for(path)
        if policy.bypass:
            return await call_next(request)

        client_ip = self._client_key(
            request,
            trust_proxy=policy.trust_proxy,
            trusted_proxies=self._config.trusted_proxies,
            proxy_chain_depth=self._config.proxy_chain_depth,
        )
        bucket = await self._get_bucket((policy.pattern, client_ip))
        allowed = await bucket.take(1.0)
        if not allowed:
            from fastapi.responses import JSONResponse  # noqa: WPS433
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "rate_limited",
                    "pattern": policy.pattern,
                    "limit_per_second": policy.refill_per_second,
                    "burst": policy.burst,
                    "client": client_ip,
                },
                headers={
                    "Retry-After": "1",
                    "X-RateLimit-Limit": str(int(policy.refill_per_second)),
                    "X-RateLimit-Burst": str(int(policy.capacity)),
                    "X-RateLimit-Pattern": policy.pattern,
                },
            )
        response = await call_next(request)
        # Inform well-behaved clients (only if response has a headers attr)
        if hasattr(response, "headers"):
            try:
                response.headers["X-RateLimit-Burst"] = str(int(policy.capacity))
                response.headers["X-RateLimit-Limit"] = str(int(policy.refill_per_second))
                response.headers["X-RateLimit-Pattern"] = policy.pattern
            except Exception:  # pragma: no cover — defensive
                pass
        return response

    # ---------------------------------------------------------------
    # ASGI 3 entry point so FastAPI can wrap this directly via
    # ``app.add_middleware(PerEndpointRateLimiter, config=...)``.
    # ---------------------------------------------------------------

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Cheap pre-checks from the scope (no full Request object needed)
        path = scope.get("path", "/")
        policy = self._config.policy_for(path)
        if policy.bypass:
            await self.app(scope, receive, send)
            return

        # Client key resolution (trust-proxy aware)
        client_ip = "unknown"
        client = scope.get("client")
        if client:
            try:
                client_ip = client[0]
            except Exception:  # pragma: no cover
                client_ip = "unknown"
        if policy.trust_proxy:
            # Reuse the same hardened logic from ``_client_key`` via a
            # scope adapter so both dispatch paths (Starlette Request
            # and raw ASGI scope) get the same anti-spoof treatment.
            scope_request = type(
                "_ScopeReq", (), {
                    "headers": {
                        n.decode("latin-1").lower(): v.decode("latin-1")
                        for n, v in (scope.get("headers") or [])
                    },
                    "client": type("_C", (), {"host": client_ip})(),
                },
            )()
            client_ip = self._client_key(
                scope_request,
                trust_proxy=True,
                trusted_proxies=self._config.trusted_proxies,
                proxy_chain_depth=self._config.proxy_chain_depth,
            )

        bucket = await self._get_bucket((policy.pattern, client_ip))
        allowed = await bucket.take(1.0)
        if not allowed:
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", b"1"),
                    (b"x-ratelimit-limit", str(int(policy.refill_per_second)).encode("latin-1")),
                    (b"x-ratelimit-burst", str(int(policy.capacity)).encode("latin-1")),
                    (b"x-ratelimit-pattern", policy.pattern.encode("latin-1")),
                ],
            })
            body = (
                '{"detail":"rate_limited","pattern":"' + policy.pattern +
                '","limit_per_second":' + str(policy.refill_per_second) +
                ',"burst":' + str(policy.burst) +
                ',"client":"' + client_ip + '"}'
            ).encode("utf-8")
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        # Allowed — forward the response with rate-limit header injection
        async def _send_wrapper(message):
            if message["type"] == "http.response.start":
                resp_headers = list(message.get("headers") or [])
                injected = {
                    b"x-ratelimit-burst": str(int(policy.capacity)).encode("latin-1"),
                    b"x-ratelimit-limit": str(int(policy.refill_per_second)).encode("latin-1"),
                    b"x-ratelimit-pattern": policy.pattern.encode("latin-1"),
                }
                seen = set()
                new_headers = []
                for name, value in resp_headers:
                    if name in injected and name not in seen:
                        new_headers.append((name, injected[name]))
                        seen.add(name)
                    elif name in injected and name in seen:
                        continue
                    else:
                        new_headers.append((name, value))
                        seen.add(name)
                for k, v in injected.items():
                    if k not in seen:
                        new_headers.append((k, v))
                        seen.add(k)
                message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, _send_wrapper)


__all__ = [
    "EndpointPolicy",
    "RateLimitConfig",
    "PerEndpointRateLimiter",
]
