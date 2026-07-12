"""Layer 6 — Sentry error aggregation.

A single in-process transport is exposed when ``sentry-sdk`` is unavailable so the rest
of the application can keep using ``capture_exception`` without an explicit guard.

Design notes
------------
* ``SENTRY_DSN`` env var (None disables the SDK entirely).
* ``environment`` defaults to ``APP_ENV`` then ``"production"``.
* All 13 backend services + imdf-main + frontend report through the same SDK init
  (the SDK auto-discoveries DSN per process). The local buffer (max 1000) is
  always populated, even when no DSN is set, so ``/api/v1/monitoring/errors`` works
  in dev / CI.
* Errors are tagged with ``service`` + ``layer`` (e.g. layer=sentry).
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, Optional

# --------------------------------------------------------------------------- #
# Optional sentry-sdk import. When missing, we fall back to a local buffer.
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - import-only branch
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    _HAS_SENTRY = True
except Exception:  # noqa: BLE001
    sentry_sdk = None  # type: ignore[assignment]
    _HAS_SENTRY = False


DEFAULT_BUFFER_SIZE = 1000
DEFAULT_RECENT_LIMIT = 100


@dataclass
class SentryEvent:
    """Minimal captured error record."""

    timestamp: float
    service: str
    layer: str
    message: str
    level: str
    tags: Dict[str, str] = field(default_factory=dict)
    exception_type: Optional[str] = None
    stack: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp)),
            "service": self.service,
            "layer": self.layer,
            "message": self.message,
            "level": self.level,
            "tags": self.tags,
            "exception_type": self.exception_type,
            "stack": self.stack,
            "context": self.context,
        }


class SentryHub:
    """Process-wide Sentry facade.

    The hub:
      * initialises ``sentry_sdk`` when ``SENTRY_DSN`` is set;
      * always maintains a ring-buffer of recent errors so the monitoring API
        works in dev / CI / Sentry-less environments.
    """

    def __init__(self, service: str = "imdf-main") -> None:
        self.service = service
        self.buffer: Deque[SentryEvent] = deque(maxlen=DEFAULT_BUFFER_SIZE)
        self._dsn: Optional[str] = None
        self._enabled: bool = False

    # -- configuration ------------------------------------------------------ #
    def init(
        self,
        dsn: Optional[str] = None,
        environment: Optional[str] = None,
        release: Optional[str] = None,
        sample_rate: float = 1.0,
        traces_sample_rate: float = 0.0,
        service: Optional[str] = None,
    ) -> bool:
        """Initialise Sentry. Returns True if the real SDK is active."""
        self.service = service or self.service
        self._dsn = dsn or os.getenv("SENTRY_DSN")
        env = environment or os.getenv("APP_ENV") or "production"

        if not self._dsn:
            self._enabled = False
            return False

        if not _HAS_SENTRY:
            # Real DSN requested but SDK not installed — log + buffer only.
            print(
                "[monitoring.sentry] SENTRY_DSN set but sentry-sdk not installed; "
                "falling back to in-memory buffer",
                file=sys.stderr,
            )
            self._enabled = False
            return False

        sentry_sdk.init(  # type: ignore[union-attr]
            dsn=self._dsn,
            environment=env,
            release=release,
            sample_rate=sample_rate,
            traces_sample_rate=traces_sample_rate,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
                LoggingIntegration(level=None, event_level=None),
            ],
            default_tags={"service": self.service, "layer": "sentry"},
        )
        self._enabled = True
        return True

    # -- capture ------------------------------------------------------------ #
    def capture_exception(
        self,
        exc: BaseException,
        *,
        layer: str = "backend",
        tags: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None,
        level: str = "error",
    ) -> None:
        """Capture an exception: forward to Sentry + local buffer."""
        ev = SentryEvent(
            timestamp=time.time(),
            service=self.service,
            layer=layer,
            message=str(exc) or exc.__class__.__name__,
            level=level,
            tags=dict(tags or {}),
            exception_type=exc.__class__.__name__,
            stack="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-8000:],
            context=dict(context or {}),
        )
        self.buffer.append(ev)

        if self._enabled and _HAS_SENTRY:
            with sentry_sdk.push_scope() as scope:  # type: ignore[union-attr]
                scope.set_tag("service", self.service)
                scope.set_tag("layer", layer)
                for k, v in (tags or {}).items():
                    scope.set_tag(k, v)
                if context:
                    for k, v in context.items():
                        scope.set_extra(k, v)
                sentry_sdk.capture_exception(exc)  # type: ignore[union-attr]

    def capture_message(
        self,
        message: str,
        *,
        layer: str = "backend",
        tags: Optional[Dict[str, str]] = None,
        level: str = "info",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ev = SentryEvent(
            timestamp=time.time(),
            service=self.service,
            layer=layer,
            message=message,
            level=level,
            tags=dict(tags or {}),
            exception_type=None,
            stack=None,
            context=dict(context or {}),
        )
        self.buffer.append(ev)

        if self._enabled and _HAS_SENTRY:
            with sentry_sdk.push_scope() as scope:  # type: ignore[union-attr]
                scope.set_tag("service", self.service)
                scope.set_tag("layer", layer)
                sentry_sdk.capture_message(message, level=level)  # type: ignore[union-attr]

    # -- query -------------------------------------------------------------- #
    def recent(self, limit: int = DEFAULT_RECENT_LIMIT, *, level: Optional[str] = None,
               service: Optional[str] = None, layer: Optional[str] = None) -> list[Dict[str, Any]]:
        out: list[Dict[str, Any]] = []
        for ev in reversed(self.buffer):
            if level and ev.level != level:
                continue
            if service and ev.service != service:
                continue
            if layer and ev.layer != layer:
                continue
            out.append(ev.to_dict())
            if len(out) >= limit:
                break
        return out

    # -- diagnostics -------------------------------------------------------- #
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def has_sdk(self) -> bool:
        return _HAS_SENTRY

    @property
    def dsn_configured(self) -> bool:
        return bool(self._dsn)

    def stats(self) -> Dict[str, Any]:
        by_level: Dict[str, int] = {}
        by_service: Dict[str, int] = {}
        for ev in self.buffer:
            by_level[ev.level] = by_level.get(ev.level, 0) + 1
            by_service[ev.service] = by_service.get(ev.service, 0) + 1
        return {
            "enabled": self._enabled,
            "sdk_installed": _HAS_SENTRY,
            "dsn_configured": bool(self._dsn),
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.maxlen,
            "by_level": by_level,
            "by_service": by_service,
        }


# --------------------------------------------------------------------------- #
# Singleton + module-level convenience helpers
# --------------------------------------------------------------------------- #
_HUB: Optional[SentryHub] = None


def get_hub(service: str = "imdf-main") -> SentryHub:
    global _HUB
    if _HUB is None:
        _HUB = SentryHub(service=service)
        _HUB.init()
    return _HUB


def init_for_service(service: str) -> SentryHub:
    """Initialise (or re-initialise) the singleton for a given microservice."""
    global _HUB
    _HUB = SentryHub(service=service)
    _HUB.init()
    return _HUB


def capture_exception(exc: BaseException, *, layer: str = "backend", **kw: Any) -> None:
    get_hub().capture_exception(exc, layer=layer, **kw)


def capture_message(message: str, *, layer: str = "backend", **kw: Any) -> None:
    get_hub().capture_message(message, layer=layer, **kw)
