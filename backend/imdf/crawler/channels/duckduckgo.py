"""DuckDuckGo Images 渠道适配器 (P20-B1)

DuckDuckGo 图片搜索 — 隐私优先, 公开无需 API key.

URL 模式 (两步):
    1. GET https://duckduckgo.com/?q={query}  (拿 vqd token)
    2. GET https://duckduckgo.com/i.js?q={query}&vqd={vqd}&f=json&p=1&s=0

JSON 响应: {"results": [{"image":"...","title":"...","width":N,
                        "height":N,"thumbnail":"...","url":"...","source":"..."}]}

vqd token 提取: <input name="vqd" value="..."> 或 input[type=hidden]
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


_DDG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _default_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    try:
        import httpx
        merged = {
            "User-Agent": _DDG_UA,
            "Accept-Language": "en-US,en;q=0.9",
            **headers,
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=merged) as client:
            r = client.get(url)
            return r.content, r.status_code, None
    except Exception as e_httpx:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": _DDG_UA, **headers})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e_url:
            return b"", 0, f"httpx: {e_httpx}; urllib: {e_url}"


class DuckDuckGoImagesCrawler(ChannelCrawler):
    """DuckDuckGo 图片搜索 — 两步抓取 (vqd token + i.js JSON).

    公开无需 key, 默认 mock=True. 真网络时两阶段 fetch (token + results)
    用同一个 http_fetcher 调用, mock 模式下直接返回 mock JSON 响应.
    """

    channel = "duckduckgo_images"
    api_endpoint = "https://duckduckgo.com"
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
        s = (page - 1) * count
        return {
            "url": f"{self.api_endpoint}/?q={query}&iax=images&ia=images",
            "i_url": f"{self.api_endpoint}/i.js",
            "query": query,
            "count": count,
            "page": page,
            "s": s,
            # 可选: 注入 vqd token 跳过 token 抓取 (测试/已知场景)
            "vqd": target.get("vqd"),
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        """两步: 先拿 vqd token, 再请求 i.js.

        返回 i.js 的 JSON bytes (真实抓取路径), mock 路径直接返回 mock.
        测试时 prep 中可注入 prep["vqd"] 跳过第一步.
        """
        if self.mock:
            return json.dumps(self._mock_response(prep), ensure_ascii=False).encode("utf-8"), 200, None

        # 测试可注入 vqd 跳过 token 抓取
        vqd = prep.get("vqd")
        if not vqd:
            vqd = self._fetch_vqd(url, headers)
            if not vqd:
                return b"", 0, "vqd token fetch failed"

        i_url = prep["i_url"]
        params = f"q={prep['query']}&vqd={vqd}&f=json&p=1&s={prep['s']}"
        full_i_url = f"{i_url}?{params}"
        try:
            content, status, err = self._http_fetcher(full_i_url, headers, self.config.timeout_seconds)
            return content, status, err
        except Exception as e:
            return b"", 0, str(e)

    def _fetch_vqd(self, url: str, headers: Dict[str, str]) -> Optional[str]:
        """抓首页拿 vqd token"""
        try:
            content, status, err = self._http_fetcher(url, headers, self.config.timeout_seconds)
            if err or status != 200 or not content:
                return None
            text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
            # 找 vqd 在 input value (DDG vqd 格式: 4-xxxxx-N 或 4-xxxxx-xxxx-xxxxx-N)
            m = re.search(r'name=["\']vqd["\']\s+value=["\']([\w-]+)["\']', text)
            if m:
                return m.group(1)
            # 备选: vqd='...'
            m = re.search(r"vqd\s*=\s*['\"]([\w-]+)['\"]", text)
            if m:
                return m.group(1)
            return None
        except Exception as e:
            logger.debug("DDG vqd fetch failed: %s", e)
            return None

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except Exception as e:
            return [], {"error": str(e), "mock": self.mock}

        items: List[Dict[str, Any]] = []
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # HTML fallback (e.g. when first-page response instead of i.js)
            items = self._parse_html_payload(text, prep)
        else:
            if not isinstance(obj, dict):
                return [], {"error": "unexpected json shape", "mock": self.mock}
            for idx, it in enumerate(obj.get("results", [])):
                if not isinstance(it, dict):
                    continue
                crawled = self._build_item_ddg(it, prep, idx)
                items.append(crawled.to_dict())

        meta = {
            "query": prep["query"],
            "page": prep.get("page", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _parse_html_payload(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """HTML fallback — 找 <img class="tile--img__img" src="...">"""
        items: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(text, self._parser)
        except Exception:
            return items
        for idx, img in enumerate(soup.select("img.tile--img__img, div.tile img")):
            obj_url = img.get("data-src") or img.get("src", "")
            if not obj_url or obj_url.startswith("data:"):
                continue
            raw = {
                "image": obj_url,
                "thumbnail": obj_url,
                "title": img.get("alt", ""),
                "url": "",
            }
            crawled = self._build_item_ddg(raw, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _build_item_ddg(self, it: Dict[str, Any], prep: Dict[str, Any],
                        idx: int) -> CrawledItem:
        url = (
            it.get("image")
            or it.get("imgurl")
            or it.get("url")
            or ""
        )
        thumb = (
            it.get("thumbnail")
            or it.get("thumb")
            or it.get("thumburl")
            or url
        )
        title = it.get("title", "")
        return CrawledItem(
            id=str(it.get("id") or f"ddg_{prep['query']}_{idx:04d}"),
            url=url,
            title=title,
            description=it.get("desc") or it.get("snippet") or "",
            source=self.channel,
            author=it.get("source") or it.get("author") or "",
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=thumb,
            extra={
                "width": int(it.get("width", 0) or 0),
                "height": int(it.get("height", 0) or 0),
                "page_url": it.get("url") or "",
                "license": "duckduckgo-crawler-terms",
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_ddg(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "query": prep["query"],
            "results": [
                {
                    "image": f"https://example.com/ddg_{prep['query']}_{i}.jpg",
                    "thumbnail": f"https://example.com/ddg_thumb_{prep['query']}_{i}.jpg",
                    "title": f"DDG mock {prep['query']} {i+1}",
                    "width": 1280,
                    "height": 720,
                    "url": f"https://example.com/page_{i}",
                    "source": f"Mock Source {i % 3}",
                }
                for i in range(count)
            ],
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
