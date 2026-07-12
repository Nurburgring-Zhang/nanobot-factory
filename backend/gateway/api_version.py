"""API version routing + deprecation header middleware.

What this solves
================
The gateway currently treats ``/api/v1/*`` and ``/api/v2/*`` as
**opaque prefixes** that get forwarded to whichever upstream happens
to handle them.  In production we need to:

1. **Expose** the active version to the client via an
   ``X-API-Version`` response header.
2. **Emit** a deprecation warning (``Deprecation`` + ``Sunset`` +
   ``Link``) when v1 routes are still alive but flagged for retirement.
3. **Negotiate** the version via ``Accept: application/vnd.imdf.v2+json``
   when the client prefers a newer version than the URL prefix.
4. **Allow both** ``/api/v1`` and ``/api/v2`` to be hit independently
   (i.e. fix any duplicate-route issues if a v2 entry shadows a v1).

Design
======
* ``ApiVersion`` — enum-like str of supported major versions
* ``VersionNegotiator`` — pure function over ``path`` + ``Accept``
  header; returns the resolved ``ApiVersion``
* ``ApiVersionMiddleware`` — Starlette ``BaseHTTPMiddleware`` that
  decorates ``request.state.api_version`` and patches response headers
* ``DeprecationPolicy`` — dataclass loaded from YAML/ENV that decides
  which versions are deprecated and what ``Sunset`` date they carry

The middleware is **side-effect free on routing** — it does NOT
re-route or refuse requests; it only adds headers and stores the
resolved version on ``request.state``.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

log = logging.getLogger("gateway.api_version")


# ---------------------------------------------------------------------
# Version model
# ---------------------------------------------------------------------

class ApiVersion:
    """A single API version, e.g. ``v1`` or ``v2``.

    Comparable + hashable.  Use :meth:`from_string` to parse.
    """

    __slots__ = ("major", "minor")

    def __init__(self, major: int, minor: int = 0) -> None:
        if major < 0 or minor < 0:
            raise ValueError(f"invalid version: {major}.{minor}")
        self.major = int(major)
        self.minor = int(minor)

    @classmethod
    def from_string(cls, s: str) -> "ApiVersion":
        s = (s or "").strip().lower().lstrip("v").lstrip("V")
        m = re.match(r"^(\d+)(?:\.(\d+))?$", s)
        if not m:
            raise ValueError(f"cannot parse version: {s!r}")
        return cls(int(m.group(1)), int(m.group(2) or 0))

    def to_string(self) -> str:
        return f"v{self.major}.{self.minor}" if self.minor else f"v{self.major}"

    def __repr__(self) -> str:
        return self.to_string()

    def __str__(self) -> str:
        return self.to_string()

    def __hash__(self) -> int:
        return hash((self.major, self.minor))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ApiVersion) and (
            self.major, self.minor,
        ) == (other.major, other.minor)

    def __lt__(self, other: "ApiVersion") -> bool:
        return (self.major, self.minor) < (other.major, other.minor)

    def __le__(self, other: "ApiVersion") -> bool:
        return (self.major, self.minor) <= (other.major, other.minor)


# ---------------------------------------------------------------------
# Deprecation policy
# ---------------------------------------------------------------------

@dataclass
class DeprecationPolicy:
    """Per-version deprecation policy."""

    deprecated_versions: List[str] = field(default_factory=lambda: ["v1"])
    sunset_date: Optional[str] = None           # ISO date or ``None``
    successor_version: Optional[str] = None     # e.g. ``v2``
    docs_url: Optional[str] = None
    # Allow additional context, e.g. ``{"reason": "v2 ships native SSE"}``
    extra: Dict[str, Any] = field(default_factory=dict)
    # --- P0 #2 enforcement timeline (added 2026-07-01) ---
    # If set, once the current date is at or past ``enforce_after``,
    # the middleware returns **HTTP 410 Gone** for any request whose
    # negotiated version is in ``deprecated_versions``.  The header
    # phase (Deprecation / Sunset / Link) still runs in the window
    # between ``sunset_date`` and ``enforce_after`` so clients get a
    # chance to migrate.
    #
    # Default enforcement schedule: 30 days after ``sunset_date``.
    # Set explicitly to override.
    enforce_after: Optional[str] = None
    # Allow tests to inject a deterministic clock; production code
    # uses ``datetime.now(tz=UTC)``.
    _now_fn: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Default the enforcement date to sunset_date + 30 days, but
        # ONLY when both are present and enforce_after wasn't set
        # explicitly.  This gives clients a fixed 30-day migration
        # window after sunset, which is the industry-standard
        # deprecation pattern (RFC 8594 sunset + grace period).
        if self.enforce_after is None and self.sunset_date:
            try:
                sunset = self._parse_date(self.sunset_date)
                if sunset is not None:
                    from datetime import timedelta
                    grace = sunset + timedelta(days=30)
                    self.enforce_after = grace.strftime("%Y-%m-%d")
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("could not derive enforce_after: %s", exc)
        if self._now_fn is None:
            from datetime import datetime as _dt, timezone as _tz
            self._now_fn = lambda: _dt.now(tz=_tz.utc)

    @staticmethod
    def _parse_date(value: str):
        """Parse ``YYYY-MM-DD`` (with optional time / tz) into a datetime."""
        if not value:
            return None
        s = str(value).strip()
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            try:
                return datetime.fromisoformat(s)
            except ValueError:
                return None

    def is_deprecated(self, version: ApiVersion) -> bool:
        return version.to_string() in [
            ApiVersion.from_string(s).to_string() for s in self.deprecated_versions
        ]

    def is_enforced(self, version: ApiVersion) -> bool:
        """Return True if ``version`` is past its enforcement date.

        "Enforced" means: the middleware should **refuse** the request
        with HTTP 410 Gone rather than continuing to serve it.
        """
        if not self.is_deprecated(version):
            return False
        if not self.enforce_after:
            return False
        now = self._now_fn() if callable(self._now_fn) else self._now_fn
        deadline = self._parse_date(self.enforce_after)
        if deadline is None:
            return False
        # Make ``now`` comparable — accept aware or naive datetimes
        if now.tzinfo is None:
            from datetime import timezone as _tz
            now = now.replace(tzinfo=_tz.utc)
        if deadline.tzinfo is None:
            from datetime import timezone as _tz
            deadline = deadline.replace(tzinfo=_tz.utc)
        return now >= deadline

    def headers(self, version: ApiVersion) -> Dict[str, str]:
        if not self.is_deprecated(version):
            return {}
        out: Dict[str, str] = {}
        out["Deprecation"] = "true"
        if self.successor_version:
            out["Deprecation-Version"] = ApiVersion.from_string(
                self.successor_version,
            ).to_string()
        if self.sunset_date:
            try:
                dt = datetime.strptime(self.sunset_date, "%Y-%m-%d")
            except ValueError:
                dt = datetime.fromisoformat(self.sunset_date)
            # Force UTC for ``format_datetime(usegmt=True)``
            if dt.tzinfo is None:
                from datetime import timezone as _tz
                dt = dt.replace(tzinfo=_tz.utc)
            out["Sunset"] = format_datetime(dt, usegmt=True)
        if self.enforce_after:
            try:
                dt2 = datetime.strptime(self.enforce_after, "%Y-%m-%d")
            except ValueError:
                dt2 = datetime.fromisoformat(self.enforce_after)
            if dt2.tzinfo is None:
                from datetime import timezone as _tz
                dt2 = dt2.replace(tzinfo=_tz.utc)
            out["Sunset-Enforced-After"] = format_datetime(dt2, usegmt=True)
        if self.docs_url:
            link = f'<{self.docs_url}>; rel="deprecation"; type="text/html"'
            if self.successor_version:
                link += f'; from="{version.to_string()}"'
            out["Link"] = link
        return out


# ---------------------------------------------------------------------
# Config loader (YAML / ENV)
# ---------------------------------------------------------------------

@dataclass
class ApiVersionConfig:
    supported_versions: List[str] = field(default_factory=lambda: ["v1", "v2"])
    default_version: str = "v1"
    deprecation: DeprecationPolicy = field(default_factory=DeprecationPolicy)

    def version_tuple(self, s: str) -> ApiVersion:
        v = ApiVersion.from_string(s)
        supported = [ApiVersion.from_string(x).to_string() for x in self.supported_versions]
        if v.to_string() not in supported:
            raise ValueError(f"unsupported version: {v} (supported={supported})")
        return v

    # ---- constructors ----

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ApiVersionConfig":
        p = Path(path)
        if not p.exists():
            log.warning("api_version yaml not found: %s — using defaults", p)
            return cls()
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return cls.from_dict(data)

    @classmethod
    def from_env(cls, env_var: str = "API_VERSION_CONFIG") -> "ApiVersionConfig":
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
    def from_dict(cls, data: Dict[str, Any]) -> "ApiVersionConfig":
        section = data.get("api_version") if isinstance(data.get("api_version"), dict) else data
        if not isinstance(section, dict):
            section = {}
        supported = section.get("supported_versions") or ["v1", "v2"]
        if not isinstance(supported, list) or not supported:
            supported = ["v1", "v2"]
        default = section.get("default_version") or "v1"
        dep_data = section.get("deprecation") or {}
        dep = DeprecationPolicy(
            deprecated_versions=list(dep_data.get("deprecated_versions") or ["v1"]),
            sunset_date=dep_data.get("sunset_date") or None,
            successor_version=dep_data.get("successor_version") or None,
            docs_url=dep_data.get("docs_url") or None,
            enforce_after=dep_data.get("enforce_after") or None,
            extra=dict(dep_data.get("extra") or {}),
        )
        cfg = cls(
            supported_versions=[str(x) for x in supported],
            default_version=str(default),
            deprecation=dep,
        )
        cfg.version_tuple(cfg.default_version)  # validate default
        for v in cfg.supported_versions:
            cfg.version_tuple(v)
        return cfg


# ---------------------------------------------------------------------
# Negotiation
# ---------------------------------------------------------------------

class VersionNegotiator:
    """Decide the API version for an inbound HTTP request.

    Order of precedence:
        1. URL ``/api/<version>/...`` prefix
        2. ``Accept`` header ``application/vnd.imdf.v<MAJOR>+json``
        3. ``X-API-Version`` request header
        4. ``default_version`` from config
    """

    _URL_RE = re.compile(r"^/api/(v\d+(?:\.\d+)?)(/|$)")

    def __init__(self, config: ApiVersionConfig) -> None:
        self.config = config

    def negotiate(
        self,
        path: str,
        accept: Optional[str] = None,
        x_version: Optional[str] = None,
    ) -> ApiVersion:
        # 1. URL
        m = self._URL_RE.match(path or "")
        if m:
            try:
                return self.config.version_tuple(m.group(1))
            except ValueError:
                pass  # fall through to next
        # 2. Accept: application/vnd.imdf.v2+json
        if accept:
            m2 = re.search(r"application/vnd\.imdf\.v(\d+(?:\.\d+)?)\+json", accept)
            if m2:
                try:
                    return self.config.version_tuple(f"v{m2.group(1)}")
                except ValueError:
                    pass
        # 3. X-API-Version header
        if x_version:
            try:
                return self.config.version_tuple(x_version)
            except ValueError:
                pass
        # 4. Default
        return self.config.version_tuple(self.config.default_version)


# ---------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------

class ApiVersionMiddleware:
    """ASGI middleware that attaches ``X-API-Version`` and deprecation headers.

    Usage::

        app.add_middleware(ApiVersionMiddleware, config=cfg)
    """

    def __init__(
        self,
        app,
        *,
        config: Optional[ApiVersionConfig] = None,
    ) -> None:
        self.app = app
        self._config: ApiVersionConfig = config or ApiVersionConfig()
        self._negotiator = VersionNegotiator(self._config)

    @property
    def config(self) -> ApiVersionConfig:
        return self._config

    def configure(self, config: ApiVersionConfig) -> None:
        """Hot-swap config (useful in tests)."""
        self._config = config
        self._negotiator = VersionNegotiator(self._config)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            # pass-through for lifespan / websockets
            await self.app(scope, receive, send)
            return

        # --- negotiate version ---
        path = scope.get("path", "/")
        headers_raw = scope.get("headers") or []
        accept = None
        x_version = None
        for name, value in headers_raw:
            nl = name.decode("latin-1").lower()
            if nl == "accept":
                accept = value.decode("latin-1")
            elif nl == "x-api-version":
                x_version = value.decode("latin-1")

        version = self._negotiator.negotiate(path, accept=accept, x_version=x_version)

        # Persist for downstream
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["api_version"] = version

        # --- P0 #2: enforcement timeline ---
        # If the resolved version is past its enforcement date, refuse
        # the request with HTTP 410 Gone.  We still attach the
        # deprecation / sunset headers so clients can read the
        # migration target even on the failure response.
        if self._config.deprecation.is_enforced(version):
            await self._send_gone(scope, receive, send, version)
            return

        # --- response header injection ---
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Build header list; mutate by hand because Starlette raw send
                # doesn't expose .setdefault for case-insensitive names
                resp_headers = list(message.get("headers") or [])
                version_str = version.to_string()
                dep_headers = self._config.deprecation.headers(version)
                injected = {
                    b"x-api-version": version_str.encode("latin-1"),
                }
                for k, v in dep_headers.items():
                    injected[k.lower().encode("latin-1")] = v.encode("latin-1")

                # Replace any pre-existing copies
                new_headers: List[Tuple[bytes, bytes]] = []
                seen = set()
                for name, value in resp_headers:
                    nl = name.lower()
                    if nl in injected:
                        if nl in seen:
                            continue
                        new_headers.append((name, injected[nl]))
                        seen.add(nl)
                    else:
                        if nl in seen and nl == b"x-api-version":
                            continue
                        new_headers.append((name, value))
                        seen.add(nl)
                # Add any injected that didn't appear
                for k, v in injected.items():
                    if k not in seen:
                        new_headers.append((k, v))
                        seen.add(k)
                message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _send_gone(self, scope, receive, send, version: "ApiVersion") -> None:
        """Emit HTTP 410 Gone for an enforced-deprecated version.

        The response still carries the deprecation headers so clients
        can discover the migration target.  The body is a small JSON
        blob explaining what happened.
        """
        import json as _json
        body_dict = {
            "detail": "api_version_removed",
            "version": version.to_string(),
            "successor": self._config.deprecation.successor_version,
            "migration_docs": self._config.deprecation.docs_url,
            "enforce_after": self._config.deprecation.enforce_after,
        }
        body_bytes = _json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        headers: List[Tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body_bytes)).encode("latin-1")),
            (b"x-api-version", version.to_string().encode("latin-1")),
        ]
        # Always attach deprecation headers so clients get a hint.
        dep_headers = self._config.deprecation.headers(version)
        for k, v in dep_headers.items():
            headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
        await send({"type": "http.response.start", "status": 410, "headers": headers})
        await send({"type": "http.response.body", "body": body_bytes, "more_body": False})


# ---------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------

def negotiate(path: str, accept: Optional[str] = None, x_version: Optional[str] = None,
              config: Optional[ApiVersionConfig] = None) -> ApiVersion:
    """One-shot negotiator (used by tests and custom handlers)."""
    return VersionNegotiator(config or ApiVersionConfig()).negotiate(path, accept, x_version)


def api_version_from_url(path: str) -> Optional[ApiVersion]:
    m = VersionNegotiator._URL_RE.match(path or "")
    return ApiVersion.from_string(m.group(1)) if m else None


__all__ = [
    "ApiVersion",
    "ApiVersionConfig",
    "DeprecationPolicy",
    "VersionNegotiator",
    "ApiVersionMiddleware",
    "negotiate",
    "api_version_from_url",
]
