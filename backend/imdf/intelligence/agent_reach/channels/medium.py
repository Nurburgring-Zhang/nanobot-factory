"""V5 P2 channel — Medium: long-form publishing.

Real integration via Medium's public RSS feed (no key required). Each
publication exposes /feed at the root:
  https://medium.com/feed/@{username}
  https://{publication}.com/feed (publication subdomain)

When query starts with @, it's treated as a username. Otherwise the
query is used as a publication slug (medium.com/<slug>). Falls back to
deterministic mock when network is unavailable or the publication does
not exist.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, List

from imdf.intelligence.agent_reach.channels._http import http_get_text
from imdf.intelligence.agent_reach.schemas import FetchResult


def _parse_medium_rss(xml_text: str) -> List[dict]:
    """Parse Medium RSS XML into a list of stories.

    Robust against missing fields and namespace prefixes (atom + dc).
    Returns up to 10 stories.
    """
    out: List[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    # RSS 2.0 <channel>/<item>
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        author = (item.findtext("{http://purl.org/dc/elements/1.1/}creator") or item.findtext("author") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        # Description is HTML — strip tags crudely
        import re as _re
        desc = _re.sub(r"<[^>]+>", "", (item.findtext("description") or "").strip())
        if title:
            out.append({"title": title, "url": link, "author": author, "published": pub, "snippet": desc[:200]})
    return out[:10]


class MediumAPI:
    channel = "medium"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[dict] = []
        source = "mock"
        url = ""

        if query:
            slug = re.sub(r"[^a-z0-9_@-]", "", query.lower())
            slug = slug.lstrip("@")
            for feed_url in (
                f"https://medium.com/feed/@{slug}",
                f"https://{slug}.medium.com/feed",
            ):
                url = feed_url
                try:
                    text = await http_get_text(url, timeout=10.0)
                    parsed = _parse_medium_rss(text)
                    if parsed:
                        items = parsed
                        source = "medium-rss"
                        break
                except Exception:
                    continue
        if not items:
            items = self._mock_items(query)
            source = "mock-fallback"
            url = url or f"https://medium.com/feed/@{re.sub(r'[^a-z0-9_@-]', '', (query or 'example').lstrip('@').lower())}"

        return FetchResult(
            success=True,
            channel=self.channel,
            query=query,
            content="\n".join(f"[{it.get('author', '')}] {it.get('title', '')}" for it in items),
            url=url,
            content_type="application/xml",
            metadata={"engine": source, "count": len(items), "results": items},
            latency_ms=(time.time() - start) * 1000.0,
        )

    @staticmethod
    def _mock_items(query: str) -> List[dict]:
        h = hashlib.md5(query.encode("utf-8")).hexdigest()[:6]
        return [
            {
                "title": f"[Mock Medium] Story #{i}: {query or 'deep dive'}",
                "url": f"https://medium.com/@mock/mock-{h}{i:02d}",
                "author": "mock-writer",
                "published": "2026-01-0{i+1}",
                "snippet": f"Mock snippet for {query} #{i}",
            }
            for i in range(3)
        ]
