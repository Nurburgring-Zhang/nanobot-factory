"""Unsplash 渠道适配器

Unsplash API:
    GET https://api.unsplash.com/search/photos?query=...
    Header: Authorization: Client-ID <ACCESS_KEY>

需要 Access Key. 无 key 时 mock.

文档: https://unsplash.com/documentation
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import ChannelCrawler, placeholder_image_item
from ..base import CrawledItem
from ..config import CrawlerConfig

logger = logging.getLogger(__name__)


class UnsplashCrawler(ChannelCrawler):
    """Unsplash 图片搜索 — REST API 或 mock"""

    channel = "unsplash"
    api_endpoint = "https://api.unsplash.com/search/photos"
    requires_key = True
    key_env_var = "UNSPLASH_ACCESS_KEY"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 api_key: Optional[str] = None, mock: bool = False,
                 http_fetcher: Optional[Any] = None):
        super().__init__(config=config, api_key=api_key, mock=mock)
        self._http_fetcher = http_fetcher

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if isinstance(target, str):
            target = {"query": target}
        if not isinstance(target, dict):
            return None
        query = target.get("query") or target.get("q")
        if not query:
            return None
        return {
            "url": self.api_endpoint,
            "query": query,
            "count": min(int(target.get("count", 20)), 50),
            "page": int(target.get("page", 1)),
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep)).encode("utf-8"), 200, None
        # Unsplash 用 Authorization: Client-ID header
        if self.api_key:
            headers["Authorization"] = f"Client-ID {self.api_key}"
        sep = "&" if "?" in url else "?"
        params = {"query": prep["query"], "per_page": prep["count"], "page": prep["page"]}
        full_url = url + sep + urllib.parse.urlencode(params)
        try:
            fetcher = self._http_fetcher or self._default_fetcher
            content, status, err = fetcher(full_url, headers, self.config.timeout_seconds)
            return content, status, err
        except Exception as e:
            return b"", 0, str(e)

    def _default_fetcher(self, url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e:
            return b"", 0, str(e)

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            obj = json.loads(text)
        except Exception as e:
            return [], {"error": str(e), "mock": self.mock}

        results = obj.get("results", [])
        items: List[Dict[str, Any]] = []
        for idx, p in enumerate(results):
            crawled = self._build_item_unsplash(p, prep, idx)
            items.append(crawled.to_dict())

        meta = {
            "query": prep["query"],
            "total": obj.get("total", 0),
            "total_pages": obj.get("total_pages", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _build_item_unsplash(self, p: Dict[str, Any], prep: Dict[str, Any],
                             idx: int) -> CrawledItem:
        """Unsplash 特定字段映射到 10 字段 (P19-C1-fix P0 #2)"""
        urls = p.get("urls", {})
        user = p.get("user", {})
        return CrawledItem(
            id=str(p.get("id", f"unsplash_{idx}")),
            url=urls.get("regular", urls.get("full", "")),
            title=p.get("alt_description") or p.get("description") or "",
            description=p.get("description", ""),
            source=self.channel,
            author=user.get("name", ""),
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=urls.get("thumb", urls.get("small", "")),
            extra={
                "width": p.get("width", 0),
                "height": p.get("height", 0),
                "color": p.get("color", ""),
                "license": "unsplash-license",
                "author_url": user.get("links", {}).get("html", ""),
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_unsplash(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "total": count * 100,
            "total_pages": 5,
            "results": [
                {
                    "id": f"unsplash_mock_{prep['query']}_{i:04d}",
                    "description": f"Mock Unsplash result {i+1}",
                    "alt_description": f"{prep['query']} image {i+1}",
                    "width": 1920,
                    "height": 1080,
                    "color": "#abcdef",
                    "urls": {
                        "raw": f"https://example.com/raw_{i}.jpg",
                        "full": f"https://example.com/full_{i}.jpg",
                        "regular": f"https://example.com/regular_{i}.jpg",
                        "small": f"https://example.com/small_{i}.jpg",
                        "thumb": f"https://example.com/thumb_{i}.jpg",
                    },
                    "user": {
                        "name": f"Photographer {i+1}",
                        "links": {"html": f"https://unsplash.com/@user{i}"},
                    },
                }
                for i in range(count)
            ],
        }