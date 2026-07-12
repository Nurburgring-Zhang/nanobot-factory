"""V5 P2 channel — Medium: long-form publishing.

Mock implementation following the same pattern as the existing 14 channels
in this directory (see reddit.py, exa_search.py). Returns deterministic
data derived from a hash of the query so tests are reproducible.

To switch to the real Medium API, override `fetch()` with a httpx call
to Medium's public endpoint and keep the same ``FetchResult`` shape.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, List

from imdf.intelligence.agent_reach.schemas import FetchResult


class MediumAPI:
    channel = "medium"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        items_data = [
            {"title": f"[Medium / @author] The truth about {query}", "extra": {"read_time_min": 4500, "claps": 234, "score": 8.2}},
            {"title": f"[Medium / @writer] Why {query} matters in 2026", "extra": {"read_time_min": 3200, "claps": 156, "score": 7.8}},
            {"title": f"[Medium / @expert] A deep dive into {query}", "extra": {"read_time_min": 5100, "claps": 312, "score": 9.1}},
        ]
        results = []
        for item in items_data:
            results.append({"title": item["title"].format(query=query), **item["extra"]})

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"{r['title']}" for r in results),
            url=f"https://medium.example.com/?q={query}",
            content_type="application/json",
            metadata={"engine": "medium-mock", "count": len(results), "results": results},
            latency_ms=(time.time() - start) * 1000.0,
        )
