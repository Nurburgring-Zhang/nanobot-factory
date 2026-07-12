"""Douyin public video-search crawler channel."""
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


class DouyinChannel(SocialCrawlerBase):
    """Search Douyin web video results without API keys."""

    channel = "douyin"
    base_url = "https://www.douyin.com"

    def _build_url(self, query: str) -> str:
        encoded = urllib.parse.quote(query)
        return f"{self.base_url}/search/{encoded}?type=video"

    async def search(self, query: str, max_results: int = 20) -> list[CrawlResult]:
        request = SocialSearchInput(query=query, max_results=max_results)
        html = await self._request(self._build_url(request.query))
        if not html:
            return []
        return self.parse(html)[: request.max_results]

    @staticmethod
    def parse(html: str) -> list[CrawlResult]:
        soup = BeautifulSoup(html or "", "html.parser")
        cards = soup.select(
            "[data-e2e='search-video-item'], .search-result-card, .video-card, "
            ".douyin-search-result, article, li"
        )
        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, ["a[href]"], ["href"])
            title = first_text(card, ["[data-e2e='video-desc']", ".title", ".desc", "h3", "a"])
            description = first_text(card, [".desc", ".content", "p"])
            author = first_text(card, ["[data-e2e='video-author']", ".author", ".name", ".user-name"])
            thumb = first_attr(card, ["img", "picture img", "video"], ["src", "data-src", "poster"])
            if not url and not title:
                continue
            result = build_crawl_result(
                source=DouyinChannel.channel,
                url=safe_url(url, DouyinChannel.base_url),
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, DouyinChannel.base_url) if thumb else "",
                extra={"host": "www.douyin.com", "type": "video"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["DouyinChannel"]
