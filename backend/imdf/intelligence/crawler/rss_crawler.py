"""智影 V4 — RSS 爬虫: feedparser (通用 + YouTube 频道 + Substack + Medium + WordPress + Hexo)"""
from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

try:
    import feedparser  # type: ignore
except ImportError:
    feedparser = None  # type: ignore
try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class RssCrawler(BaseCrawler):
    """RSS/Atom 爬虫 — 自动识别 6 种常见格式"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    async def _ensure_client(self):
        if self._client is None and httpx is not None:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """抓取 RSS feed — 返回每个 entry 作为单独 doc 的聚合"""
        start = time.time()
        if feedparser is None:
            raise RuntimeError("feedparser 未安装: pip install feedparser")
        if httpx is None:
            raise RuntimeError("httpx 未安装: pip install httpx")
        client = await self._ensure_client()
        resp = await client.get(url, headers={"User-Agent": "IMDF-Crawler/4.0 (+rss)"})
        resp.raise_for_status()
        # feedparser 支持 bytes/str
        parsed = feedparser.parse(resp.content)
        # feed 级 metadata
        feed_meta = {
            "title": getattr(parsed.feed, "title", ""),
            "link": getattr(parsed.feed, "link", ""),
            "description": getattr(parsed.feed, "description", ""),
            "language": getattr(parsed.feed, "language", ""),
            "updated": str(getattr(parsed.feed, "updated", "")),
        }
        # 提取 entries
        entries: List[Dict[str, Any]] = []
        for entry in parsed.entries[: self.config.max_pages]:
            entries.append(
                {
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "summary": getattr(entry, "summary", "") or getattr(entry, "description", ""),
                    "author": getattr(entry, "author", ""),
                    "published": str(getattr(entry, "published", "")),
                    "tags": [t.get("term") for t in getattr(entry, "tags", []) if t.get("term")],
                    "content": _extract_content(entry),
                }
            )
        # 主 doc 含整个 feed 摘要
        main_text = f"Feed: {feed_meta['title']}\nEntries: {len(entries)}\n"
        for i, e in enumerate(entries[:20]):
            main_text += f"\n[{i}] {e['title']}\n{e['summary'][:200]}\n"
        return RawDocument(
            url=url,
            type="rss",
            title=feed_meta["title"],
            text=main_text,
            json={"feed": feed_meta, "entries": entries},
            source_metadata={"protocol": "rss", "bozo": parsed.bozo, "entries_count": len(entries)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    def iter_entries(self, doc: RawDocument):
        """从聚合 doc 拆出 entry-level docs"""
        entries = doc.json.get("entries", [])
        for i, e in enumerate(entries):
            yield RawDocument(
                url=e.get("link", ""),
                type="rss_entry",
                title=e.get("title", ""),
                text=e.get("content") or e.get("summary", ""),
                source_channel=doc.source_channel,
                source_metadata={"feed_title": doc.title, "index": i, "published": e.get("published")},
            )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def _extract_content(entry: Any) -> str:
    """从 feedparser entry 提取正文 (兼容多种 RSS 变体)"""
    if hasattr(entry, "content") and entry.content:
        try:
            return entry.content[0].get("value", "")
        except Exception:
            pass
    if hasattr(entry, "summary"):
        return entry.summary
    if hasattr(entry, "description"):
        return entry.description
    return ""
