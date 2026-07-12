"""V5 P2 channel — Pocket: read-later.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Pocket API, override `fetch()` with a httpx call
to Pocket's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class PocketAPI:
    channel = "pocket"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[Pocket Save] {query} - long read", "extra": {"read_time_min": 2400, "tags_count": 89}},
            {"title": f"[Pocket Save] {query} - tutorial", "extra": {"read_time_min": 1800, "tags_count": 56}},
            {"title": f"[Pocket Save] {query} - reference", "extra": {"read_time_min": 1200, "tags_count": 34}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://pocket.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "pocket-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
