"""V5 P2 channel — StumbleUpon: discovery engine.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real StumbleUpon API, override `fetch()` with a httpx call
to StumbleUpon's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class StumbleuponAPI:
    channel = "stumbleupon"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[StumbleUpon] {query} - highly rated", "extra": {"views": 4321, "rating": 4.5}},
            {"title": f"[StumbleUpon] {query} - trending", "extra": {"views": 3210, "rating": 4.3}},
            {"title": f"[StumbleUpon] {query} - staff pick", "extra": {"views": 2100, "rating": 4.7}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://stumbleupon.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "stumbleupon-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
