"""V5 第32章 — xiaohongshu (小红书) channel: RedFox (mock)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class RedFox:
    """Mock xiaohongshu API — deterministic note entries."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        return FetchResult(
            success=True,
            channel="xiaohongshu",
            query=query,
            content=f"Mock 小红书笔记: 关于 '{query}' 的 2 条热门笔记",
            url=f"https://xiaohongshu.com/search?keyword={query}",
            content_type="application/json",
            metadata={
                "engine": "redfox-mock",
                "note_id": f"xhs_{h}",
                "title": f"关于{query}的种草笔记",
                "author": f"user_{h[:6]}",
                "likes": 1024 + (hash(query) % 10_000),
                "is_mock": True,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["RedFox"]