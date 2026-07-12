"""360 Images (image.so.com) 渠道适配器 (P20-B1)

360 图片搜索 — 公开无需 API key.

URL 模式:
    https://image.so.com/s?q={query}&src=srp&sn={start}&pn={count}

HTML 结构 (简化):
    - JSON 嵌入: <script>var imgData = [...]</script>
    - <a class="img-link" href="..."><img src="..."></a>
    - AJAX 端点 sn=&pn= 增量加载

项目实际是 .so.com (无 image 前缀时), image.so.com 跳转过去.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from . import ChannelCrawler
from ._schemas import (
    CrawledItemModel,
    SearchRequest,
    SearchResponse,
    build_search_response,
    convert_crawl_result,
)
from ..base import CrawledItem
from ..config import CrawlerConfig

logger = logging.getLogger(__name__)


_SO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _default_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    try:
        import httpx
        merged = {"User-Agent": _SO_UA, **headers}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=merged) as client:
            r = client.get(url)
            return r.content, r.status_code, None
    except Exception as e_httpx:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": _SO_UA, **headers})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e_url:
            return b"", 0, f"httpx: {e_httpx}; urllib: {e_url}"


class SoImagesCrawler(ChannelCrawler):
    """360 图片搜索 — JSON embedded + HTML fallback.

    公开无需 key, 默认 mock=True.
    """

    channel = "so_images"
    api_endpoint = "https://image.so.com/s"
    requires_key = False
    key_env_var = ""

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 mock: bool = True,
                 http_fetcher: Optional[Any] = None,
                 parser: str = "html.parser"):
        super().__init__(config=config, mock=mock)
        self._http_fetcher = http_fetcher or _default_fetcher
        self._parser = parser

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if isinstance(target, str):
            target = {"query": target}
        if not isinstance(target, dict):
            return None
        query = target.get("query") or target.get("q")
        if not query:
            return None
        count = min(int(target.get("count", 30)), 100)
        page = int(target.get("page", 1))
        sn = (page - 1) * count
        return {
            "url": f"{self.api_endpoint}?q={query}&src=srp&sn={sn}&pn={count}",
            "query": query,
            "count": count,
            "page": page,
            "sn": sn,
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep), ensure_ascii=False).encode("utf-8"), 200, None
        try:
            merged = {"User-Agent": _SO_UA, **headers}
            content, status, err = self._http_fetcher(url, merged, self.config.timeout_seconds)
            return content, status, err
        except Exception as e:
            return b"", 0, str(e)

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except Exception as e:
            return [], {"error": str(e), "mock": self.mock}

        items: List[Dict[str, Any]] = []
        # 优先尝试 JSON (360 ajax 端点)
        if text.lstrip().startswith("{") or text.lstrip().startswith("["):
            items = self._parse_json_payload(text, prep)
        if not items:
            items = self._parse_html_payload(text, prep)
        if not items:
            items = self._parse_embedded_json(text, prep)

        meta = {
            "query": prep["query"],
            "page": prep.get("page", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _parse_json_payload(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return items
        if not isinstance(obj, dict):
            return items
        # 360 ajax 响应: {"list": [...], "total": N}
        for idx, it in enumerate(obj.get("list", []) or obj.get("items", [])):
            if not isinstance(it, dict):
                continue
            crawled = self._build_item_so(it, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _parse_html_payload(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(text, self._parser)
        except Exception as e:
            logger.debug("360 BS4 parse error: %s", e)
            return items
        # 模式: a.img-link > img
        for idx, a in enumerate(soup.select("a.img-link, div.img, div.img-cell")):
            img = a.select_one("img")
            obj_url = ""
            if img:
                obj_url = (
                    img.get("data-imgurl")
                    or img.get("data-original")
                    or img.get("src", "")
                )
            if not obj_url:
                obj_url = a.get("data-imgurl") or a.get("data-original") or ""
            if not obj_url:
                continue
            thumb = img.get("src", "") if img else obj_url
            title = (img.get("alt", "") if img else "") or a.get("title", "")
            raw = {
                "img": obj_url,
                "thumb": thumb,
                "title": title,
                "url": a.get("href", ""),
            }
            crawled = self._build_item_so(raw, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _parse_embedded_json(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 <script>var imgData = {...}</script> 抓 JSON"""
        items: List[Dict[str, Any]] = []
        m = re.search(
            r"var\s+imgData\s*=\s*(\{.*?\})\s*[;<]|"
            r"window\.__NUXT__\s*=\s*(\{.*?\});",
            text, re.DOTALL,
        )
        if not m:
            return items
        json_str = m.group(1) or m.group(2)
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError:
            return items
        if not isinstance(obj, dict):
            return items
        data = obj.get("list", []) or obj.get("items", []) or []
        for idx, it in enumerate(data):
            if not isinstance(it, dict):
                continue
            crawled = self._build_item_so(it, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _build_item_so(self, it: Dict[str, Any], prep: Dict[str, Any],
                       idx: int) -> CrawledItem:
        url = (
            it.get("img")
            or it.get("imgurl")
            or it.get("url")
            or it.get("src")
            or ""
        )
        thumb = (
            it.get("thumb")
            or it.get("thumbUrl")
            or it.get("thumbnail")
            or url
        )
        title = it.get("title", "") or it.get("alt", "")
        return CrawledItem(
            id=str(it.get("id") or it.get("di") or f"so_{prep['query']}_{idx:04d}"),
            url=url,
            title=title,
            description=it.get("desc") or it.get("content") or "",
            source=self.channel,
            author=it.get("author") or it.get("site") or "",
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=thumb,
            extra={
                "width": int(it.get("width", 0) or 0),
                "height": int(it.get("height", 0) or 0),
                "from_url": it.get("url") or it.get("fromUrl") or "",
                "license": "360-crawler-terms",
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_so(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "list": [
                {
                    "id": i + 1,
                    "img": f"https://example.com/so_{prep['query']}_{i}.jpg",
                    "thumb": f"https://example.com/so_thumb_{prep['query']}_{i}.jpg",
                    "title": f"360 mock {prep['query']} {i+1}",
                    "width": 1920,
                    "height": 1080,
                    "url": f"https://example.com/page_{i}",
                }
                for i in range(count)
            ],
            "total": count * 8,
        }

    async def search(self, query: str, max_results: int = 50) -> List[CrawledItemModel]:
        """异步 search — Pydantic v2 CrawledItemModel 返回."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self.crawl({"query": query, "count": max_results})
        )
        return convert_crawl_result(
            result.items, query=query, page=1, mock=self.mock,
            extra_metadata=result.metadata,
        )

    async def search_request(self, request: SearchRequest) -> SearchResponse:
        """Pydantic v2 输入/输出 API."""
        loop = asyncio.get_event_loop()
        target = {
            "query": request.query,
            "count": request.max_results,
            "page": request.page,
            **request.extra,
        }
        result = await loop.run_in_executor(None, lambda: self.crawl(target))
        return build_search_response(
            result.items, query=request.query, page=request.page,
            mock=self.mock, extra_metadata=result.metadata,
        )
