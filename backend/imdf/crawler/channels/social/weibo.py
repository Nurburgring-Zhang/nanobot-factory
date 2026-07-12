"""Weibo public mobile search crawler channel."""
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


class WeiboChannel(SocialCrawlerBase):
    """Search Weibo mobile public pages (m.weibo.cn) for metadata snippets."""

    channel = "weibo"
    base_url = "https://m.weibo.cn"
    search_endpoint = "https://m.weibo.cn/search"

    def _build_url(self, query: str) -> str:
        container = f"100103type=1&q={query}"
        return f"{self.search_endpoint}?{urllib.parse.urlencode({'containerid': container})}"

    async def search(self, query: str, max_results: int = 20) -> list[CrawlResult]:
        request = SocialSearchInput(query=query, max_results=max_results)
        html = await self._request(self._build_url(request.query))
        if not html:
            return []
        return self.parse(html)[: request.max_results]

    @staticmethod
    def parse(html: str) -> list[CrawlResult]:
        soup = BeautifulSoup(html or "", "html.parser")
        cards = soup.select("[data-card-type], .card, .m-panel, article, .weibo-item")
        if not cards:
            cards = soup.select("a[href]")

        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, ["a[href]"], ["href"])
            if not url and getattr(card, "name", "") == "a":
                url = str(card.get("href") or "")
            url = safe_url(url, WeiboChannel.base_url)
            title = first_text(
                card,
                [".weibo-text", ".m-text-box", ".card-title", ".txt", "h3", "a"],
            )
            description = first_text(card, [".weibo-text", ".desc", ".sub-text", "p"])
            author = first_text(card, [".m-text-cut", ".name", ".author", ".user-name"])
            thumb = first_attr(card, ["img"], ["src", "data-src"])
            result = build_crawl_result(
                source=WeiboChannel.channel,
                url=url,
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, WeiboChannel.base_url) if thumb else "",
                extra={"host": "m.weibo.cn"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["WeiboChannel"]
