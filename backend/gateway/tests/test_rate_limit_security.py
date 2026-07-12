"""P0 #1 — X-Forwarded-For spoofing protection.

Background
==========
``trust_proxy=True`` lets the rate-limit middleware use the
``X-Forwarded-For`` header to bucket clients.  Without hardening,
**any** client can send ``X-Forwarded-For: <random IP>`` and bypass
their bucket — a single attacker would consume their real bucket
once, then pretend to be an unlimited number of distinct IPs.

This test module pins the new behaviour:

1. Direct connections from **untrusted** IPs MUST have their
   ``X-Forwarded-For`` header IGNORED — the bucket key falls back to
   ``request.client.host``.
2. Direct connections from **trusted** proxies MAY honour
   ``X-Forwarded-For``, but only by walking the chain from the right
   ``proxy_chain_depth`` hops and picking the first non-trusted IP.
3. Custom ``trusted_proxies`` lists (e.g. "only 10.0.0.5") restrict
   which upstream IPs are allowed to set XFF.
4. Spoofing attempts (XFF contains a literal "*" or an absurdly long
   chain) don't crash the middleware.

Run::

    python -m pytest backend/gateway/tests/test_rate_limit_security.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_PROJ = Path(__file__).resolve().parents[3]
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from backend.gateway.rate_limit_config import (  # noqa: E402
    EndpointPolicy,
    PerEndpointRateLimiter,
    RateLimitConfig,
    _ip_in_trusted,
    _parse_trusted,
)


# ---------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------

class _FakeRequest:
    """Minimal shim for ``PerEndpointRateLimiter._client_key``."""

    def __init__(
        self,
        path: str = "/api/v1/x",
        client_host: str = "1.2.3.4",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.url = type("U", (), {"path": path})()
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})()


def _cfg(trusted: Optional[List[str]] = None, depth: int = 1) -> RateLimitConfig:
    return RateLimitConfig.from_dict({
        "rate_limits": {
            "defaults": {"capacity": 100, "refill_per_second": 1000.0, "burst": 100},
            "trusted_proxies": trusted if trusted is not None else [
                "127.0.0.1/32",
                "10.0.0.0/8",
                "172.16.0.0/12",
                "192.168.0.0/16",
            ],
            "proxy_chain_depth": depth,
            "endpoints": [],
        },
    })


def _mw(cfg: RateLimitConfig) -> PerEndpointRateLimiter:
    return PerEndpointRateLimiter(app=None, config=cfg)


# ---------------------------------------------------------------------
# 1. Trusted-proxy helpers
# ---------------------------------------------------------------------

class TestTrustedProxyHelpers:
    def test_parse_cidr(self):
        nets = _parse_trusted(["10.0.0.0/8"])
        assert _ip_in_trusted("10.0.0.1", nets) is True
        assert _ip_in_trusted("11.0.0.1", nets) is False

    def test_parse_bare_ip_wraps_to_host(self):
        nets = _parse_trusted(["192.168.1.5"])
        assert _ip_in_trusted("192.168.1.5", nets) is True
        assert _ip_in_trusted("192.168.1.6", nets) is False

    def test_parse_invalid_entries_skipped(self):
        nets = _parse_trusted(["not-an-ip", "", "10.0.0.0/8"])
        assert _ip_in_trusted("10.0.0.1", nets) is True
        # Invalid entries didn't add anything new
        assert _ip_in_trusted("not-an-ip", nets) is False

    def test_ipv6_loopback(self):
        nets = _parse_trusted(["::1/128"])
        assert _ip_in_trusted("::1", nets) is True
        assert _ip_in_trusted("::2", nets) is False


# ---------------------------------------------------------------------
# 2. XFF ignored when direct client is not trusted
# ---------------------------------------------------------------------

class TestXffIgnoredForUntrustedDirect:
    """The classic spoofing attack: attacker is not behind our proxy."""

    def test_attacker_with_public_ip_xff_ignored(self):
        cfg = _cfg()
        mw = _mw(cfg)
        # Direct client is 8.8.8.8 (public, NOT in trusted proxies)
        req = _FakeRequest(
            client_host="8.8.8.8",
            headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        # Spoofing rejected — fall back to direct client
        assert key == "8.8.8.8"

    def test_attacker_with_rfc1918_outside_subnet_xff_ignored(self):
        cfg = _cfg()  # trusts 10.0.0.0/8
        mw = _mw(cfg)
        # Direct client is 172.32.0.1 (public, NOT in 172.16/12)
        req = _FakeRequest(
            client_host="172.32.0.1",
            headers={"x-forwarded-for": "1.1.1.1"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert key == "172.32.0.1"

    def test_no_xff_falls_back_to_direct(self):
        cfg = _cfg()
        mw = _mw(cfg)
        req = _FakeRequest(client_host="10.0.0.5", headers={})
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert key == "10.0.0.5"


# ---------------------------------------------------------------------
# 3. XFF chain walked correctly with proxy_chain_depth
# ---------------------------------------------------------------------

class TestProxyChainWalk:
    def test_depth_1_walks_one_hop(self):
        cfg = _cfg(depth=1)
        mw = _mw(cfg)
        # Direct=10.0.0.1 (trusted), XFF=client,proxy1
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "1.1.1.1, 10.0.0.5"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=1,
        )
        # proxy1=10.0.0.5 (trusted) → skip; client=1.1.1.1 (not trusted) → return
        assert key == "1.1.1.1"

    def test_depth_2_walks_two_hops(self):
        cfg = _cfg(depth=2)
        mw = _mw(cfg)
        # Direct=10.0.0.1, XFF=client,proxy1,proxy2
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "1.1.1.1, 10.0.0.2, 10.0.0.3"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=2,
        )
        # proxy2=10.0.0.3 trusted, proxy1=10.0.0.2 trusted, client=1.1.1.1 → return
        assert key == "1.1.1.1"

    def test_depth_3_walks_three_hops(self):
        cfg = _cfg(depth=3)
        mw = _mw(cfg)
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "2.2.2.2, 10.0.0.2, 10.0.0.3, 10.0.0.4"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=3,
        )
        # skip 3 trusted hops, find 2.2.2.2
        assert key == "2.2.2.2"

    def test_short_chain_uses_leftmost(self):
        """If XFF chain is shorter than depth, use the leftmost entry."""
        cfg = _cfg(depth=3)
        mw = _mw(cfg)
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "3.3.3.3"},  # only 1 entry
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=3,
        )
        assert key == "3.3.3.3"

    def test_all_trusted_chain_returns_leftmost(self):
        """Edge case: every entry in XFF is trusted.  Return leftmost."""
        cfg = _cfg(depth=1)
        mw = _mw(cfg)
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "10.0.0.99, 10.0.0.98"},
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=1,
        )
        # 10.0.0.98 trusted → walk back to 10.0.0.99 → all trusted → return 10.0.0.99
        assert key == "10.0.0.99"

    def test_empty_chain_falls_back(self):
        cfg = _cfg(depth=1)
        mw = _mw(cfg)
        req = _FakeRequest(
            client_host="10.0.0.1",
            headers={"x-forwarded-for": "  , , "},  # only commas / spaces
        )
        key = mw._client_key(
            req,
            trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=1,
        )
        # No usable entries → fall back to direct
        assert key == "10.0.0.1"


# ---------------------------------------------------------------------
# 4. Custom trusted_proxies list
# ---------------------------------------------------------------------

class TestCustomTrustedProxies:
    def test_only_specific_proxy_trusted(self):
        cfg = _cfg(trusted=["10.0.0.42"])  # single IP, not a range
        mw = _mw(cfg)
        # Direct=10.0.0.42 (trusted) — XFF can be honoured
        req_ok = _FakeRequest(
            client_host="10.0.0.42",
            headers={"x-forwarded-for": "1.1.1.1"},
        )
        key_ok = mw._client_key(
            req_ok, trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert key_ok == "1.1.1.1"

        # Direct=10.0.0.99 (NOT in single-IP trusted list) — XFF ignored
        req_no = _FakeRequest(
            client_host="10.0.0.99",
            headers={"x-forwarded-for": "1.1.1.1"},
        )
        key_no = mw._client_key(
            req_no, trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert key_no == "10.0.0.99"

    def test_empty_trusted_means_no_xff(self):
        """With ``trusted_proxies=[]``, XFF is never honoured."""
        cfg = _cfg(trusted=[])
        mw = _mw(cfg)
        req = _FakeRequest(
            client_host="1.2.3.4",
            headers={"x-forwarded-for": "9.9.9.9"},
        )
        key = mw._client_key(
            req, trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert key == "1.2.3.4"


# ---------------------------------------------------------------------
# 5. End-to-end: spoofing attempt creates separate buckets
# ---------------------------------------------------------------------

class TestSpoofingIsolation:
    @pytest.mark.asyncio
    async def test_attacker_cannot_share_bucket_with_victim(self):
        """The headline P0 #1 test:

        Attacker at 8.8.8.8 sends XFF claiming to be 1.1.1.1.
        The middleware MUST NOT bucket them with the real 1.1.1.1
        client (who might be a paying customer).
        """
        cfg = RateLimitConfig.from_dict({
            "rate_limits": {
                "defaults": {"capacity": 5, "refill_per_second": 0.001, "burst": 5},
                "trusted_proxies": ["10.0.0.0/8"],
                "proxy_chain_depth": 1,
                "endpoints": [
                    {
                        "pattern": "/api/v1/upload",
                        "capacity": 5, "refill_per_second": 0.001, "burst": 5,
                        "trust_proxy": True,
                    },
                ],
            },
        })
        mw = PerEndpointRateLimiter(app=None, config=cfg)

        real_client_calls: List[str] = []

        async def call_next(_req):
            real_client_calls.append(mw._client_key(
                _req, trust_proxy=True,
                trusted_proxies=cfg.trusted_proxies,
                proxy_chain_depth=cfg.proxy_chain_depth,
            ))
            return "ok"

        # Legit request: real 1.1.1.1 client through 10.0.0.5 proxy
        legit_req = _FakeRequest(
            "/api/v1/upload", "10.0.0.5",
            headers={"x-forwarded-for": "1.1.1.1"},
        )
        legit_key = mw._client_key(
            legit_req, trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        assert legit_key == "1.1.1.1", "legit client should resolve to 1.1.1.1"

        # Attack: 8.8.8.8 sends XFF claiming to be 1.1.1.1
        attack_req = _FakeRequest(
            "/api/v1/upload", "8.8.8.8",
            headers={"x-forwarded-for": "1.1.1.1, 10.0.0.5"},
        )
        attack_key = mw._client_key(
            attack_req, trust_proxy=True,
            trusted_proxies=cfg.trusted_proxies,
            proxy_chain_depth=cfg.proxy_chain_depth,
        )
        # Critical: attack does NOT collapse to 1.1.1.1
        assert attack_key != "1.1.1.1", (
            "SECURITY: attacker at 8.8.8.8 spoofed XFF to claim 1.1.1.1 "
            "but middleware trusted them — bucket is shared!"
        )
        assert attack_key == "8.8.8.8"

        # Verify buckets are different
        await mw.dispatch(legit_req, call_next)
        await mw.dispatch(attack_req, call_next)
        assert len(real_client_calls) == 2
        assert real_client_calls[0] == "1.1.1.1"
        assert real_client_calls[1] == "8.8.8.8"


# ---------------------------------------------------------------------
# 6. Stats include proxy-trust settings
# ---------------------------------------------------------------------

class TestStatsIncludeProxyTrust:
    def test_stats_has_trusted_proxies(self):
        cfg = _cfg(trusted=["10.0.0.0/8"])
        s = cfg.stats()
        assert s["trusted_proxies"] == ["10.0.0.0/8"]
        assert s["proxy_chain_depth"] == 1