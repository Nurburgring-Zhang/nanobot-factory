"""Zhihu public search crawler channel."""
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


class ZhihuChannel(SocialCrawlerBase):
    """Search Zhihu public questions and answers from web search pages."""

    channel = "zhihu"
    base_url = "https://www.zhihu.com"
    search_endpoint = "https://www.zhihu.com/search"

    def _build_url(self, query: str) -> str:
        params = {"type": "content", "q": query}
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
        cards = soup.select(".List-item, .SearchResult-Card, .ContentItem, article, section")
        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, [".ContentItem-title a[href]", "h2 a[href]", "a[href]"], ["href"])
            title = first_text(card, [".ContentItem-title", ".Highlight", "h2", "h3", "a"])
            description = first_text(card, [".RichContent-inner", ".SearchResult-content", ".excerpt", "p"])
            author = first_text(card, [".AuthorInfo-name", ".UserLink-link", ".author", ".name"])
            thumb = first_attr(card, ["img"], ["src", "data-src"])
            if not url and not title:
                continue
            result = build_crawl_result(
                source=ZhihuChannel.channel,
                url=safe_url(url, ZhihuChannel.base_url),
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, ZhihuChannel.base_url) if thumb else "",
                extra={"host": "www.zhihu.com", "type": "qa"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["ZhihuChannel"]
