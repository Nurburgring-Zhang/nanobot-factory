"""V5 P2 channel — Vimeo: video hosting.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Vimeo API, override `fetch()` with a httpx call
to Vimeo's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class VimeoAPI:
    channel = "vimeo"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[{query} - Official Trailer", "extra": {"duration_s": 240, "views": 1800, "rating": 4.7}},
            {"title": f"[{query} - Behind the Scenes", "extra": {"duration_s": 60, "views": 720, "rating": 4.5}},
            {"title": f"[{query} - Documentary Clip", "extra": {"duration_s": 180, "views": 2400, "rating": 4.8}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://vimeo.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "vimeo-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
