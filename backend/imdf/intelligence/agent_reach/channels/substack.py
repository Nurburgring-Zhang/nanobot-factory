"""V5 P2 channel — Substack: newsletters.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Substack API, override `fetch()` with a httpx call
to Substack's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class SubstackAPI:
    channel = "substack"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[Substack] {query} weekly digest", "extra": {"subscribers": 2500, "open_rate": 89}},
            {"title": f"[Substack] {query} deep analysis", "extra": {"subscribers": 3800, "open_rate": 56}},
            {"title": f"[Substack] {query} opinion piece", "extra": {"subscribers": 1800, "open_rate": 42}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://substack.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "substack-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
