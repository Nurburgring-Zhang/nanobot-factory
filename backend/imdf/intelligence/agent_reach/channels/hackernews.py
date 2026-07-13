"""V5 P2 channel — Hacker News: tech news.

Real integration via Algolia HN Search API (no key required) plus the
public Firebase HN API. Both return JSON that maps cleanly to our
FetchResult. Falls back to the deterministic mock when network is
unavailable (offline / CI / sandboxed).
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any, List, Optional

from imdf.intelligence.agent_reach.channels._http import http_get_json
from imdf.intelligence.agent_reach.schemas import FetchResult

# Public HN APIs (both no key):
# - Algolia HN Search: https://hn.algolia.com/api/v1/search?query=foo
# - Firebase HN API:   https://hacker-news.firebaseio.com/v0/topstories.json
HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
HN_FIREBASE_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_FIREBASE_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


class HackernewsAPI:
    channel = "hackernews"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[dict] = []
        source = "mock"
        try:
            # Use Algolia for query-driven search, Firebase for top stories.
            if query:
                url = f"{HN_ALGOLIA_URL}?query={query}&hitsPerPage=10"
                data = await http_get_json(url)
                for hit in data.get("hits", [])[:10]:
                    items.append({
                        "id": str(hit.get("objectID", "")),
                        "title": hit.get("title") or "(untitled)",
                        "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                        "points": hit.get("points", 0),
                        "comments": hit.get("num_comments", 0),
                        "author": hit.get("author", ""),
                        "created_at": hit.get("created_at_i", 0),
                    })
                source = "hn-algolia"
            else:
                # No query: return top stories
                top_ids = await http_get_json(HN_FIREBASE_TOP)
                # Fetch first 10 items in parallel
                item_data = await asyncio.gather(
                    *(http_get_json(HN_FIREBASE_ITEM.format(id=i)) for i in (top_ids or [])[:10]),
                    return_exceptions=True,
                )
                for d in item_data:
                    if isinstance(d, Exception) or not isinstance(d, dict):
                        continue
                    items.append({
                        "id": str(d.get("id", "")),
                        "title": d.get("title") or "(untitled)",
                        "url": d.get("url") or f"https://news.ycombinator.com/item?id={d.get('id')}",
                        "points": d.get("score", 0),
                        "comments": d.get("descendants", 0),
                        "author": d.get("by", ""),
                        "created_at": d.get("time", 0),
                    })
                source = "hn-firebase"
        except Exception:
            # Network down — fall back to mock data so the caller still
            # gets a useful response rather than a hard error.
            items = self._mock_items(query)
            source = "mock-fallback"

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"[{it.get('points', 0)}↑] {it.get('title', '')}" for it in items),
            url=f"https://hn.algolia.com/?q={query}" if query else "https://news.ycombinator.com/",
            content_type="application/json",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )

    @staticmethod
    def _mock_items(query: str) -> List[dict]:
        """Deterministic mock for offline mode (CI / no network)."""
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6] if query else "000000"
        kinds = ["show_hn", "ask_hn", "story"]
        items = []
        for i in range(3):
            items.append({
                "id": f"{h}{i:02d}",
                "title": f"[Mock HN] {'/'.join(kinds)} #{i}: {query or 'top stories'}",
                "url": f"https://news.ycombinator.com/item?id={h}{i:02d}",
                "points": 100 * (i + 1),
                "comments": 20 * (i + 1),
                "author": "mock-author",
                "created_at": int(time.time()) - i * 3600,
                "_kind": kinds[i],
            })
        return items
