"""V5 第32章 — RSS channel: FeedParser (mock — deterministic feed entries)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class FeedParser:
    """Mock RSS feed parser — returns 2 deterministic entries per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        entries = [
            {
                "title": f"RSS entry 1 about {query}",
                "link": f"https://mock-feed-{h}.example.com/post/1",
                "published": "2026-01-15T09:00:00Z",
                "summary": f"Mock summary 1 for {query}",
            },
            {
                "title": f"RSS entry 2 about {query}",
                "link": f"https://mock-feed-{h}.example.com/post/2",
                "published": "2026-01-15T12:00:00Z",
                "summary": f"Mock summary 2 for {query}",
            },
        ]
        return FetchResult(
            success=True,
            channel="rss",
            query=query,
            content="\n".join(f"[{e['published']}] {e['title']}" for e in entries),
            url=f"https://mock-feed-{h}.example.com/feed.xml",
            content_type="application/rss+xml",
            metadata={
                "engine": "feedparser-mock",
                "entries": entries,
                "feed_title": f"Mock Feed {h[:6]}",
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["FeedParser"]