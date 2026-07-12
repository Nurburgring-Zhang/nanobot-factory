"""V5 第32章 — Bilibili channel: BilibiliDL (mock — deterministic BV id)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class BilibiliDL:
    """Mock Bilibili downloader — BV-style id + deterministic metadata."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        bv_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10].upper()
        return FetchResult(
            success=True,
            channel="bilibili",
            query=query,
            content=f"Mock B站 video: '{query}' — placeholder subtitle.",
            url=f"https://bilibili.com/video/BV{bv_hash}",
            content_type="application/json",
            metadata={
                "engine": "bilibili-mock",
                "bv_id": f"BV{bv_hash}",
                "title": f"Mock B站视频 — {query}",
                "duration_seconds": 180 + (hash(query) % 720),
                "uploader": f"mock_up_{bv_hash[:6]}",
                "views": 5000 + (hash(query) % 50_000),
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["BilibiliDL"]