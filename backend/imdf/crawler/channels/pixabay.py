"""Pixabay 渠道适配器

Pixabay API:
    GET https://pixabay.com/api/?key=KEY&q=...

需要 API Key. 无 key 时 mock.

文档: https://pixabay.com/api/docs/
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


class PixabayCrawler(ChannelCrawler):
    """Pixabay 图片搜索 — REST API 或 mock"""

    channel = "pixabay"
    api_endpoint = "https://pixabay.com/api/"
    requires_key = True
    key_env_var = "PIXABAY_API_KEY"

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
            "count": min(int(target.get("count", 20)), 200),
            "page": int(target.get("page", 1)),
            "image_type": target.get("image_type", "photo"),
            "category": target.get("category"),
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep)).encode("utf-8"), 200, None
        params = {
            "key": self.api_key,
            "q": urllib.parse.quote_plus(prep["query"]),
            "per_page": prep["count"],
            "page": prep["page"],
            "image_type": prep["image_type"],
        }
        if prep.get("category"):
            params["category"] = prep["category"]
        sep = "&" if "?" in url else "?"
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

        hits = obj.get("hits", [])
        items: List[Dict[str, Any]] = []
        for idx, h in enumerate(hits):
            crawled = self._build_item_pixabay(h, prep, idx)
            items.append(crawled.to_dict())

        meta = {
            "query": prep["query"],
            "total": obj.get("total", 0),
            "total_hits": obj.get("totalHits", 0),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _build_item_pixabay(self, h: Dict[str, Any], prep: Dict[str, Any],
                            idx: int) -> CrawledItem:
        """Pixabay 特定字段映射到 10 字段 (P19-C1-fix P0 #2 + P0 #3)

        P0 #3 修复:
          title = user 字段 (uploader name) — 不再使用 tags (tags 应该移到 keywords)
          keywords = tags 列表 (用户搜索相关)
        """
        tags_str = h.get("tags", "")
        if isinstance(tags_str, str):
            keywords = [t.strip() for t in tags_str.split(",") if t.strip()][:10]
        else:
            keywords = list(tags_str) if tags_str else []
        # P0 #3: title 用 user 字段
        title = (
            h.get("user", "")  # Pixabay 给的是 user name
            or h.get("pageURL", "").split("/")[-1]  # 或从 URL 派生
            or f"Pixabay item {idx}"
        )
        return CrawledItem(
            id=str(h.get("id", f"pixabay_{idx}")),
            url=h.get("largeImageURL", h.get("webformatURL", "")),
            title=str(title),
            description=f"Pixabay image by {h.get('user', 'unknown')}",
            source=self.channel,
            author=str(h.get("user", "")),
            keywords=keywords,
            created_at=datetime.utcnow(),
            thumbnail_url=h.get("previewURL", h.get("webformatURL", "")),
            extra={
                "width": int(h.get("imageWidth", 0)),
                "height": int(h.get("imageHeight", 0)),
                "license": "pixabay-license",
                "page_url": h.get("pageURL", ""),
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_pixabay(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "total": count * 50,
            "totalHits": count * 50,
            "hits": [
                {
                    "id": 1000000 + i,
                    "pageURL": f"https://pixabay.com/mock/{i}",
                    "tags": f"{prep['query']}, sample, mock",
                    "previewURL": f"https://example.com/preview_{i}.jpg",
                    "webformatURL": f"https://example.com/web_{i}.jpg",
                    "largeImageURL": f"https://example.com/large_{i}.jpg",
                    "imageWidth": 1920,
                    "imageHeight": 1080,
                    "user": f"mock_user_{i}",
                    "user_id": 1000 + i,
                }
                for i in range(count)
            ],
        }