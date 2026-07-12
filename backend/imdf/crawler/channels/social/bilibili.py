"""Bilibili public video-search crawler channel."""
from __future__ import annotations

import json
import urllib.parse

from bs4 import BeautifulSoup

from ._base import (
    CrawlResult,
    SocialCrawlerBase,
    SocialSearchInput,
    build_crawl_result,
    clean_text,
    first_attr,
    first_text,
    safe_url,
)


class BilibiliChannel(SocialCrawlerBase):
    """Search Bilibili public video metadata via the web-interface endpoint."""

    channel = "bilibili"
    base_url = "https://www.bilibili.com"
    search_endpoint = "https://api.bilibili.com/x/web-interface/search/type"

    def _build_url(self, query: str) -> str:
        params = {"search_type": "video", "keyword": query, "page": 1}
        return f"{self.search_endpoint}?{urllib.parse.urlencode(params)}"

    async def search(self, query: str, max_results: int = 20) -> list[CrawlResult]:
        request = SocialSearchInput(query=query, max_results=max_results)
        payload = await self._request(self._build_url(request.query))
        if not payload:
            return []
        return self.parse(payload)[: request.max_results]

    @staticmethod
    def parse(html: str) -> list[CrawlResult]:
        text = (html or "").strip()
        if text.startswith("{"):
            parsed = BilibiliChannel._parse_json(text)
            if parsed:
                return parsed
        return BilibiliChannel._parse_html(text)

    @staticmethod
    def _parse_json(text: str) -> list[CrawlResult]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        data = payload.get("data") if isinstance(payload, dict) else None
        records = data.get("result", []) if isinstance(data, dict) else []
        if not isinstance(records, list):
            return []
        results: list[CrawlResult] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            title = clean_text(raw.get("title") or raw.get("typename") or "")
            url = raw.get("arcurl") or raw.get("url") or ""
            if not url and raw.get("bvid"):
                url = f"https://www.bilibili.com/video/{raw['bvid']}"
            thumb = raw.get("pic") or raw.get("cover") or ""
            result = build_crawl_result(
                source=BilibiliChannel.channel,
                url=safe_url(url, BilibiliChannel.base_url),
                title=title,
                description=raw.get("description") or raw.get("desc") or "",
                author=raw.get("author") or raw.get("mid") or "",
                thumbnail_url=safe_url(thumb, BilibiliChannel.base_url) if thumb else "",
                extra={
                    "host": "api.bilibili.com",
                    "type": "video",
                    "play": raw.get("play"),
                    "danmaku": raw.get("danmaku"),
                },
            )
            results.append(result)
        return results

    @staticmethod
    def _parse_html(html: str) -> list[CrawlResult]:
        soup = BeautifulSoup(html or "", "html.parser")
        cards = soup.select(".bili-video-card, .video-item, .video-list li, article, li")
        results: list[CrawlResult] = []
        seen: set[str] = set()
        for card in cards:
            url = first_attr(card, ["a[href]"], ["href"])
            title = first_text(card, [".bili-video-card__info--tit", ".title", "h3", "a"])
            description = first_text(card, [".desc", ".description", "p"])
            author = first_text(card, [".bili-video-card__info--author", ".up-name", ".author"])
            thumb = first_attr(card, ["img"], ["src", "data-src"])
            if not url and not title:
                continue
            result = build_crawl_result(
                source=BilibiliChannel.channel,
                url=safe_url(url, BilibiliChannel.base_url),
                title=title,
                description=description,
                author=author,
                thumbnail_url=safe_url(thumb, BilibiliChannel.base_url) if thumb else "",
                extra={"host": "www.bilibili.com", "type": "video"},
            )
            if result.id not in seen:
                seen.add(result.id)
                results.append(result)
        return results


__all__ = ["BilibiliChannel"]
