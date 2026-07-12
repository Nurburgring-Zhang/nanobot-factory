"""Baidu Tieba public post-search crawler channel."""
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


class TiebaChannel(SocialCrawlerBase):
    """Search Baidu Tieba public threads from tieba.baidu.com."""

    channel = "tieba"
    base_url = "https://tieba.baidu.com"
    search_endpoint = "https://tieba.baidu.com/f/search/res"

    def _build_url(self, query: str) -> str:
        params = {"ie": "utf-8", "qw": query}
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
        cards = soup.select(".s_post, .j_thread_list, .threadlist_li, .search_item, li")
        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, [".p_title a[href]", ".threadlist_title a[href]", "a[href]"], ["href"])
            title = first_text(card, [".p_title", ".threadlist_title", ".title", "h3", "a"])
            description = first_text(card, [".p_content", ".threadlist_abs", ".abstract", "p"])
            author = first_text(card, [".p_violet", ".frs-author-name", ".author", ".name"])
            thumb = first_attr(card, ["img"], ["src", "data-src"])
            if not url and not title:
                continue
            result = build_crawl_result(
                source=TiebaChannel.channel,
                url=safe_url(url, TiebaChannel.base_url),
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, TiebaChannel.base_url) if thumb else "",
                extra={"host": "tieba.baidu.com", "type": "thread"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["TiebaChannel"]
