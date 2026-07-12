"""V5 P2 channel — Hacker News: tech news.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Hacker News API, override `fetch()` with a httpx call
to Hacker News's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class HackernewsAPI:
    channel = "hackernews"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[HN] Show HN: {query}", "extra": {"points": 512, "comments": 156, "kind": 'show_hn'}},
            {"title": f"[HN] Ask HN: {query}?", "extra": {"points": 256, "comments": 89, "kind": 'ask_hn'}},
            {"title": f"[HN] {query} - a technical deep dive", "extra": {"points": 1024, "comments": 234, "kind": 'story'}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://hackernews.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "hackernews-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
