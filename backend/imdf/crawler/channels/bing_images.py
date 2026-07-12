"""Bing Images 渠道适配器 (P20-B1)

Bing 图片搜索 — 公开无需 API key.

URL 模式:
    https://www.bing.com/images/async?q={query}&first={start}&count={count}
    或主搜索: https://www.bing.com/images/search?q={query}&first={start}

HTML 结构 (简化):
    - <a class="iusc" m="{...}"> — m 属性是 JSON 字符串
    - JSON 内容: {"murl":"...","t":"...","desc":"...","turl":"...","mtime":"..."}
    - 或 data 属性内的 imgUrl / thumbnailUrl
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


_BING_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _default_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    try:
        import httpx
        merged = {
            "User-Agent": _BING_UA,
            "Accept-Language": "en-US,en;q=0.9",
            **headers,
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=merged) as client:
            r = client.get(url)
            return r.content, r.status_code, None
    except Exception as e_httpx:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": _BING_UA, **headers})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e_url:
            return b"", 0, f"httpx: {e_httpx}; urllib: {e_url}"


class BingImagesCrawler(ChannelCrawler):
    """Bing 图片搜索 — HTML 解析 (a.iusc m={...} 模式).

    公开无需 key, 默认 mock=True.
    """

    channel = "bing_images"
    api_endpoint = "https://www.bing.com/images/async"
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
        first = (page - 1) * count + 1
        return {
            "url": f"{self.api_endpoint}?q={query}&first={first}&count={count}&mmasync=1",
            "query": query,
            "count": count,
            "page": page,
            "first": first,
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return self._mock_html_response(prep).encode("utf-8"), 200, None
        try:
            merged = {
                "User-Agent": _BING_UA,
                "Accept-Language": "en-US,en;q=0.9",
                **headers,
            }
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
        items = self._parse_iusc(text, prep)
        if not items:
            items = self._parse_img_tags(text, prep)

        meta = {
            "query": prep["query"],
            "page": prep.get("page", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _parse_iusc(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 a.iusc 元素的 m= JSON 属性 — Bing 核心模式"""
        items: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(text, self._parser)
        except Exception as e:
            logger.debug("Bing BS4 parse error: %s", e)
            return items
        for idx, a in enumerate(soup.select("a.iusc, a.iusc[m]")):
            m_str = a.get("m")
            if not m_str:
                continue
            try:
                m = json.loads(m_str)
            except (json.JSONDecodeError, TypeError):
                continue
            crawled = self._build_item_bing(m, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _parse_img_tags(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """兜底: 直接抓 img 标签的 data-* 属性"""
        items: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(text, self._parser)
        except Exception:
            return items
        for idx, img in enumerate(soup.select("img")):
            obj_url = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-hi-res-url")
                or img.get("src", "")
            )
            if not obj_url or obj_url.startswith("data:"):
                continue
            raw = {
                "murl": obj_url,
                "turl": img.get("src", ""),
                "t": img.get("alt", ""),
                "desc": img.get("alt", ""),
            }
            crawled = self._build_item_bing(raw, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _build_item_bing(self, it: Dict[str, Any], prep: Dict[str, Any],
                         idx: int) -> CrawledItem:
        url = (
            it.get("murl")
            or it.get("mediaurl")
            or it.get("imgurl")
            or it.get("url")
            or ""
        )
        thumb = (
            it.get("turl")
            or it.get("thumburl")
            or it.get("thumbnail")
            or url
        )
        title = it.get("t", "") or it.get("title", "") or it.get("desc", "")
        desc = it.get("desc", "") or it.get("snippet", "")
        return CrawledItem(
            id=str(it.get("mid") or it.get("id") or f"bing_{prep['query']}_{idx:04d}"),
            url=url,
            title=title,
            description=desc,
            source=self.channel,
            author=it.get("purl") or it.get("author") or "",
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=thumb,
            extra={
                "width": int(it.get("mw", 0) or it.get("width", 0) or 0),
                "height": int(it.get("mh", 0) or it.get("height", 0) or 0),
                "page_url": it.get("purl") or it.get("pageurl") or "",
                "license": "bing-crawler-terms",
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_bing(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        """保留旧 API 兼容 (虽然现在 _do_fetch 直接返回 HTML)"""
        return {}

    def _mock_html_response(self, prep: Dict[str, Any]) -> str:
        """mock 完整 HTML — 含 a.iusc 元素 (模拟 Bing 真实页)"""
        count = prep["count"]
        items_html = []
        for i in range(count):
            m = {
                "murl": f"https://example.com/bing_{prep['query']}_{i}.jpg",
                "turl": f"https://example.com/bing_thumb_{prep['query']}_{i}.jpg",
                "t": f"Bing mock {prep['query']} {i+1}",
                "desc": f"Mock description {i+1}",
                "mid": f"bing_{prep['query']}_{i:04d}",
                "purl": f"https://example.com/page_{i}",
                "mw": 1920,
                "mh": 1080,
            }
            items_html.append(
                f'<a class="iusc" m=\'{json.dumps(m, ensure_ascii=False)}\'></a>'
            )
        return (
            "<!DOCTYPE html><html><body>"
            + "<div class='dgControl'>"
            + "".join(items_html)
            + "</div></body></html>"
        )

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
