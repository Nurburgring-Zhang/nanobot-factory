"""V5 P2 channel — Instapaper: read-later.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Instapaper API, override `fetch()` with a httpx call
to Instapaper's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class InstapaperAPI:
    channel = "instapaper"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[Instapaper] {query} - article", "extra": {"word_count": 1800, "highlights": 67}},
            {"title": f"[Instapaper] {query} - essay", "extra": {"word_count": 2400, "highlights": 45}},
            {"title": f"[Instapaper] {query} - blog post", "extra": {"word_count": 1200, "highlights": 32}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://instapaper.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "instapaper-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
