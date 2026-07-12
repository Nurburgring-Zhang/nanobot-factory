"""P0 #2 — API version deprecation timeline + 410 Gone enforcement.

Background
==========
The original ``DeprecationPolicy`` only emitted deprecation headers
(``Deprecation: true``, ``Sunset``, ``Link``).  Nothing actually
**refused** traffic after the sunset date.  In production this means
legacy v1 clients keep consuming capacity forever, blocking our
ability to decommission the upstream service.

P0 #2 adds:

1. ``enforce_after`` — explicit ISO date past which the middleware
   returns HTTP **410 Gone** for any request whose negotiated version
   is in ``deprecated_versions``.
2. **Default 30-day grace period** — if only ``sunset_date`` is set,
   ``enforce_after`` defaults to ``sunset_date + 30 days``.  This is
   the industry-standard migration window pattern (RFC 8594 sunset).
3. **Header phase** — between sunset and enforcement, clients get
   deprecation headers; after enforcement they get 410 Gone with the
   same headers and a JSON migration payload.

Run::

    python -m pytest backend/gateway/tests/test_api_version_deprecation.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.api_version import (  # noqa: E402
    ApiVersion,
    ApiVersionConfig,
    ApiVersionMiddleware,
    DeprecationPolicy,
    VersionNegotiator,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _fixed_now(year: int, month: int, day: int) -> Callable[[], datetime]:
    """Return a ``_now_fn`` callable returning a fixed UTC datetime."""
    fixed = datetime(year, month, day, tzinfo=timezone.utc)
    return lambda: fixed


# ---------------------------------------------------------------------
# 1. is_enforced + is_deprecated
# ---------------------------------------------------------------------

class TestIsEnforced:
    def test_non_deprecated_never_enforced(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            sunset_date="2026-01-01",
            enforce_after="2026-02-01",
            _now_fn=_fixed_now(2027, 1, 1),
        )
        assert dep.is_deprecated(ApiVersion.from_string("v1")) is True
        assert dep.is_deprecated(ApiVersion.from_string("v2")) is False
        # Even though v2 isn't deprecated, enforce_after shouldn't fire.
        assert dep.is_enforced(ApiVersion.from_string("v2")) is False

    def test_not_enforced_before_deadline(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            sunset_date="2026-01-01",
            enforce_after="2026-02-01",
            _now_fn=_fixed_now(2026, 1, 15),
        )
        assert dep.is_enforced(ApiVersion.from_string("v1")) is False

    def test_enforced_at_deadline(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            sunset_date="2026-01-01",
            enforce_after="2026-02-01",
            _now_fn=_fixed_now(2026, 2, 1),
        )
        assert dep.is_enforced(ApiVersion.from_string("v1")) is True

    def test_enforced_after_deadline(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            sunset_date="2026-01-01",
            enforce_after="2026-02-01",
            _now_fn=_fixed_now(2026, 6, 1),
        )
        assert dep.is_enforced(ApiVersion.from_string("v1")) is True

    def test_no_enforce_after_never_enforced(self):
        """If both sunset_date and enforce_after are unset, never enforce.

        Note: when ``sunset_date`` is set, ``enforce_after`` defaults to
        ``sunset_date + 30 days`` via ``__post_init__``.  This test
        exercises the case where *neither* is set (so ``enforce_after``
        stays None) and verifies that ``is_enforced`` returns False
        regardless of the current date.
        """
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            _now_fn=_fixed_now(2030, 1, 1),
        )
        # No sunset, no enforce_after → header-only phase forever.
        assert dep.enforce_after is None
        assert dep.is_enforced(ApiVersion.from_string("v1")) is False


# ---------------------------------------------------------------------
# 2. Default 30-day grace period
# ---------------------------------------------------------------------

class TestDefaultGracePeriod:
    def test_default_30_days_after_sunset(self):
        dep = DeprecationPolicy(sunset_date="2026-01-01")
        # No explicit enforce_after → defaults to sunset + 30 days
        assert dep.enforce_after == "2026-01-31"

    def test_explicit_enforce_after_respected(self):
        dep = DeprecationPolicy(
            sunset_date="2026-01-01",
            enforce_after="2026-12-31",
        )
        assert dep.enforce_after == "2026-12-31"

    def test_no_sunset_no_default_enforce(self):
        dep = DeprecationPolicy()
        assert dep.sunset_date is None
        assert dep.enforce_after is None

    def test_invalid_sunset_no_default_enforce(self):
        """Invalid sunset_date string doesn't blow up; just no default."""
        dep = DeprecationPolicy(sunset_date="not-a-date")
        # Should fall back to no default enforcement
        assert dep.enforce_after is None


# ---------------------------------------------------------------------
# 3. Headers include Sunset-Enforced-After
# ---------------------------------------------------------------------

class TestEnforcementHeader:
    def test_header_includes_enforced_after(self):
        dep = DeprecationPolicy(
            deprecated_versions=["v1"],
            sunset_date="2026-01-01",
            enforce_after="2026-02-01",
        )
        h = dep.headers(ApiVersion.from_string("v1"))
        assert "Sunset-Enforced-After" in h
        assert "GMT" in h["Sunset-Enforced-After"]
        assert "01 Feb 2026" in h["Sunset-Enforced-After"]

    def test_header_only_when_explicit(self):
        """Default-derived enforce_after still appears in headers."""
        dep = DeprecationPolicy(sunset_date="2026-01-01")
        h = dep.headers(ApiVersion.from_string("v1"))
        assert "Sunset-Enforced-After" in h
        assert "31 Jan 2026" in h["Sunset-Enforced-After"]


# ---------------------------------------------------------------------
# 4. Middleware emits 410 Gone after enforcement
# ---------------------------------------------------------------------

class TestMiddlewareEnforcement:
    @pytest.mark.asyncio
    async def test_410_for_v1_after_enforce(self):
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v2",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-01-01",
                    "enforce_after": "2026-02-01",
                    "successor_version": "v2",
                },
            },
        })
        # Pin "now" to a date AFTER enforce_after
        cfg.deprecation._now_fn = _fixed_now(2026, 6, 1)

        response_started: Dict[str, Any] = {}
        body_chunks: List[bytes] = []

        async def inner_app(scope, receive, send):
            # Should never be called
            raise RuntimeError("inner_app should not run for enforced-deprecated request")

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_started["status"] = message.get("status")
                response_started["headers"] = list(message.get("headers") or [])
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body") or b"")

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http", "method": "GET", "path": "/api/v1/users",
            "headers": [], "query_string": b"",
        }
        await mw(scope, None, fake_send)

        # 410 Gone
        assert response_started["status"] == 410
        # Headers carry migration hints
        hmap = {n.lower(): v for n, v in response_started["headers"]}
        assert hmap[b"x-api-version"] == b"v1"
        assert hmap[b"deprecation"] == b"true"
        # Sunset + Sunset-Enforced-After
        assert b"sunset" in hmap
        assert b"sunset-enforced-after" in hmap
        # Body is JSON
        body = b"".join(body_chunks)
        payload = json.loads(body.decode("utf-8"))
        assert payload["detail"] == "api_version_removed"
        assert payload["version"] == "v1"
        assert payload["successor"] == "v2"

    @pytest.mark.asyncio
    async def test_v2_unaffected_after_enforcement(self):
        """v2 traffic MUST keep flowing even after v1 is enforced."""
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v2",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-01-01",
                    "enforce_after": "2026-02-01",
                },
            },
        })
        cfg.deprecation._now_fn = _fixed_now(2026, 6, 1)

        inner_called = {"n": 0}
        response_started: Dict[str, Any] = {}

        async def inner_app(scope, receive, send):
            inner_called["n"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_started["status"] = message.get("status")
                response_started["headers"] = list(message.get("headers") or [])

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http", "method": "GET", "path": "/api/v2/users",
            "headers": [], "query_string": b"",
        }
        await mw(scope, None, fake_send)

        assert inner_called["n"] == 1
        assert response_started["status"] == 200
        # No Deprecation header for v2
        hmap = {n.lower(): v for n, v in response_started["headers"]}
        assert b"deprecation" not in hmap

    @pytest.mark.asyncio
    async def test_header_phase_before_enforce(self):
        """Between sunset and enforce_after: headers only, no 410."""
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v1",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-01-01",
                    "enforce_after": "2026-02-01",
                },
            },
        })
        cfg.deprecation._now_fn = _fixed_now(2026, 1, 15)  # after sunset, before enforce

        inner_called = {"n": 0}
        response_started: Dict[str, Any] = {}

        async def inner_app(scope, receive, send):
            inner_called["n"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

        async def fake_send(message):
            if message["type"] == "http.response.start":
                response_started["status"] = message.get("status")
                response_started["headers"] = list(message.get("headers") or [])

        mw = ApiVersionMiddleware(inner_app, config=cfg)
        scope = {
            "type": "http", "method": "GET", "path": "/api/v1/users",
            "headers": [], "query_string": b"",
        }
        await mw(scope, None, fake_send)

        # Inner was called (no 410)
        assert inner_called["n"] == 1
        # 200 OK
        assert response_started["status"] == 200
        # But Deprecation header still present
        hmap = {n.lower(): v for n, v in response_started["headers"]}
        assert hmap[b"deprecation"] == b"true"
        assert b"sunset" in hmap


# ---------------------------------------------------------------------
# 5. Config loader respects enforce_after
# ---------------------------------------------------------------------

class TestConfigLoader:
    def test_enforce_after_loaded(self):
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v2",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "enforce_after": "2026-12-31",
                },
            },
        })
        assert cfg.deprecation.enforce_after == "2026-12-31"

    def test_enforce_after_default_when_only_sunset_set(self):
        cfg = ApiVersionConfig.from_dict({
            "api_version": {
                "supported_versions": ["v1", "v2"],
                "default_version": "v2",
                "deprecation": {
                    "deprecated_versions": ["v1"],
                    "sunset_date": "2026-06-01",
                },
            },
        })
        # 30 days after sunset
        assert cfg.deprecation.enforce_after == "2026-07-01"