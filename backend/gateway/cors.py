"""Per-origin CORS configuration + custom middleware.

Motivation
==========
The current gateway uses :class:`fastapi.middleware.cors.CORSMiddleware`
with a hard-coded list of origins:

.. code-block:: python

    allow_origins = os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080",
    ).split(",")

That's fragile in production because:

1. **Wildcard ``*`` with credentials is forbidden** by the spec — many
   environments end up hitting this.
2. Different **deployment stages** (dev / staging / prod) need wildly
   different origin lists — environment variables are enough but YAML
   is clearer.
3. ``preflight`` responses are not cached — every OPTIONS request
   re-runs the whole middleware pipeline.

What this module provides
=========================

* :class:`CorsConfig` — dataclass loaded from YAML/ENV
* :class:`CorsPolicy` — per-origin ``(methods, headers, credentials,
  expose_headers, max_age)``
* :class:`CorsMiddleware` — drop-in replacement for Starlette's
  CORSMiddleware with per-origin lookup + automatic preflight caching
  (``Access-Control-Max-Age``)
* :func:`resolve_cors` — one-shot helper returning the headers for a
  given ``origin``

YAML schema
-----------

.. code-block:: yaml

    cors:
      enabled: true
      default:
        origins: ["*"]
        methods: [GET, POST, OPTIONS]
        headers: ["*"]
        credentials: false
        max_age: 600
      origins:
        - origin: "https://app.imdf.example.com"
          methods: [GET, POST, PUT, PATCH, DELETE, OPTIONS]
          headers: [Content-Type, Authorization, X-Request-ID]
          credentials: true
          max_age: 86400
          expose_headers:
            - X-Request-ID
            - X-RateLimit-Limit
            - X-RateLimit-Burst
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

log = logging.getLogger("gateway.cors")


class CorsConfigError(ValueError):
    """Raised when the CORS configuration violates a security invariant.

    Currently this fires when ``origin='*'`` is combined with
    ``credentials=True`` — browsers will silently drop the
    ``Access-Control-Allow-Credentials`` header in that combination,
    so serving it is a security anti-pattern (and almost certainly a
    misconfiguration).  We refuse to load such configs rather than
    start the gateway in a broken state.
    """


def _strip_scheme(origin: str) -> str:
    """Remove ``http://`` / ``https://`` from an origin URL."""
    if not origin:
        return ""
    for prefix in ("https://", "http://"):
        if origin.startswith(prefix):
            return origin[len(prefix):]
    return origin


# ---------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------

@dataclass
class CorsPolicy:
    """Per-origin CORS policy."""

    origin: str = "*"
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "OPTIONS"])
    headers: List[str] = field(default_factory=lambda: ["*"])
    expose_headers: List[str] = field(default_factory=list)
    credentials: bool = False
    max_age: int = 600  # seconds — preflight cache

    # ---- helpers ----

    def allows(self, request_origin: str) -> bool:
        if self.origin == "*":
            return True
        if self.origin == request_origin:
            return True
        # Wildcard subdomain: ``*.example.com`` matches any subdomain +
        # the apex.  We compare hostnames after stripping the URL scheme.
        if self.origin.startswith("*."):
            base = self.origin[2:]
            host = _strip_scheme(request_origin)
            return host == base or host.endswith("." + base)
        return False

    def to_headers(
        self,
        request_origin: Optional[str] = None,
        *,
        preflight: bool = False,
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}

        # Access-Control-Allow-Origin (echo, not wildcard, when creds=True)
        if self.origin == "*" and not self.credentials:
            out["Access-Control-Allow-Origin"] = "*"
        else:
            out["Access-Control-Allow-Origin"] = request_origin or self.origin

        if preflight:
            out["Access-Control-Allow-Methods"] = ", ".join(self.methods)
            out["Access-Control-Allow-Headers"] = ", ".join(self.headers)
            out["Access-Control-Max-Age"] = str(self.max_age)
        if self.credentials:
            out["Access-Control-Allow-Credentials"] = "true"
        if self.expose_headers:
            out["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        # Vary on Origin (cache keys differ per Origin)
        out["Vary"] = "Origin"
        return out


@dataclass
class CorsConfig:
    """The full CORS configuration tree."""

    enabled: bool = True
    default: CorsPolicy = field(default_factory=CorsPolicy)
    origins: List[CorsPolicy] = field(default_factory=list)

    # ---- constructors ----

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CorsConfig":
        p = Path(path)
        if not p.exists():
            log.warning("cors yaml not found: %s — using defaults", p)
            return cls()
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return cls.from_dict(data)

    @classmethod
    def from_env(cls, env_var: str = "CORS_CONFIG") -> "CorsConfig":
        raw = os.environ.get(env_var, "")
        if not raw.strip():
            return cls()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(f"{env_var} must be a JSON object")
            return cls.from_dict({"cors": data})
        except Exception as exc:
            log.warning("invalid %s: %s — using defaults", env_var, exc)
            return cls()

    @classmethod
    def from_env_legacy(cls) -> "CorsConfig":
        """Backward-compat: read ``CORS_ALLOWED_ORIGINS`` etc."""
        origins_raw = os.environ.get(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080",
        )
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
        try:
            max_age = int(os.environ.get("CORS_MAX_AGE", "600"))
        except ValueError:
            max_age = 600
        return cls(
            enabled=os.environ.get("CORS_DISABLED", "") != "1",
            default=CorsPolicy(
                origin="*",
                methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                headers=["*"],
                credentials=False,
                max_age=max_age,
            ),
            origins=[
                CorsPolicy(
                    origin=o,
                    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                    headers=["*"],
                    credentials=False,
                    max_age=max_age,
                )
                for o in origins
            ],
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorsConfig":
        section = data.get("cors") if isinstance(data.get("cors"), dict) else data
        if not isinstance(section, dict):
            section = {}

        enabled = bool(section.get("enabled", True))
        default_data = section.get("default") or {}
        default = cls._policy_from_dict(default_data)

        origins: List[CorsPolicy] = []
        for entry in section.get("origins") or []:
            if not isinstance(entry, dict):
                continue
            origins.append(cls._policy_from_dict(entry))

        cfg = cls(enabled=enabled, default=default, origins=origins)
        cfg._validate()
        return cfg

    @staticmethod
    def _policy_from_dict(d: Dict[str, Any]) -> CorsPolicy:
        if not isinstance(d, dict):
            d = {}
        return CorsPolicy(
            origin=str(d.get("origin") or "*"),
            methods=list(d.get("methods") or ["GET", "POST", "OPTIONS"]),
            headers=list(d.get("headers") or ["*"]),
            expose_headers=list(d.get("expose_headers") or []),
            credentials=bool(d.get("credentials", False)),
            max_age=int(d.get("max_age") or 600),
        )

    # ---- lookup ----

    def resolve(self, request_origin: Optional[str]) -> CorsPolicy:
        """Return the policy that should apply to ``request_origin``.

        Falls back to ``self.default``.  Wildcard ``*`` policies match
        any origin; wildcard subdomain patterns (``*.example.com``)
        match any subdomain as well as the apex domain.
        """
        if not request_origin:
            return self.default

        # 1. exact match
        for pol in self.origins:
            if pol.origin == request_origin:
                return pol
        # 2. wildcard subdomain match (host comparison, scheme stripped)
        host = _strip_scheme(request_origin)
        for pol in self.origins:
            if pol.origin.startswith("*."):
                base = pol.origin[2:]
                if host == base or host.endswith("." + base):
                    return pol
        # 3. default fallback
        if self.default.allows(request_origin):
            return self.default
        return self.default

    def allows(self, request_origin: Optional[str]) -> bool:
        if not self.enabled:
            return False
        return self.resolve(request_origin).allows(request_origin)

    def headers(
        self,
        request_origin: Optional[str] = None,
        *,
        preflight: bool = False,
        request_method: Optional[str] = None,
        request_headers: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        pol = self.resolve(request_origin)
        if not self.enabled:
            return {}
        return pol.to_headers(request_origin, preflight=preflight)

    def _validate(self) -> None:
        # P0 #4 — refuse to load ``*`` + credentials=True.
        # Browsers will silently drop ``Access-Control-Allow-Credentials``
        # in this combination, so serving it is a security
        # anti-pattern (and almost certainly a misconfiguration).
        offenders: List[str] = []
        for pol in [self.default, *self.origins]:
            if pol.origin == "*" and pol.credentials:
                offenders.append(pol.origin)
        if offenders:
            raise CorsConfigError(
                "CORS misconfiguration: origin='*' with credentials=True is "
                "forbidden (browsers drop Access-Control-Allow-Credentials). "
                "Use a specific origin list instead. "
                f"Offending policies: {offenders!r}"
            )


# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

class CorsMiddleware:
    """Per-origin CORS middleware with preflight handling + caching headers.

    Drop-in replacement for ``starlette.middleware.cors.CORSMiddleware``
    that reads its config from a :class:`CorsConfig`.

    We DO NOT use Starlette's built-in CORSMiddleware because:
    1. It only allows ``list[str]`` of origins, not per-origin policies.
    2. It does not warn on ``*`` + credentials misconfigurations.
    """

    def __init__(
        self,
        app,
        *,
        config: Optional[CorsConfig] = None,
    ) -> None:
        self.app = app
        self._config: CorsConfig = config or CorsConfig()

    @property
    def config(self) -> CorsConfig:
        return self._config

    def configure(self, config: CorsConfig) -> None:
        self._config = config

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not self._config.enabled:
            await self.app(scope, receive, send)
            return

        headers_raw = scope.get("headers") or []
        request_origin: Optional[str] = None
        request_method: Optional[str] = None
        request_headers: List[str] = []
        for name, value in headers_raw:
            nl = name.decode("latin-1").lower()
            if nl == "origin":
                request_origin = value.decode("latin-1")
            elif nl == "access-control-request-method":
                request_method = value.decode("latin-1")
            elif nl == "access-control-request-headers":
                request_headers = [
                    h.strip() for h in value.decode("latin-1").split(",") if h.strip()
                ]

        method = scope.get("method", "GET").upper()
        is_preflight = (
            method == "OPTIONS"
            and request_origin is not None
            and request_method is not None
        )

        cors_headers = self._config.headers(
            request_origin, preflight=is_preflight,
        )

        if is_preflight:
            status = 204
            response_headers: List[Tuple[bytes, bytes]] = [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in cors_headers.items()
            ]
            # Add the standard preflight Content-Length: 0
            response_headers.append((b"content-length", b"0"))
            await send({"type": "http.response.start", "status": status, "headers": response_headers})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        # Non-preflight: pass through but inject headers into the response
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                resp_headers = list(message.get("headers") or [])
                # Normalise cors_headers to lower-case keys for lookup
                cors_headers_lc = {k.lower(): v for k, v in cors_headers.items()}
                injected_keys = {k.encode("latin-1") for k in cors_headers_lc.keys()}
                # Replace existing copies to avoid duplicates
                new_headers = []
                seen = set()
                for name, value in resp_headers:
                    nl = name.lower()
                    if nl in injected_keys:
                        if nl in seen:
                            continue
                        new_headers.append((name, cors_headers_lc[nl.decode("latin-1")].encode("latin-1")))
                        seen.add(nl)
                    else:
                        new_headers.append((name, value))
                        seen.add(nl)
                for k, v in cors_headers_lc.items():
                    kenc = k.encode("latin-1")
                    if kenc not in seen:
                        new_headers.append((kenc, v.encode("latin-1")))
                        seen.add(kenc)
                message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------

def resolve_cors(
    request_origin: Optional[str],
    *,
    config: Optional[CorsConfig] = None,
    preflight: bool = False,
) -> Dict[str, str]:
    """One-shot header builder (used by tests and external code)."""
    cfg = config or CorsConfig()
    return cfg.headers(request_origin, preflight=preflight)


__all__ = [
    "CorsConfig",
    "CorsPolicy",
    "CorsMiddleware",
    "resolve_cors",
]
