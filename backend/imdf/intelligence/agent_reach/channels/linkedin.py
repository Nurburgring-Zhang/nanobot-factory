"""V5 第32章 — LinkedIn channel: LinkedInMCP (mock — deterministic profile stub)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class LinkedInMCP:
    """Mock LinkedIn MCP — 1 deterministic profile per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        return FetchResult(
            success=True,
            channel="linkedin",
            query=query,
            content=f"Mock LinkedIn profile snippet for '{query}'",
            url=f"https://linkedin.com/in/mock-user-{h}",
            content_type="application/json",
            metadata={
                "engine": "linkedin-mcp-mock",
                "profile_id": f"li_{h}",
                "name": f"Mock User {h[:4].upper()}",
                "headline": f"Engineer @ MockCorp (specialist in {query})",
                "is_mock": True,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["LinkedInMCP"]