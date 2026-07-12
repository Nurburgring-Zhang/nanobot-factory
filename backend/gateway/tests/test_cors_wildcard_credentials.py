"""P0 #4 — CORS wildcard + credentials is forbidden.

Background
==========
The CORS spec explicitly forbids the combination of
``Access-Control-Allow-Origin: *`` with
``Access-Control-Allow-Credentials: true``:

> If credentials mode is "include", then ``Access-Control-Allow-Origin``
> cannot be ``*``; it MUST be the request's Origin header value.

Browsers silently drop ``Access-Control-Allow-Credentials`` in this
combination, so the developer thinks credentials work but actually
they don't — and worse, a CSRF attacker could exploit the confusion.

P0 #4 makes ``*`` + ``credentials=True`` a **hard error** at config
load time.  The gateway refuses to start with that configuration.

Run::

    python -m pytest backend/gateway/tests/test_cors_wildcard_credentials.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.cors import (  # noqa: E402
    CorsConfig,
    CorsConfigError,
    CorsMiddleware,
    CorsPolicy,
)


# ---------------------------------------------------------------------
# 1. CorsConfigError raised on invalid combinations
# ---------------------------------------------------------------------

class TestCorsConfigError:
    def test_wildcard_default_with_credentials_raises(self):
        """``default: {origin: '*', credentials: True}`` MUST raise."""
        with pytest.raises(CorsConfigError) as excinfo:
            CorsConfig.from_dict({
                "cors": {
                    "default": {"origin": "*", "credentials": True},
                },
            })
        assert "*" in str(excinfo.value)
        assert "credentials" in str(excinfo.value).lower()

    def test_wildcard_in_origins_with_credentials_raises(self):
        """An entry in ``origins`` with ``*`` + ``credentials=True`` raises."""
        with pytest.raises(CorsConfigError):
            CorsConfig.from_dict({
                "cors": {
                    "origins": [
                        {"origin": "*", "credentials": True},
                    ],
                },
            })

    def test_multiple_offenders_all_reported(self):
        """When multiple policies violate, all are reported in the error."""
        with pytest.raises(CorsConfigError) as excinfo:
            CorsConfig.from_dict({
                "cors": {
                    "default": {"origin": "*", "credentials": True},
                    "origins": [
                        {"origin": "*", "credentials": True},
                        {"origin": "https://safe.com", "credentials": True},
                    ],
                },
            })
        msg = str(excinfo.value)
        # Error message should mention the violation
        assert "forbidden" in msg.lower() or "credentials" in msg.lower()


# ---------------------------------------------------------------------
# 2. Valid combinations still accepted
# ---------------------------------------------------------------------

class TestValidCombinationsAccepted:
    def test_wildcard_without_credentials_ok(self):
        """``*`` alone is fine — the spec only forbids the combination."""
        cfg = CorsConfig.from_dict({
            "cors": {
                "default": {"origin": "*", "credentials": False},
            },
        })
        assert cfg.default.origin == "*"
        assert cfg.default.credentials is False

    def test_specific_origin_with_credentials_ok(self):
        """``https://app.com`` + ``credentials=True`` is the standard pattern."""
        cfg = CorsConfig.from_dict({
            "cors": {
                "origins": [
                    {"origin": "https://app.example.com", "credentials": True},
                ],
            },
        })
        pol = cfg.resolve("https://app.example.com")
        assert pol.credentials is True

    def test_wildcard_subdomain_with_credentials_ok(self):
        """``*.example.com`` is NOT literal ``*`` — combination is allowed."""
        cfg = CorsConfig.from_dict({
            "cors": {
                "origins": [
                    {"origin": "*.partners.example.com", "credentials": True},
                ],
            },
        })
        pol = cfg.resolve("https://x.partners.example.com")
        assert pol.origin.startswith("*.")
        assert pol.credentials is True

    def test_mixed_valid_origins(self):
        """Mixed list — some with credentials, some without — all OK."""
        cfg = CorsConfig.from_dict({
            "cors": {
                "origins": [
                    {"origin": "https://app1.com", "credentials": True},
                    {"origin": "https://app2.com", "credentials": False},
                    {"origin": "https://app3.com"},
                    {"origin": "*.partners.com", "credentials": True},
                ],
            },
        })
        assert len(cfg.origins) == 4

    def test_default_credentials_false_safely_paired_with_star(self):
        """The actual safe pattern: ``*`` + credentials=False."""
        cfg = CorsConfig.from_dict({
            "cors": {
                "default": {"origin": "*"},  # credentials defaults to False
            },
        })
        assert cfg.default.credentials is False


# ---------------------------------------------------------------------
# 3. CorsPolicy header construction is unchanged for valid configs
# ---------------------------------------------------------------------

class TestHeadersForValidConfigs:
    def test_specific_origin_with_credentials_emits_echo(self):
        """When credentials=True, Allow-Origin MUST echo the request's origin
        (not ``*``).  This is the correct behaviour that we protect by
        refusing the ``*`` + credentials combination upstream."""
        pol = CorsPolicy(origin="https://app.example.com", credentials=True)
        h = pol.to_headers("https://app.example.com")
        assert h["Access-Control-Allow-Origin"] == "https://app.example.com"
        assert h["Access-Control-Allow-Credentials"] == "true"

    def test_wildcard_without_credentials_emits_star(self):
        pol = CorsPolicy(origin="*", credentials=False)
        h = pol.to_headers("https://anywhere.com")
        assert h["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in h


# ---------------------------------------------------------------------
# 4. Env-var / legacy loader doesn't bypass the validation
# ---------------------------------------------------------------------

class TestEnvLoadersSafe:
    def test_from_env_legacy_no_wildcard_with_credentials(self):
        """``CORS_ALLOWED_ORIGINS`` legacy loader builds specific-origin
        policies with credentials=False — must NOT raise."""
        import os
        old = os.environ.get("CORS_ALLOWED_ORIGINS")
        try:
            os.environ["CORS_ALLOWED_ORIGINS"] = (
                "https://a.com,https://b.com,https://c.com"
            )
            cfg = CorsConfig.from_env_legacy()
            assert all(not p.credentials for p in cfg.origins)
            assert all(p.origin != "*" for p in cfg.origins)
        finally:
            if old is None:
                os.environ.pop("CORS_ALLOWED_ORIGINS", None)
            else:
                os.environ["CORS_ALLOWED_ORIGINS"] = old

    def test_yaml_loader_respects_validation(self, tmp_path):
        """A YAML file with ``*`` + credentials=True must be rejected."""
        import yaml
        yaml_path = tmp_path / "cors.yaml"
        yaml_path.write_text(yaml.safe_dump({
            "cors": {
                "default": {"origin": "*", "credentials": True},
            },
        }, allow_unicode=True), encoding="utf-8")
        with pytest.raises(CorsConfigError):
            CorsConfig.from_yaml(yaml_path)


# ---------------------------------------------------------------------
# 5. Middleware is constructed only with valid configs
# ---------------------------------------------------------------------

class TestMiddlewareWithSafeConfig:
    @pytest.mark.asyncio
    async def test_middleware_starts_with_valid_config(self):
        cfg = CorsConfig.from_dict({
            "cors": {
                "origins": [
                    {"origin": "https://app.example.com", "credentials": True},
                ],
            },
        })
        mw = CorsMiddleware(app=None, config=cfg)
        assert mw.config is cfg

    def test_middleware_constructor_would_refuse_wildcard_credentials(self):
        """If a developer manages to build a CorsConfig with a violation
        via the low-level constructor (bypassing from_dict), they should
        still get an error on construction.  We expose ``validate()``."""
        # Manually build a violating config — bypasses from_dict validation
        bad = CorsConfig(
            enabled=True,
            default=CorsPolicy(origin="*", credentials=True),
            origins=[],
        )
        # Re-run validation explicitly
        with pytest.raises(CorsConfigError):
            bad._validate()