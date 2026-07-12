"""NewsAPI (newsapi.org) channel adapter (P20-F RSS).

NewsAPI exposes a /v2/everything endpoint that requires an API key for full
access, but a public HEAD / GET to ``https://newsapi.org/`` returns a JSON
manifest of public categories. We treat the search query as a category filter
and emit a synthetic crawl result pointing to the public search-page URL:

    https://newsapi.org/search?q={query}

When an API key is configured via env ``NEWSAPI_KEY``, the channel will
attempt the real ``/v2/everything`` endpoint. Without a key, it gracefully
returns metadata-only results linking to the public search page.

公开搜索端点 — 无 key 时返回 metadata-only 占位结果.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.parse
from datetime import datetime
from typing import List

from . import BaseCrawlerChannel
from .._schemas import CrawledItemModel

logger = logging.getLogger(__name__)


_PUBLIC_SEARCH = "https://newsapi.org/search"
_API_EVERYTHING = "https://newsapi.org/v2/everything"


class NewsApiChannel(BaseCrawlerChannel):
    """NewsAPI — 新闻聚合搜索.

    Without an API key, falls back to metadata-only results pointing to
    the public search page. With ``NEWSAPI_KEY`` env var, calls the real
    /v2/everything endpoint and parses articles.
    """

    channel = "newsapi"
    api_endpoint = _PUBLIC_SEARCH
    rate_limit_seconds = 1.0
    timeout_seconds = 15.0

    def __init__(self, *args, api_key: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._api_key = api_key or os.environ.get("NEWSAPI_KEY", "").strip()

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawledItemModel]:
        if not query or not query.strip():
            return []
        q = query.strip()
        if self._api_key:
            return await self._search_with_key(q, max_results)
        return self._search_public(q, max_results)

    async def _search_with_key(self, query: str, max_results: int) -> List[CrawledItemModel]:
        """Real /v2/everything API call (requires NEWSAPI_KEY)."""
        params = {"q": query, "pageSize": min(max_results, 100)}
        url = f"{_API_EVERYTHING}?{urllib.parse.urlencode(params)}"
        raw = await self._fetch(
            url,
            headers={"Accept": "application/json", "X-Api-Key": self._api_key},
        )
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("%s invalid JSON from %s", self.channel, url)
            return []
        return self.parse(raw)[:max_results]

    def _search_public(self, query: str, max_results: int) -> List[CrawledItemModel]:
        """Metadata-only fallback — synthesize a result pointing to the search page."""
        encoded = urllib.parse.quote(query)
        url = f"{_PUBLIC_SEARCH}?q={encoded}"
        digest = hashlib.sha256(f"newsapi|{query}".encode("utf-8")).hexdigest()[:16]
        item = CrawledItemModel(
            id=f"newsapi_{digest}",
            url=url,
            title=f"NewsAPI search: {query}",
            description=(
                f"Public search results for '{query}' at newsapi.org. "
                "Configure NEWSAPI_KEY env var for full article metadata."
            ),
            source="newsapi",
            author="newsapi.org",
            keywords=[query],
            created_at=datetime.utcnow(),
            thumbnail_url="",
            extra={
                "platform": "newsapi",
                "host": "newsapi.org",
                "mode": "public-fallback",
                "needs_api_key": True,
            },
        )
        # 在 metadata-only 模式下, max_results 只会 1 — 不是真有那么多结果
        return [item] * min(max(1, max_results), 1)

    @staticmethod
    def parse(raw: str) -> List[CrawledItemModel]:
        """Parse /v2/everything JSON response → list[CrawledItemModel]."""
        if not raw or not raw.strip():
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        articles = payload.get("articles") or []
        if not isinstance(articles, list):
            return []
        results: List[CrawledItemModel] = []
        for art in articles:
            if not isinstance(art, dict):
                continue
            url = art.get("url") or ""
            if not url:
                continue
            title = art.get("title") or ""
            description = art.get("description") or art.get("content") or ""
            author = art.get("author") or (art.get("source") or {}).get("name") or ""
            thumbnail = art.get("urlToImage") or ""
            published = art.get("publishedAt")
            created_at: datetime | None = None
            if isinstance(published, str):
                try:
                    created_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except Exception:
                    created_at = None
            try:
                item = CrawledItemModel(
                    id=f"newsapi_{url[:80]}",
                    url=url,
                    title=title[:500],
                    description=description[:2000],
                    source="newsapi",
                    author=author[:200],
                    keywords=[],
                    created_at=created_at or datetime.utcnow(),
                    thumbnail_url=thumbnail,
                    extra={
                        "platform": "newsapi",
                        "host": "newsapi.org",
                        "source_name": (art.get("source") or {}).get("name", ""),
                    },
                )
                results.append(item)
            except Exception as exc:
                logger.debug("newsapi article parse error: %s", exc)
                continue
        return results


__all__ = ["NewsApiChannel"]