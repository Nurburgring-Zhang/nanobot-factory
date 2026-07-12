"""V5 第32章 — Reddit channel: RedditAPI (mock — deterministic thread entries)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class RedditAPI:
    """Mock Reddit API — returns 2 deterministic threads per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        rh = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        threads = [
            {
                "id": f"t3_{rh}01",
                "subreddit": f"r/{rh[:3]}",
                "title": f"[Discussion] {query} — perspectives?",
                "score": 256,
                "comments": 42,
            },
            {
                "id": f"t3_{rh}02",
                "subreddit": f"r/{rh[3:]}",
                "title": f"[News] {query} — latest updates",
                "score": 128,
                "comments": 19,
            },
        ]
        return FetchResult(
            success=True,
            channel="reddit",
            query=query,
            content="\n".join(f"[{t['subreddit']}] {t['title']}" for t in threads),
            url=f"https://reddit.com/search/?q={query}",
            content_type="application/json",
            metadata={
                "engine": "reddit-mock",
                "count": len(threads),
                "threads": threads,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["RedditAPI"]