"""V5 第32章 — Twitter channel: TwitterAPI (mock — no real call).

Deterministic mock: returns 3 fake tweets with stable IDs derived from
the query hash so tests can assert reproducibility.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class TwitterAPI:
    """Mock Twitter API — deterministic fake tweets per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        """Return 3 mock tweets deterministically derived from query hash."""
        start = time.time()
        qhash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:8]
        tweets = [
            {
                "id": f"tw_{qhash}_1",
                "author": f"user_{qhash[:4]}",
                "text": f"Mock tweet 1 about '{query}' — interesting times!",
                "likes": 42,
                "retweets": 7,
                "created_at": "2026-01-15T10:00:00Z",
            },
            {
                "id": f"tw_{qhash}_2",
                "author": f"user_{qhash[4:]}",
                "text": f"Mock tweet 2 about '{query}' — second take.",
                "likes": 18,
                "retweets": 2,
                "created_at": "2026-01-15T11:30:00Z",
            },
            {
                "id": f"tw_{qhash}_3",
                "author": f"user_{qhash[:6]}",
                "text": f"Mock tweet 3 about '{query}' — and a third one.",
                "likes": 99,
                "retweets": 14,
                "created_at": "2026-01-15T13:45:00Z",
            },
        ]
        content_lines = [f"@{t['author']}: {t['text']}" for t in tweets]
        return FetchResult(
            success=True,
            channel="twitter",
            query=query,
            content="\n".join(content_lines),
            url=f"https://twitter.com/search?q={query}",
            content_type="application/json",
            metadata={
                "engine": "twitter-mock",
                "count": len(tweets),
                "tweets": tweets,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["TwitterAPI"]