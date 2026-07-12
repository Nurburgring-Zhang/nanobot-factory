"""智影 V4 — 搜索引擎爬虫: SerpAPI/Google CSE/Bing/DuckDuckGo/Brave"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class SearchEngineCrawler(BaseCrawler):
    """搜索引擎爬虫 — 5 大 provider 统一接口"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    async def _ensure_client(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装")
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """url 实际是 query 字符串 — 由 dispatcher 在调用时重写"""
        # 搜索引擎 url 是 search_url 模式,query 在 selectors
        query = self.config.selectors.get("query", url)
        provider = self.config.selectors.get("provider", "duckduckgo")
        start = time.time()
        if provider == "serpapi":
            return await self._fetch_serpapi(query, start)
        if provider == "google_cse":
            return await self._fetch_google_cse(query, start)
        if provider == "bing":
            return await self._fetch_bing(query, start)
        if provider == "brave":
            return await self._fetch_brave(query, start)
        # 默认: DuckDuckGo (公开 HTML, 不需 key)
        return await self._fetch_duckduckgo(query, start)

    async def _fetch_serpapi(self, query: str, start: float) -> RawDocument:
        """SerpAPI (付费) — 统一 Google/Bing/Baidu 结果"""
        client = await self._ensure_client()
        api_key = self.config.selectors.get("api_key", os.getenv("SERPAPI_KEY", ""))
        params = {
            "q": query,
            "api_key": api_key,
            "num": min(self.config.max_pages, 100),
            "engine": self.config.selectors.get("engine", "google"),
        }
        resp = await client.get("https://serpapi.com/search.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = _extract_serpapi_results(data)
        return RawDocument(
            url=f"serpapi://{quote_plus(query)}",
            type="json",
            title=f"Search: {query}",
            text="\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results[:10]),
            json={"results": results, "raw": data},
            source_metadata={"provider": "serpapi", "query": query},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_google_cse(self, query: str, start: float) -> RawDocument:
        """Google Custom Search JSON API"""
        client = await self._ensure_client()
        api_key = self.config.selectors.get("api_key", os.getenv("GOOGLE_CSE_KEY", ""))
        cx = self.config.selectors.get("cx", os.getenv("GOOGLE_CSE_CX", ""))
        params = {
            "q": query,
            "key": api_key,
            "cx": cx,
            "num": min(self.config.max_pages, 10),
        }
        resp = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in data.get("items", [])
        ]
        return RawDocument(
            url=f"google_cse://{quote_plus(query)}",
            type="json",
            title=f"Google CSE: {query}",
            text="\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results[:10]),
            json={"results": results, "raw": data},
            source_metadata={"provider": "google_cse", "query": query, "total": data.get("searchInformation", {}).get("totalResults", 0)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_bing(self, query: str, start: float) -> RawDocument:
        """Bing Web Search API (Azure)"""
        client = await self._ensure_client()
        api_key = self.config.selectors.get("api_key", os.getenv("BING_SEARCH_KEY", ""))
        endpoint = self.config.selectors.get("endpoint", "https://api.bing.microsoft.com/v7.0/search")
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        params = {"q": query, "count": min(self.config.max_pages, 50)}
        resp = await client.get(endpoint, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("webPages", {}).get("value", []):
            results.append(
                {
                    "title": item.get("name", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
        return RawDocument(
            url=f"bing://{quote_plus(query)}",
            type="json",
            title=f"Bing: {query}",
            text="\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results[:10]),
            json={"results": results, "raw": data},
            source_metadata={"provider": "bing", "query": query},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_brave(self, query: str, start: float) -> RawDocument:
        """Brave Search API"""
        client = await self._ensure_client()
        api_key = self.config.selectors.get("api_key", os.getenv("BRAVE_SEARCH_KEY", ""))
        headers = {"X-Subscription-Token": api_key}
        params = {"q": query, "count": min(self.config.max_pages, 50)}
        resp = await client.get("https://api.search.brave.com/res/v1/web/search", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
            for item in data.get("web", {}).get("results", [])
        ]
        return RawDocument(
            url=f"brave://{quote_plus(query)}",
            type="json",
            title=f"Brave: {query}",
            text="\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results[:10]),
            json={"results": results, "raw": data},
            source_metadata={"provider": "brave", "query": query},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_duckduckgo(self, query: str, start: float) -> RawDocument:
        """DuckDuckGo HTML (公开, 不需 key) — 通过 /html/ 端点"""
        client = await self._ensure_client()
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            BeautifulSoup = None
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        resp.raise_for_status()
        results: List[Dict[str, Any]] = []
        if BeautifulSoup is not None:
            soup = BeautifulSoup(resp.text, "lxml")
            for r in soup.select(".result")[: self.config.max_pages]:
                title_el = r.select_one(".result__a")
                snippet_el = r.select_one(".result__snippet")
                href = title_el.get("href", "") if title_el else ""
                # DDG 重定向: //duckduckgo.com/l/?uddg=... → 解码
                if "uddg=" in href:
                    import re
                    m = re.search(r"uddg=([^&]+)", href)
                    if m:
                        from urllib.parse import unquote
                        href = unquote(m.group(1))
                results.append(
                    {
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "url": href,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    }
                )
        return RawDocument(
            url=f"ddg://{quote_plus(query)}",
            type="html",
            title=f"DDG: {query}",
            text="\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results[:10]),
            json={"results": results},
            source_metadata={"provider": "duckduckgo", "query": query},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def _extract_serpapi_results(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 SerpAPI response 提取统一结果"""
    results: List[Dict[str, Any]] = []
    # organic_results (Google)
    for item in data.get("organic_results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return results
