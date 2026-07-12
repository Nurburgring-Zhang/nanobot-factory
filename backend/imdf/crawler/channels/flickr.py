"""Flickr 渠道适配器

Flickr REST API:
    GET https://api.flickr.com/services/rest/?method=flickr.photos.search&api_key=KEY&text=...

公开 API, 需要 API key. 无 key 时 mock.

鉴权: API Key (query param api_key)
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


class FlickrCrawler(ChannelCrawler):
    """Flickr 图片搜索 — REST API 或 mock.

    使用:
        cw = FlickrCrawler(api_key="...", mock=False)
        result = cw.crawl({"query": "sunset", "count": 20})
    """

    channel = "flickr"
    api_endpoint = "https://api.flickr.com/services/rest/"
    requires_key = True
    key_env_var = "FLICKR_API_KEY"

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
        query = target.get("query") or target.get("text")
        if not query:
            return None
        return {
            "url": self.api_endpoint,
            "query": query,
            "count": min(int(target.get("count", 20)), 100),
            "page": int(target.get("page", 1)),
            "sort": target.get("sort", "relevance"),
            "license": target.get("license"),  # e.g. "1,2,4,5"
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep)).encode("utf-8"), 200, None
        params = {
            "method": "flickr.photos.search",
            "api_key": self.api_key,
            "format": "json",
            "nojsoncallback": "1",
            "text": prep["query"],
            "per_page": prep["count"],
            "page": prep["page"],
            "sort": prep["sort"],
        }
        if prep.get("license"):
            params["license"] = prep["license"]
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

        photos_obj = obj.get("photos", {})
        photos = photos_obj.get("photo", [])
        items: List[Dict[str, Any]] = []
        for idx, p in enumerate(photos):
            crawled = self._build_item_flickr(p, prep, idx)
            items.append(crawled.to_dict())

        meta = {
            "query": prep["query"],
            "total": photos_obj.get("total", "0"),
            "page": photos_obj.get("page", 1),
            "pages": photos_obj.get("pages", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _build_item_flickr(self, p: Dict[str, Any], prep: Dict[str, Any],
                           idx: int) -> CrawledItem:
        """Flickr 特定字段映射到 10 字段 (P19-C1-fix P0 #2)"""
        url_tpl = (
            f"https://farm{p.get('farm', 0)}.staticflickr.com/"
            f"{p.get('server', '0')}/{p.get('id', '')}_{p.get('secret', '')}.jpg"
        )
        return CrawledItem(
            id=str(p.get("id", f"flickr_{idx}")),
            url=url_tpl,
            title=p.get("title", ""),
            description=f"Flickr photo {p.get('id', '')}",
            source=self.channel,
            author=p.get("owner", ""),
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=url_tpl.replace(".jpg", "_s.jpg"),
            extra={
                "license": f"flickr-license-{p.get('license', '0')}",
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_flickr(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "photos": {
                "page": prep["page"],
                "pages": 1,
                "perpage": count,
                "total": str(count * 10),
                "photo": [
                    {
                        "id": f"mock_{prep['query']}_{i:04d}",
                        "owner": "mock_owner",
                        "secret": "abc123",
                        "server": "65535",
                        "farm": 1,
                        "title": f"Flickr mock {prep['query']} {i+1}",
                        "license": "4",
                    }
                    for i in range(count)
                ],
            }
        }