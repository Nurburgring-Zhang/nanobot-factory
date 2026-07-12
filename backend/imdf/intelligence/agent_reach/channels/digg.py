"""V5 P2 channel — Digg: news aggregator.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Digg API, override `fetch()` with a httpx call
to Digg's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class DiggAPI:
    channel = "digg"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[Digg Front Page] {query} hits the front page", "extra": {"diggs": 432, "comments": 89}},
            {"title": f"[Digg Tech] Discussion: {query}", "extra": {"diggs": 256, "comments": 42}},
            {"title": f"[Digg World] {query} global impact", "extra": {"diggs": 128, "comments": 19}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://digg.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "digg-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
