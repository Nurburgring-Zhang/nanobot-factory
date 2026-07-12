"""RSSHub (rsshub.app) channel adapter (P20-F RSS).

RSSHub is a public RSS aggregator with hundreds of routes.
We expose the universal search endpoint:
    https://rsshub.app/search/{query}
which returns a JSON list of matching RSS sources.

For per-feed requests, RSSHub also exposes:
    https://rsshub.app/{route}
returning Atom XML. We parse the Atom <entry> elements into
CrawledItemModel entries.

公开无需 key, 但默认走 1 RPS 限速 + UA 池防止被临时封 IP.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup

from . import BaseCrawlerChannel
from .._schemas import CrawledItemModel

logger = logging.getLogger(__name__)


# 公开 RSSHub 端点 — 用户可自建镜像; 默认走官方
_SEARCH_ENDPOINT = "https://rsshub.app/search/{query}"
_FEED_ENDPOINT = "https://rsshub.app/{route}"


class RsshubChannel(BaseCrawlerChannel):
    """RSSHub — 公开 RSS 聚合.

    Usage:
        cw = RsshubChannel()
        items = await cw.search("machine learning", max_results=20)

    search() 调用 /search/{query} (JSON), 然后选第一条 feed route
    去拉 Atom XML, 最后 parse() 提取 <entry> 元素.
    """

    channel = "rsshub"
    api_endpoint = _SEARCH_ENDPOINT
    rate_limit_seconds = 1.0
    timeout_seconds = 15.0

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawledItemModel]:
        if not query or not query.strip():
            return []
        encoded = urllib.parse.quote(query.strip())
        # 第一步: 拿搜索 JSON
        search_url = _SEARCH_ENDPOINT.format(query=encoded)
        raw = await self._fetch(search_url, headers={"Accept": "application/json"})
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("%s invalid JSON from %s", self.channel, search_url)
            return []
        routes = self._extract_routes(payload)
        if not routes:
            return []
        # 第二步: 用第一条 route 去拉 feed
        first_route = routes[0]
        feed_url = _FEED_ENDPOINT.format(route=first_route)
        feed_raw = await self._fetch(feed_url, headers={"Accept": "application/atom+xml"})
        if not feed_raw:
            return []
        items = self.parse(feed_raw)
        return items[:max_results]

    @staticmethod
    def parse(raw: str) -> List[CrawledItemModel]:
        """Atom XML → list[CrawledItemModel]. Empty / malformed → []."""
        if not raw or not raw.strip():
            return []
        try:
            soup = BeautifulSoup(raw, "xml")
        except Exception:
            soup = BeautifulSoup(raw, "html.parser")
        entries = soup.find_all("entry")
        if not entries:
            # 退而求其次 — RSS <item>
            entries = soup.find_all("item")
        results: List[CrawledItemModel] = []
        for entry in entries:
            try:
                title = (entry.title.get_text(strip=True) if entry.title else "") or ""
                link_el = entry.find("link")
                url = ""
                if link_el is not None:
                    url = link_el.get("href") or link_el.get_text(strip=True) or ""
                if not url:
                    guid_el = entry.find("guid") or entry.find("id")
                    if guid_el is not None:
                        url = guid_el.get_text(strip=True)
                summary_el = entry.find("summary") or entry.find("content") or entry.find("description")
                description = summary_el.get_text(" ", strip=True) if summary_el else ""
                author_el = entry.find("author") or entry.find("dc:creator")
                author = author_el.get_text(strip=True) if author_el else ""
                updated_el = entry.find("updated") or entry.find("pubDate") or entry.find("published")
                updated: datetime | None = None
                if updated_el is not None:
                    try:
                        from email.utils import parsedate_to_datetime
                        updated = parsedate_to_datetime(updated_el.get_text(strip=True))
                    except Exception:
                        updated = None
                if not url:
                    continue
                item = CrawledItemModel(
                    id=f"rsshub_{url[:80]}",
                    url=url,
                    title=title[:500],
                    description=description[:2000],
                    source="rsshub",
                    author=author[:200],
                    keywords=[],
                    created_at=updated or datetime.utcnow(),
                    thumbnail_url="",
                    extra={"platform": "rsshub", "host": "rsshub.app"},
                )
                results.append(item)
            except Exception as exc:
                logger.debug("rsshub entry parse error: %s", exc)
                continue
        return results

    @staticmethod
    def _extract_routes(payload: object) -> List[str]:
        """从 /search JSON 提取候选 route 路径."""
        # 形状 1: list[str]
        if isinstance(payload, list):
            return [str(x) for x in payload if isinstance(x, str) and x.strip()][:1]
        # 形状 2: {"data": [...]}
        if isinstance(payload, dict):
            data = payload.get("data") or payload.get("routes") or payload.get("results")
            if isinstance(data, list):
                routes: List[str] = []
                for entry in data:
                    if isinstance(entry, str):
                        routes.append(entry)
                    elif isinstance(entry, dict):
                        route = entry.get("route") or entry.get("path") or entry.get("url")
                        if isinstance(route, str) and route.strip():
                            routes.append(route)
                return routes[:1]
        return []


__all__ = ["RsshubChannel"]