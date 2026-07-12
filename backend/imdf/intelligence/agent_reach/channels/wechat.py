"""V5 第32章 — WeChat channel: WeChatMCP (mock — deterministic article snippet)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class WeChatMCP:
    """Mock WeChat MCP — 1 deterministic 公众号 article per query."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:8]
        return FetchResult(
            success=True,
            channel="wechat",
            query=query,
            content=f"Mock 公众号文章 snippet for '{query}'",
            url=f"https://mp.weixin.qq.com/s/mock_{h}",
            content_type="application/json",
            metadata={
                "engine": "wechat-mcp-mock",
                "article_id": f"wx_{h}",
                "account": f"mock_account_{h[:6]}",
                "title": f"Mock 公众号 — {query}",
                "is_mock": True,
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["WeChatMCP"]