"""Shared HTTP helper for live P2 channel adapters.

Channels that have a public no-auth API use this module to fetch real
data. Channels that require API keys (Feedly/Digg/Tumblr/Pocket/Instapaper)
fall back to mock mode unless their env key is set; the dispatch happens
inside each channel's ``fetch()`` method.

This module is intentionally tiny — no Pydantic models, no retry
backoff. If a real channel needs retry / auth headers, extend per-channel.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    import httpx  # type: ignore
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


async def http_get_json(url: str, *, timeout: float = 15.0, headers: Optional[Dict[str, str]] = None) -> Any:
    """GET a URL and parse JSON. Returns the parsed value on success,
    raises on any error so callers can fall back to mock mode."""
    headers = headers or {}
    headers.setdefault("Accept", "application/json")
    headers.setdefault("User-Agent", "nanobot-factory/2.0 (https://github.com/Nurburgring-Zhang/nanobot-factory)")

    if _HAS_HTTPX:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
    # urllib fallback (sync, in thread)
    def _urllib_get() -> Any:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read())
    return await asyncio.to_thread(_urllib_get)


async def http_get_text(url: str, *, timeout: float = 15.0, headers: Optional[Dict[str, str]] = None) -> str:
    """GET a URL and return the raw text. For HTML / XML / RSS / Atom feeds
    that the caller parses with regex / feedparser."""
    headers = headers or {}
    headers.setdefault("User-Agent", "nanobot-factory/2.0 (https://github.com/Nurburgring-Zhang/nanobot-factory)")
    if _HAS_HTTPX:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text
    def _urllib_get() -> str:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")
    return await asyncio.to_thread(_urllib_get)


def is_https(url: str) -> bool:
    """Quick safety check before fetching a user-supplied URL."""
    try:
        return urlparse(url).scheme == "https"
    except Exception:
        return False


def domain(url: str) -> str:
    """Return the netloc (host) of a URL, or empty string on parse error."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def strip_html(text: str) -> str:
    """Crude HTML tag stripper for feed snippets — does NOT sanitise,
    so do not use on attacker-controlled input. For our use case (RSS
    feed titles + descriptions) it is safe and fast."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()
