"""Baidu Images 渠道适配器 (P20-B1)

百度图片搜索 — 公开页 https://image.baidu.com 无需 API key,
通过 HTML + JSON 嵌入方式抓取。

URL 模式:
    https://image.baidu.com/search/index?tn=resultjson&word={query}&pn={pn}

HTML 结构 (简化):
    - 列表项: <li class="imgitem" data-objurl="..." data-thumburl="..." data-fromUrl="...">
    - 或: <a class="imgitem" style="background-image:url(...)" data-objurl="...">
    - JSON API 响应格式: {"data": [{"objURL":"...","fromURL":"...","thumbURL":"..."}]}

公开爬取注意:
    - 反爬较严 — 应使用真实 UA 池 + 限速
    - 默认 mock=True 避免真网络调用挂死
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


# 默认 User-Agent — Baidu 对默认 UA 不太敏感, 但仍建议用真实浏览器
_BAIDU_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _default_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    """httpx 同步 fetcher — 失败时回退 urllib."""
    try:
        import httpx
        merged = {"User-Agent": _BAIDU_UA, **headers}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=merged) as client:
            r = client.get(url)
            return r.content, r.status_code, None
    except Exception as e_httpx:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": _BAIDU_UA, **headers})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e_url:
            return b"", 0, f"httpx: {e_httpx}; urllib: {e_url}"


class BaiduImagesCrawler(ChannelCrawler):
    """百度图片搜索 — HTML + JSON 双路解析.

    公开无需 key, 默认 mock=True 避免真网络.
    真实抓取 (mock=False) 时建议设置 RPS 0.3-0.5 防止被封 IP.

    使用:
        cw = BaiduImagesCrawler(mock=True)
        result = cw.crawl({"query": "可爱猫咪", "count": 30})
    """

    channel = "baidu_images"
    api_endpoint = "https://image.baidu.com/search/index"
    requires_key = False
    key_env_var = ""

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 mock: bool = True,
                 http_fetcher: Optional[Any] = None,
                 parser: str = "html.parser"):
        super().__init__(config=config, mock=mock)
        self._http_fetcher = http_fetcher or _default_fetcher
        self._parser = parser  # BeautifulSoup parser

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if isinstance(target, str):
            target = {"query": target}
        if not isinstance(target, dict):
            return None
        query = target.get("query") or target.get("word") or target.get("q")
        if not query:
            return None
        count = min(int(target.get("count", 30)), 100)
        page = int(target.get("page", 1))
        pn = (page - 1) * count
        return {
            "url": f"{self.api_endpoint}?tn=resultjson&word={query}&pn={pn}&rn={count}",
            "query": query,
            "count": count,
            "page": page,
            "pn": pn,
            "search_type": "image",
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self.mock:
            return json.dumps(self._mock_response(prep), ensure_ascii=False).encode("utf-8"), 200, None
        try:
            merged = {"User-Agent": _BAIDU_UA, **headers}
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
        # 优先尝试 JSON 解析 (tn=resultjson 端点返回)
        if text.lstrip().startswith("{") or text.lstrip().startswith("["):
            items = self._parse_json_payload(text, prep)
        # 失败时回退 HTML
        if not items:
            items = self._parse_html_payload(text, prep)

        meta = {
            "query": prep["query"],
            "page": prep.get("page", 1),
            "items_count": len(items),
            "mock": self.mock,
        }
        return items, meta

    def _parse_json_payload(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """JSON payload 解析 — Baidu resultjson 端点返回 {data: [...]}"""
        items: List[Dict[str, Any]] = []
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(obj, dict):
            return []
        data = obj.get("data", [])
        for idx, it in enumerate(data):
            if not isinstance(it, dict):
                continue
            obj_url = it.get("objURL") or it.get("middleURL") or it.get("thumbURL") or ""
            if not obj_url:
                continue
            crawled = self._build_item_baidu(it, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _parse_html_payload(self, text: str, prep: Dict[str, Any]) -> List[Dict[str, Any]]:
        """HTML payload 解析 — 抓取 .imgitem data-objurl"""
        items: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(text, self._parser)
        except Exception as e:
            logger.debug("Baidu BS4 parse error: %s", e)
            return items
        # 模式 1: li.imgitem[data-objurl]
        for idx, li in enumerate(soup.select("li.imgitem, div.imgitem, a.imgitem")):
            obj_url = (
                li.get("data-objurl")
                or li.get("data-objURL")
                or li.get("objurl")
            )
            thumb_url = li.get("data-thumburl") or li.get("data-thumbURL") or ""
            from_url = li.get("data-fromurl") or li.get("data-fromURL") or ""
            if not obj_url:
                # 模式 2: style="background-image:url(...)"
                style = li.get("style", "")
                m = re.search(r"background-image\s*:\s*url\((['\"]?)([^'\")]+)\1\)", style)
                if m:
                    obj_url = m.group(2)
            if not obj_url:
                continue
            title_el = li.select_one("img") or li
            title = title_el.get("alt", "") if title_el else ""
            raw = {
                "objURL": obj_url,
                "thumbURL": thumb_url,
                "fromURL": from_url,
                "title": title,
            }
            crawled = self._build_item_baidu(raw, prep, idx)
            items.append(crawled.to_dict())
        return items

    def _build_item_baidu(self, it: Dict[str, Any], prep: Dict[str, Any],
                          idx: int) -> CrawledItem:
        """百度图片字段映射到 10 字段"""
        url = it.get("objURL") or it.get("objurl") or it.get("middleURL") or it.get("thumbURL") or ""
        thumb = it.get("thumbURL") or it.get("thumburl") or url
        title = it.get("title", "") or it.get("fromPageTitle", "") or it.get("alt", "")
        return CrawledItem(
            id=str(it.get("id") or it.get("di") or f"baidu_{prep['query']}_{idx:04d}"),
            url=url,
            title=title,
            description=it.get("fromURL") or it.get("fromurl") or "",
            source=self.channel,
            author=it.get("author") or it.get("uploader") or "",
            keywords=[prep.get("query", "")],
            created_at=datetime.utcnow(),
            thumbnail_url=thumb,
            extra={
                "width": int(it.get("width", 0) or 0),
                "height": int(it.get("height", 0) or 0),
                "from_url": it.get("fromURL") or it.get("fromurl") or "",
                "license": "baidu-crawler-terms",
                "mock": self.mock,
            },
        )

    def _build_item(self, raw: Dict[str, Any], prep: Dict[str, Any],
                    idx: int) -> CrawledItem:
        return self._build_item_baidu(raw, prep, idx)

    def _mock_response(self, prep: Dict[str, Any]) -> Dict[str, Any]:
        count = prep["count"]
        return {
            "data": [
                {
                    "id": i + 1,
                    "objURL": f"https://example.com/baidu_{prep['query']}_{i}.jpg",
                    "thumbURL": f"https://example.com/baidu_thumb_{prep['query']}_{i}.jpg",
                    "fromURL": f"https://example.com/page_{i}",
                    "title": f"Baidu mock {prep['query']} {i+1}",
                    "width": 1024,
                    "height": 768,
                    "fromPageTitle": f"Mock page {i+1}",
                }
                for i in range(count)
            ],
        }

    # ============== task-spec API: async search() ==============

    async def search(self, query: str, max_results: int = 50) -> List[CrawledItemModel]:
        """异步 search 入口 — 满足 task spec 接口.

        Pydantic v2 返回类型. 包装同步 crawl() 到 asyncio 线程池,
        再用 CrawledItemModel.from_dict() 把 list of dict 转 Pydantic models.
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self.crawl({"query": query, "count": max_results})
        )
        return convert_crawl_result(
            result.items, query=query, page=1, mock=self.mock,
            extra_metadata=result.metadata,
        )

    async def search_request(self, request: SearchRequest) -> SearchResponse:
        """接受 Pydantic v2 SearchRequest 输入, 返回 SearchResponse.

        这是 task spec 推荐的 Pydantic-typed 入口.
        """
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
