"""V5 P2 channel — Delicious: social bookmarking.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Delicious API, override `fetch()` with a httpx call
to Delicious's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class DeliciousAPI:
    channel = "delicious"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[delicious/{query}] Top saved link about {query}", "extra": {"saves": 1024, "tags_count": 32}},
            {"title": f"[delicious/{query}] Reference: {query} docs", "extra": {"saves": 512, "tags_count": 18}},
            {"title": f"[delicious/{query}] Tutorial: {query}", "extra": {"saves": 256, "tags_count": 12}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://delicious.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "delicious-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
