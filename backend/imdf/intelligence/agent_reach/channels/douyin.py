"""V5 第32章 — Douyin channel: DouyinAPI (mock — deterministic video)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class DouyinAPI:
    """Mock Douyin API — 1 deterministic video per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:16]
        return FetchResult(
            success=True,
            channel="douyin",
            query=query,
            content=f"Mock 抖音 video description for '{query}'",
            url=f"https://douyin.com/video/{h}",
            content_type="application/json",
            metadata={
                "engine": "douyin-mock",
                "aweme_id": h,
                "author": f"mock_user_{h[:8]}",
                "likes": 2048 + (hash(query) % 50_000),
                "is_mock": True,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["DouyinAPI"]