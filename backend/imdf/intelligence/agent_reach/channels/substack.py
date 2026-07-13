"""V5 P2 channel — Substack: newsletters.

Real integration via Substack's public RSS feeds (no key required).
Every public Substack publication exposes /feed at the root:
  https://{publication}.substack.com/feed
  https://{publication}.substack.com/rss

When a query is given, we treat it as a publication slug and try both
the /feed and /rss endpoints. The feed is XML (RSS 2.0), parsed with
regex (no extra dep).

Falls back to deterministic mock when network is unavailable or the
publication does not exist.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, List, Optional

from imdf.intelligence.agent_reach.channels._http import http_get_text
from imdf.intelligence.agent_reach.schemas import FetchResult


def _parse_rss(xml_text: str) -> List[dict]:
    """Parse RSS 2.0 XML into a list of {title, url, author, published} dicts.

    Robust against minor XML variations (CDATA, missing fields, namespace
    prefixes). Returns up to 10 items.
    """
    out: List[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    channel = root.find("channel")
    if channel is None:
        return out
    for item in channel.findall("item")[:10]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        author = (item.findtext("author") or "").strip() or (item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        out.append({"title": title, "url": link, "author": author, "published": pub})
    return out


class SubstackAPI:
    channel = "substack"

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        start = time.time()
        items: List[dict] = []
        source = "mock"
        url = ""
        if query:
            pub = re.sub(r"[^a-z0-9_-]", "", query.lower())
            for path in ("/feed", "/rss"):
                url = f"https://{pub}.substack.com{path}"
                try:
                    text = await http_get_text(url, timeout=10.0)
                    parsed = _parse_rss(text)
                    if parsed:
                        items = parsed
                        source = "substack-rss"
                        break
                except Exception:
                    continue
        if not items:
            items = self._mock_items(query)
            source = "mock-fallback"
            url = f"https://{re.sub(r'[^a-z0-9_-]', '', (query or 'example').lower())}.substack.com/feed"

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
                "title": f"[Mock Substack] Issue #{i}: {query or 'weekly digest'}",
                "url": f"https://example.substack.com/p/mock_{h}{i:02d}",
                "author": "mock-author",
                "published": "Mon, 01 Jan 2026 00:00:00 GMT",
            }
            for i in range(3)
        ]
