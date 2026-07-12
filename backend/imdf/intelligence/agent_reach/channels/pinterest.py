"""V5 P2 channel — Pinterest: image bookmarking.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Pinterest API, override `fetch()` with a httpx call
to Pinterest's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class PinterestAPI:
    channel = "pinterest"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[{query} inspiration board 1]", "extra": {"width": 1024, "height": 768, "pins": 156}},
            {"title": f"[{query} DIY collection]", "extra": {"width": 800, "height": 600, "pins": 89}},
            {"title": f"[{query} aesthetic pins]", "extra": {"width": 1200, "height": 900, "pins": 245}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://pinterest.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "pinterest-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
