"""Reddit (old.reddit.com) channel adapter (P20-F RSS).

Reddit exposes a public JSON endpoint at:
    https://old.reddit.com/search.json?q={query}&restrict_sr=&sort=relevance&t=all

We parse the ``data.children[*].data`` entries into CrawledItemModel.

Notes:
    - User-Agent 必须是唯一标识的浏览器 (Reddit 强校验); 否则 429.
    - 公开端点无 key, 但需要合理 UA + 1 RPS.
    - 不用 oauth, 走匿名 read-only endpoint.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from typing import List

from . import BaseCrawlerChannel
from .._schemas import CrawledItemModel

logger = logging.getLogger(__name__)


_SEARCH_ENDPOINT = "https://old.reddit.com/search.json"
_SUBREDDIT_ENDPOINT = "https://old.reddit.com/r/{sub}.json"


class RedditChannel(BaseCrawlerChannel):
    """Reddit — 公开 JSON 搜索端点.

    Usage:
        cw = RedditChannel()
        items = await cw.search("open source AI", max_results=20)

    Implements async ``search(query, max_results)`` returning a list of
    CrawledItemModel from the public search-results JSON feed.
    """

    channel = "reddit"
    api_endpoint = _SEARCH_ENDPOINT
    rate_limit_seconds = 1.0
    timeout_seconds = 15.0

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawledItemModel]:
        if not query or not query.strip():
            return []
        params = {
            "q": query.strip(),
            "restrict_sr": "",
            "sort": "relevance",
            "t": "all",
            "limit": str(min(max_results, 100)),
        }
        url = f"{_SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
        # Reddit 强校验 UA — 用浏览器 UA + Accept: application/json
        raw = await self._fetch(
            url,
            headers={"Accept": "application/json"},
        )
        if not raw:
            return []
        items = self.parse(raw)
        return items[:max_results]

    @staticmethod
    def parse(raw: str) -> List[CrawledItemModel]:
        """Parse Reddit search-results JSON → list[CrawledItemModel]."""
        if not raw or not raw.strip():
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("reddit invalid JSON payload")
            return []
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        children = data.get("children") or []
        if not isinstance(children, list):
            return []
        results: List[CrawledItemModel] = []
        for entry in children:
            if not isinstance(entry, dict):
                continue
            inner = entry.get("data")
            if not isinstance(inner, dict):
                continue
            url = inner.get("url_overridden_by_dest") or inner.get("url") or ""
            if not url:
                # 自身 post — 用 reddit 评论页
                permalink = inner.get("permalink") or ""
                if permalink:
                    url = f"https://old.reddit.com{permalink}"
            if not url:
                continue
            title = inner.get("title") or ""
            selftext = inner.get("selftext") or ""
            subreddit = inner.get("subreddit") or ""
            author = inner.get("author") or ""
            thumb = inner.get("thumbnail") or ""
            if thumb and not thumb.startswith("http"):
                thumb = ""
            created_utc = inner.get("created_utc")
            created_at: datetime | None = None
            if isinstance(created_utc, (int, float)):
                try:
                    created_at = datetime.utcfromtimestamp(created_utc)
                except Exception:
                    created_at = None
            try:
                item = CrawledItemModel(
                    id=f"reddit_{inner.get('id', url[:60])}",
                    url=url,
                    title=title[:500],
                    description=selftext[:2000],
                    source="reddit",
                    author=author[:200],
                    keywords=[subreddit] if subreddit else [],
                    created_at=created_at or datetime.utcnow(),
                    thumbnail_url=thumb[:2000] if thumb else "",
                    extra={
                        "platform": "reddit",
                        "host": "old.reddit.com",
                        "subreddit": subreddit,
                        "score": inner.get("score"),
                        "num_comments": inner.get("num_comments"),
                        "permalink": f"https://old.reddit.com{inner.get('permalink', '')}",
                    },
                )
                results.append(item)
            except Exception as exc:
                logger.debug("reddit entry parse error: %s", exc)
                continue
        return results


__all__ = ["RedditChannel"]