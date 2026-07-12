"""Google Images 渠道适配器

注: Google 公开图片搜索无官方 API; 实际生产应使用 Custom Search API (需 key).
无 key 时进入 mock 模式 — 生成 placeholder results.

Custom Search JSON API:
    GET https://www.googleapis.com/customsearch/v1?key=KEY&cx=CX&q=...
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


class GoogleImagesCrawler(ChannelCrawler):
    """Google 图片搜索 — Custom Search API 或 mock.

    config:
        cx: 搜索引擎 ID (Custom Search Engine ID)
        api_key: Google API key (或 GOOGLE_API_KEY env)

    使用:
        cw = GoogleImagesCrawler(cx="abc123", api_key="...", mock=False)
        result = cw.crawl({"query": "cute cats", "count": 20})
    """

    channel = "google_images"
    api_endpoint = "https://www.googleapis.com/customsearch/v1"
    requires_key = True
    key_env_var = "GOOGLE_API_KEY"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 api_key: Optional[str] = None, cx: Optional[str] = None,
                 mock: bool = False,
                 http_fetcher: Optional[Any] = None):
        super().__init__(config=config, api_key=api_key, mock=mock)
        import os
        self.cx = cx or os.environ.get("GOOGLE_CX")
        # mock if missing both
        if not self.api_key or not self.cx:
            self.mock = True
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
            "count": min(int(target.get("count", 10)), 50),
            "start": int(target.get("start", 1)),
            "search_type": target.get("search_type", "image"),
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep)).encode("utf-8"), 200, None
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": prep["query"],
            "searchType": prep["search_type"],
            "num": prep["count"],
            "start": prep["start"],
        }
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
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            return [], {"error": str(e), "mock": self.mock}

        items: List[Dict[str, Any]] = []
        for idx, it in enumerate(obj.get("items", [])):
            # (P19-C1-fix P0 #2) — 通过 _build_item() 构造统一 10 字段 CrawledItem
            crawled = self._build_item_google(it, prep, idx)
            items.append(crawled.to_dict())

        meta = {
            "query": prep["query"],
            "total_results": obj.get("searchInformation", {}).get("totalResults", "0"),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _build_item_google(self, it: Dict[str, Any], prep: Dict[str, Any],
                           idx: int) -> CrawledItem:
        """Google Images 特定字段映射到 10 字段 (P19-C1-fix P0 #2)"""
        image = it.get("image", {})
        return CrawledItem(
            id=str(it.get("cacheId", "")) or (it.get("link", "")[:64]),
            url=it.get("link", ""),
            title=it.get("title", ""),
            description=it.get("snippet", ""),
            source=self.channel,
            author="",
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=image.get("thumbnailLink", ""),
            extra={
                "width": int(image.get("width", 0)),
                "height": int(image.get("height", 0)),
                "context_link": image.get("contextLink", ""),
                "license": "unknown",
                "mock": self.mock,
            },
        )

    # 保留 _build_item 作为 default 实现入口 (channel 子类通用接口)
    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_google(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep.get("count", 10)
        return {
            "items": [
                {
                    "title": f"{prep['query']} sample {i+1}",
                    "link": f"https://example.com/img_{i}.jpg",
                    "snippet": f"Mock result {i+1} for query: {prep['query']}",
                    "image": {
                        "thumbnailLink": f"https://example.com/thumb_{i}.jpg",
                        "width": 1024,
                        "height": 768,
                        "contextLink": f"https://example.com/page_{i}",
                    },
                }
                for i in range(count)
            ],
            "searchInformation": {"totalResults": str(count * 100)},
        }