"""Xiaohongshu public note-search crawler channel."""
from __future__ import annotations

import urllib.parse

from bs4 import BeautifulSoup

from ._base import (
    CrawlResult,
    SocialCrawlerBase,
    SocialSearchInput,
    build_crawl_result,
    first_attr,
    first_text,
    safe_url,
)


class XiaohongshuChannel(SocialCrawlerBase):
    """Search Xiaohongshu web note metadata from public search pages."""

    channel = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com"
    search_endpoint = "https://www.xiaohongshu.com/search_result"

    def _build_url(self, query: str) -> str:
        params = {"keyword": query, "source": "web_explore_feed"}
        return f"{self.search_endpoint}?{urllib.parse.urlencode(params)}"

    async def search(self, query: str, max_results: int = 20) -> list[CrawlResult]:
        request = SocialSearchInput(query=query, max_results=max_results)
        html = await self._request(self._build_url(request.query))
        if not html:
            return []
        return self.parse(html)[: request.max_results]

    @staticmethod
    def parse(html: str) -> list[CrawlResult]:
        soup = BeautifulSoup(html or "", "html.parser")
        cards = soup.select(".note-item, .feeds-page .note-card, .explore-feed, article, section")
        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, ["a[href]"], ["href"])
            title = first_text(card, [".title", ".note-title", ".desc", "h3", "a"])
            description = first_text(card, [".desc", ".content", ".note-content", "p"])
            author = first_text(card, [".author", ".name", ".user", ".nickname"])
            thumb = first_attr(card, ["img"], ["src", "data-src"])
            if not url and not title:
                continue
            result = build_crawl_result(
                source=XiaohongshuChannel.channel,
                url=safe_url(url, XiaohongshuChannel.base_url),
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, XiaohongshuChannel.base_url) if thumb else "",
                extra={"host": "www.xiaohongshu.com", "type": "note"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["XiaohongshuChannel"]
