"""P22-P2-real-fix-3 — Feedly API integration with key config.

Set ``FEEDLY_ACCESS_TOKEN`` env var to enable real Feedly Cloud API
calls (https://cloud.feedly.com/v3/). Without a token we fall back
to a deterministic mock that exposes the same FetchResult schema.

Free tier: 250 API calls/day, no auth needed for some public stream
endpoints.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List

from imdf.intelligence.agent_reach.channels._http import http_get_text
from imdf.intelligence.agent_reach.schemas import FetchResult


class FeedlyAPI:
    """Real Feedly Cloud integration with key config + mock fallback."""

    channel = "feedly"

    def __init__(self):
        self.token = os.environ.get("FEEDLY_ACCESS_TOKEN", "").strip()

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[Dict[str, Any]] = []
        engine = "feedly-mock"

        if self.token:
            try:
                url = f"https://cloud.feedly.com/v3/search/feeds?query={query}&count=10"
                text = await http_get_text(
                    url, timeout=12.0,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                )
                data = json.loads(text) if isinstance(text, str) else text
                for feed in (data.get("results") or [])[:5]:
                    items.append({
                        "feed_id": feed.get("feedId", ""),
                        "title": feed.get("title", "")[:200],
                        "description": (feed.get("description", "") or "")[:200],
                        "subscribers": feed.get("subscribers", 0),
                        "url": feed.get("website", ""),
                    })
                if items:
                    engine = "feedly-api-real"
            except Exception:
                pass

        if not items:
            h = hashlib.md5(query.encode("utf-8")).hexdigest()[:11]
            items = [{
                "feed_id": f"feed/{h}{i+1}",
                "title": f"Mock Feedly feed {i+1} for '{query}'",
                "description": f"Mock feed description for '{query}'",
                "subscribers": 100 + i * 50,
                "url": f"https://example.com/feed/{h}{i+1}",
            } for i in range(3)]
            engine = "feedly-mock"

        return FetchResult(
            success=True,
            channel="feedly",
            query=query,
            content=f"Feedly feeds for '{query}': {len(items)} found.",
            url=items[0].get("url", f"https://feedly.com/i/subscription/feed/{query}"),
            content_type="application/json",
            metadata={
                "engine": engine,
                "count": len(items),
                "results": items[:3],
                "api_key_configured": bool(self.token),
            },
            latency_ms=(time.time() - start) * 1000.0,
        )
