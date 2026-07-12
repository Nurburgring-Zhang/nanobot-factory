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

    async def fetch(self, url: str, **kwargs: Any) -> FetchResult:
        """Fetch a URL via Jina Reader — returns clean markdown.

        Args:
            url: target URL (will be appended after ``https://r.jina.ai/``)
            **kwargs: optional ``headers`` dict to override defaults

        Returns:
            FetchResult(success, content=markdown, url, content_type, metadata)
        """
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
            return FetchResult(
                success=False,
                channel="web",
                query=url,
                url=target,
                error=f"timeout after {self.timeout.total}s",
                metadata={"engine": "jina-reader"},
                latency_ms=(time.time() - start) * 1000.0,
            )
        except Exception as e:
            return FetchResult(
                success=False,
                channel="web",
                query=url,
                url=target,
                error=f"{type(e).__name__}: {e}",
                metadata={"engine": "jina-reader"},
                latency_ms=(time.time() - start) * 1000.0,
            )

    async def ping(self) -> bool:
        """Lightweight health check — try a trivial request."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.JINA_BASE}/https://example.com") as resp:
                    return 200 <= resp.status < 300
        except Exception as e:  # noqa: BLE001
            logger.debug("JinaReader ping failed: %s", e)
            return False


__all__ = ["JinaReader"]