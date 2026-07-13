"""V5 P2 channel — Reddit: social news / discussion.

Real integration via Reddit's public JSON endpoints (no key required,
no auth). Endpoints used:
  - https://www.reddit.com/r/{subreddit}/new.json?limit=N
  - https://www.reddit.com/r/{subreddit}/top.json?t=day&limit=N
  - https://www.reddit.com/r/{subreddit}/search.json?q=foo&restrict_sr=1

The JSON shape is documented at https://reddit.com/dev/api — but in
practice every result has ``data.children[*].data.{title,url,score,
num_comments,subreddit,created_utc,permalink}``.

Falls back to deterministic mock when network is unavailable.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from typing import Any, List

from imdf.intelligence.agent_reach.channels._http import http_get_json
from imdf.intelligence.agent_reach.schemas import FetchResult


class RedditAPI:
    channel = "reddit"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        subreddit = (kwargs.get("subreddit") or "").strip() or "all"
        sort = (kwargs.get("sort") or "top").strip()  # top | new | hot | rising
        limit = int(kwargs.get("limit", 10))
        items: List[dict] = []
        source = "mock"

        # Build URL
        if query and query.startswith("r/"):
            subreddit = query[2:].split(" ")[0]
            sort = "new"
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
        elif query and "/" in query:
            # Treat as subreddit
            subreddit = query.split(" ")[0].replace("r/", "")
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
        elif query:
            # Global search
            url = f"https://www.reddit.com/search.json?q={query}&limit={limit}"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"

        try:
            data = await http_get_json(url, headers={"User-Agent": "nanobot-factory/2.0 (research)"})
            children = (data.get("data") or {}).get("children") or []
            for child in children[:limit]:
                d = child.get("data") or {}
                items.append({
                    "id": d.get("id", ""),
                    "title": d.get("title", ""),
                    "url": d.get("url_overridden_by_dest") or d.get("url", ""),
                    "permalink": "https://reddit.com" + d.get("permalink", ""),
                    "subreddit": d.get("subreddit", ""),
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "author": d.get("author", "[deleted]"),
                    "created_utc": d.get("created_utc", 0),
                })
            source = "reddit-json"
        except Exception:
            items = self._mock_items(query, subreddit, sort, limit)
            source = "mock-fallback"

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query or subreddit,
            content="\n".join(f"[r/{it.get('subreddit', '')}] {it.get('title', '')}" for it in items),
            url=url,
            content_type="application/json",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )

    @staticmethod
    def _mock_items(query: str, subreddit: str, sort: str, limit: int) -> List[dict]:
        h = hashlib.md5(f"{query}|{subreddit}|{sort}".encode("utf-8")).hexdigest()[:6]
        return [
            {
                "id": f"mock_{h}{i:02d}",
                "title": f"[Mock Reddit] r/{subreddit} {sort} #{i}: {query or 'top'}",
                "url": f"https://reddit.com/r/{subreddit}/comments/mock_{h}{i:02d}",
                "permalink": f"https://reddit.com/r/{subreddit}/comments/mock_{h}{i:02d}",
                "subreddit": subreddit,
                "score": 200 * (i + 1),
                "comments": 30 * (i + 1),
                "author": "mock-user",
                "created_utc": int(time.time()) - i * 1800,
            }
            for i in range(min(3, limit))
        ]
