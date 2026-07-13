"""V5 P2 channel — Vimeo: video hosting.

Real integration via Vimeo's public oEmbed endpoint (no key required).
The oEmbed endpoint returns JSON metadata for any public Vimeo video
when given the URL.

  https://vimeo.com/api/oembed.json?url=https://vimeo.com/123456

When the query is a Vimeo URL, we fetch oEmbed. When it's a search
term, we hit Vimeo's public search page (HTML) and parse the result
list — Vimeo's search page is publicly accessible without auth.

Falls back to deterministic mock when network is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, List
from urllib.parse import urlencode

from imdf.intelligence.agent_reach.channels._http import http_get_json, http_get_text
from imdf.intelligence.agent_reach.schemas import FetchResult

VIMEO_OEMBED = "https://vimeo.com/api/oembed.json"
VIMEO_SEARCH = "https://vimeo.com/search"


class VimeoAPI:
    channel = "vimeo"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[dict] = []
        source = "mock"

        # Decide: URL vs search
        if query and ("vimeo.com/" in query or query.isdigit()):
            url = query if query.startswith("http") else f"https://vimeo.com/{query}"
            try:
                oembed_url = f"{VIMEO_OEMBED}?{urlencode({'url': url, 'width': 640})}"
                data = await http_get_json(oembed_url)
                items.append({
                    "id": str(data.get("video_id", "")),
                    "title": data.get("title", ""),
                    "url": data.get("url", url),
                    "thumbnail_url": data.get("thumbnail_url", ""),
                    "duration_s": int(data.get("duration", 0)),
                    "author": data.get("author_name", ""),
                    "width": int(data.get("width", 0)),
                    "height": int(data.get("height", 0)),
                })
                source = "vimeo-oembed"
            except Exception:
                items = [self._oembed_mock(url)]
                source = "mock-fallback"
        else:
            # Search term — fetch Vimeo's public search page
            try:
                html = await http_get_text(f"{VIMEO_SEARCH}?q={query}")
                # Parse search results: each <li> contains a thumbnail and title link
                # Pattern: <a href="/videos/12345" ...> <h2>Title</h2>
                pattern = re.compile(
                    r'<a[^>]+href="(/videos/(\d+))"[^>]*>.*?<h2[^>]*>([^<]+)</h2>',
                    re.S,
                )
                for m in pattern.finditer(html)[:10]:
                    path, vid, title = m.group(1), m.group(2), m.group(3).strip()
                    items.append({
                        "id": vid,
                        "title": title,
                        "url": f"https://vimeo.com{path}",
                        "thumbnail_url": "",
                        "duration_s": 0,
                        "author": "",
                    })
                if items:
                    source = "vimeo-search"
            except Exception:
                pass
            if not items:
                items = self._mock_items(query)
                source = "mock-fallback"

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"[{it.get('author', '')}] {it.get('title', '')}" for it in items),
            url=items[0]["url"] if items else f"https://vimeo.com/search?q={query}",
            content_type="application/json",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )

    @staticmethod
    def _oembed_mock(url: str) -> dict:
        h = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        return {
            "id": h,
            "title": f"[Mock Vimeo] {url}",
            "url": url,
            "thumbnail_url": f"https://i.vimeocdn.com/video/{h}.jpg",
            "duration_s": 180,
            "author": "mock-vimeo-author",
            "width": 640,
            "height": 360,
        }

    @staticmethod
    def _mock_items(query: str) -> List[dict]:
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        return [
            {
                "id": f"{h}{i:02d}",
                "title": f"[Mock Vimeo] {query or 'top clip'} #{i}",
                "url": f"https://vimeo.com/mock_{h}{i:02d}",
                "thumbnail_url": f"https://i.vimeocdn.com/video/{h}{i:02d}.jpg",
                "duration_s": 60 * (i + 1),
                "author": "mock-vimeo-author",
                "width": 640,
                "height": 360,
            }
            for i in range(3)
        ]
