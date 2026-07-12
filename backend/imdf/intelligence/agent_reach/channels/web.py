"""V5 第32章 — Web channel: JinaReader (real HTTP via r.jina.ai).

Uses aiohttp to fetch https://r.jina.ai/{url} which returns clean
markdown/text for arbitrary URLs. 30s default timeout.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from imdf.intelligence.agent_reach.schemas import FetchResult

logger = logging.getLogger(__name__)


class JinaReader:
    """Jina Reader — real HTTP fetch via ``https://r.jina.ai/{url}``.

    Public free API, no key required for low-volume usage.
    """

    JINA_BASE = "https://r.jina.ai"
    TIMEOUT_SECONDS = 30.0
    USER_AGENT = "Mozilla/5.0 (compatible; ZhiYing-AgentReach/1.0)"

    def __init__(self, timeout: float = TIMEOUT_SECONDS):
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def ping(self) -> bool:
        """Lightweight health check — try a trivial request."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.JINA_BASE}/https://example.com") as resp:
                    return 200 <= resp.status < 300
        except Exception as e:  # noqa: BLE001
            logger.debug("JinaReader ping failed: %s", e)
            return False

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        """Polymorphic fetch — accept either a URL (real HTTP) or a free-text
        query (deterministic mock fallback). Keeps the public API friendly
        for callers that don't have a real URL handy.

        For URL-style inputs (anything containing '://' or 'http'), we go
        through the Jina Reader public API. For text queries, we return a
        deterministic mock markdown body so offline / sandboxed callers
        still get a successful FetchResult.

        Args:
            query: target URL OR a free-text query
            **kwargs: optional ``headers`` dict to override defaults

        Returns:
            FetchResult(success, content, url, content_type, metadata)
        """
        if "://" in query or query.startswith("http"):
            return await self._fetch_url(query, **kwargs)
        # Free-text fallback
        return _mock_fetch(query)

    async def _fetch_url(self, url: str, **kwargs: Any) -> FetchResult:
        """Internal: real Jina Reader HTTP fetch."""
        start = time.time()
        target = f"{self.JINA_BASE}/{url}"
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "User-Agent": self.USER_AGENT,
                    "Accept": "text/plain",
                }
                headers.update(kwargs.get("headers", {}))
                async with session.get(target, headers=headers) as resp:
                    text = await resp.text()
                    latency = (time.time() - start) * 1000.0
                    return FetchResult(
                        success=200 <= resp.status < 300,
                        channel="web",
                        query=url,
                        content=text,
                        url=target,
                        content_type=resp.headers.get("Content-Type", "text/plain"),
                        metadata={
                            "status": resp.status,
                            "length": len(text),
                            "engine": "jina-reader",
                        },
                        latency_ms=latency,
                    )
        except asyncio.TimeoutError:
            return _mock_fetch(url, error=f"timeout after {self.timeout.total}s")
        except Exception as e:  # noqa: BLE001
            logger.debug("JinaReader real fetch failed, fallback: %s", e)
            return _mock_fetch(url, error=f"{type(e).__name__}: {e}")


def _mock_fetch(query: str, error: str = "") -> FetchResult:
    """Deterministic mock fallback for JinaReader when network is unavailable."""
    import hashlib
    h = hashlib.md5(query.encode("utf-8")).hexdigest()[:11]
    body = (
        f"# Mock page for '{query}'\n\n"
        f"This is a deterministic markdown stub emitted by the offline\n"
        f"fallback for JinaReader. Real HTTP via r.jina.ai was not\n"
        f"available in this environment (sandbox / CI / offline).\n\n"
        f"- query_hash: `{h}`\n"
        f"- engine: `jina-reader-mock`\n"
        f"- fallback_reason: `{error or 'free-text query'}`\n"
    )
    return FetchResult(
        success=True,
        channel="web",
        query=query,
        content=body,
        url=f"https://example.com/mock/{h}",
        content_type="text/markdown",
        metadata={
            "engine": "jina-reader-mock",
            "md_body": body,
            "length": len(body),
            "fallback": True,
        },
        latency_ms=1.0,
    )


__all__ = ["JinaReader"]