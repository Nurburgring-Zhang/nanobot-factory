"""V5 第32章 — Exa Search channel: ExaSearch (mock)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class ExaSearch:
    """Mock Exa semantic search — 3 deterministic results."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        results = [
            {
                "title": f"Exa result 1: Deep dive into {query}",
                "url": f"https://exa-mock-{h}.example.com/article/1",
                "score": 0.95,
                "snippet": f"This is a mock Exa result about {query} (top match)",
            },
            {
                "title": f"Exa result 2: {query} explained",
                "url": f"https://exa-mock-{h}.example.com/article/2",
                "score": 0.87,
                "snippet": f"Second mock Exa match for {query}",
            },
            {
                "title": f"Exa result 3: {query} in 2026",
                "url": f"https://exa-mock-{h}.example.com/article/3",
                "score": 0.81,
                "snippet": f"Third mock Exa result for {query}",
            },
        ]
        return FetchResult(
            success=True,
            channel="exa_search",
            query=query,
            content="\n".join(f"[{r['score']:.2f}] {r['title']}" for r in results),
            url=f"https://exa.ai/search?q={query}",
            content_type="application/json",
            metadata={
                "engine": "exa-mock",
                "count": len(results),
                "results": results,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["ExaSearch"]