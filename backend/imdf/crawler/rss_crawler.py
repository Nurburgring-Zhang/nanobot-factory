"""RSSCrawler — feedparser 驱动的 RSS/Atom 采集 (P19-B3 §5)

特性:
- feedparser 解析 RSS 0.9x / 2.0 / Atom 1.0 / RDF
- 增量: GUID 去重 (持久化到 state)
- metadata: title / author / published / tags
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .base import BaseCrawler, CrawlResult, CrawlStatus
from .config import CrawlerConfig

logger = logging.getLogger(__name__)


@dataclass
class RSSItem:
    """单条 RSS entry"""
    guid: str
    title: str
    link: str
    published: Optional[str] = None
    author: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    enclosures: List[Dict[str, str]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guid": self.guid,
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "author": self.author,
            "summary": (self.summary or "")[:500],
            "content": (self.content or "")[:1000],
            "tags": self.tags,
            "enclosures": self.enclosures,
        }


class RSSCrawler(BaseCrawler):
    """RSS / Atom feed 爬虫 — 用 feedparser

    使用:
        cw = RSSCrawler(config=CrawlerConfig(channel="rss"))
        result = cw.crawl("https://example.com/feed.xml")
        for item in result.items:
            print(item["title"], item["link"])
    """

    channel = "rss"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 feed_fetcher: Optional[Callable[[str], bytes]] = None,
                 state_dir: Optional[str] = None):
        super().__init__(config=config)
        # feed_fetcher: 测试用 mock
        self._feed_fetcher = feed_fetcher or self._default_feed_fetcher
        # 增量去重 state (持久化到 JSON)
        if state_dir is None:
            state_dir = os.environ.get(
                "CRAWLER_STATE_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
            )
        self._state_dir = state_dir
        os.makedirs(self._state_dir, exist_ok=True)
        self._seen_guids: Dict[str, Set[str]] = {}  # url -> set(guid)
        self._state_lock_file = os.path.join(self._state_dir, "rss_seen.json")

    # ============== _prepare ==============

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """target = str URL or dict {url, full_history: bool}"""
        if isinstance(target, str):
            target = {"url": target}
        if not isinstance(target, dict):
            return None
        url = target.get("url") or target.get("feed")
        if not url:
            return None
        return {
            "url": url,
            "full_history": bool(target.get("full_history", False)),
            "max_items": int(target.get("max_items", 100)),
        }

    # ============== _do_fetch ==============

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        """feed_fetcher -> raw bytes"""
        try:
            content = self._feed_fetcher(url)
            return content, 200, None
        except Exception as e:
            return b"", 0, str(e)

    def _default_feed_fetcher(self, url: str) -> bytes:
        """默认 urllib fetcher"""
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": self.config.get_user_agent(),
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
            return resp.read()

    # ============== _parse ==============

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """feedparser -> RSSItem list"""
        try:
            import feedparser  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"feedparser required: {e}")

        if isinstance(raw, bytes):
            content = raw.decode("utf-8", errors="replace")
        else:
            content = str(raw)

        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"feed parse error: {parsed.bozo_exception}")

        feed_meta = {
            "feed_title": parsed.feed.get("title", "") if parsed.feed else "",
            "feed_link": parsed.feed.get("link", "") if parsed.feed else "",
            "feed_subtitle": parsed.feed.get("subtitle", "") if parsed.feed else "",
            "total_entries": len(parsed.entries),
        }

        seen = self._load_seen(prep["url"])
        items: List[Dict[str, Any]] = []
        max_items = prep.get("max_items", 100)
        full_history = prep.get("full_history", False)

        for entry in parsed.entries[:max_items]:
            guid = self._make_guid(entry)
            item = RSSItem(
                guid=guid,
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published=self._format_date(entry),
                author=entry.get("author", ""),
                summary=entry.get("summary", ""),
                content="".join([c.value for c in entry.get("content", [])]) or entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "",
                tags=[t.get("term", "") for t in entry.get("tags", []) if t.get("term")],
                enclosures=[{"href": e.get("href", ""), "type": e.get("type", "")}
                             for e in entry.get("enclosures", [])],
                raw=dict(entry),
            )
            if not full_history and guid in seen:
                continue
            seen.add(guid)
            items.append(item.to_dict())

        # 持久化 seen state
        self._save_seen(prep["url"], seen)
        feed_meta["new_items"] = len(items)
        feed_meta["deduped"] = feed_meta["total_entries"] - len(items)
        return items, feed_meta

    def _make_guid(self, entry: Dict[str, Any]) -> str:
        """稳定 GUID: 优先 id, 否则 link, 否则 hash(title)"""
        if entry.get("id"):
            return str(entry["id"])
        if entry.get("link"):
            return str(entry["link"])
        if entry.get("title"):
            return "title:" + hashlib.sha256(entry["title"].encode("utf-8")).hexdigest()[:32]
        return "anon:" + hashlib.sha256(json.dumps(dict(entry), sort_keys=True).encode()).hexdigest()[:32]

    def _format_date(self, entry: Dict[str, Any]) -> Optional[str]:
        """尝试多种 published 字段, 标准化为 ISO"""
        for key in ("published", "updated", "created"):
            val = entry.get(key)
            if val:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(val)
                    return dt.isoformat()
                except Exception:
                    return str(val)
        return None

    # ============== 持久化 ==============

    def _load_seen(self, feed_url: str) -> Set[str]:
        if feed_url in self._seen_guids:
            return self._seen_guids[feed_url]
        seen: Set[str] = set()
        if os.path.exists(self._state_lock_file):
            try:
                with open(self._state_lock_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                seen = set(data.get(feed_url, []))
            except Exception as e:
                logger.debug("seen-state load failed: %s", e)
        self._seen_guids[feed_url] = seen
        return seen

    def _save_seen(self, feed_url: str, seen: Set[str]) -> None:
        """持久化 seen state — 限制最多 10000 条防爆"""
        seen_list = list(seen)[-10000:]
        existing: Dict[str, List[str]] = {}
        if os.path.exists(self._state_lock_file):
            try:
                with open(self._state_lock_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        existing[feed_url] = seen_list
        try:
            tmp = self._state_lock_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False)
            os.replace(tmp, self._state_lock_file)
        except Exception as e:
            logger.warning("seen-state save failed: %s", e)