"""V5 第32章 — Instagram channel: Instaloader (mock — deterministic post)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class Instaloader:
    """Mock Instagram loader — 1 deterministic post per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:11]
        return FetchResult(
            success=True,
            channel="instagram",
            query=query,
            content=f"Mock Instagram post caption for '{query}'",
            url=f"https://instagram.com/p/{h}",
            content_type="application/json",
            metadata={
                "engine": "instaloader-mock",
                "shortcode": h,
                "likes": 512 + (hash(query) % 5_000),
                "comments": 12 + (hash(query) % 200),
                "is_mock": True,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["Instaloader"]