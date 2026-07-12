"""Gitee (码云) repository search channel (P20-E)

Public Gitee search via web interface:

    GET https://gitee.com/search?utf8=%E2%9C%93&q={query}

Gitee also offers a JSON search API:

    GET https://gitee.com/api/v5/search/repositories?q={query}&per_page={n}&page={p}

Default endpoint: REST API v5 (no auth required for public search).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import BaseCrawlerChannel, CrawlResult, register

logger = logging.getLogger(__name__)


@register
class GiteeChannel(BaseCrawlerChannel):
    """Search public Gitee repositories via REST API v5."""
    channel = "gitee"
    api_endpoint = "https://gitee.com/api/v5/search/repositories"
    web_endpoint = "https://gitee.com/search"

    def __init__(self, use_html_fallback: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.use_html_fallback = use_html_fallback

    # ---------- search ----------

    async def _search_impl(self, query: str, max_results: int) -> List[CrawlResult]:
        if self.use_html_fallback:
            return await self._search_html(query, max_results)
        return await self._search_api(query, max_results)

    async def _search_api(self, query: str, max_results: int) -> List[CrawlResult]:
        per_page = min(max_results, 100)
        params = {
            "q": query,
            "per_page": per_page,
            "page": 1,
            "sort": "stars_count",
            "order": "desc",
        }
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query}
        if not body:
            return []
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return []
        items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data") or data.get("items") or []
        return [self._build_from_api(item, idx) for idx, item in enumerate(items)]

    async def _search_html(self, query: str, max_results: int) -> List[CrawlResult]:
        params = {"utf8": "✓", "q": query, "type": "Repositories"}
        url = f"{self.web_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query, "max_results": max_results}
        if not body:
            return []
        return self.parse(body)[:max_results]

    # ---------- parsing ----------

    def _build_from_api(self, item: Dict[str, Any], idx: int) -> CrawlResult:
        full_name = item.get("full_name") or item.get("path") or item.get("name") or f"gitee_{idx}"
        url = item.get("html_url") or item.get("url") or (
            f"https://gitee.com/{full_name}" if full_name and "/" in full_name else ""
        )
        author = item.get("namespace") or {}
        if isinstance(author, dict):
            author_name = author.get("name") or author.get("path") or ""
        else:
            author_name = str(author) if author else ""
        if not author_name and "/" in full_name:
            author_name = full_name.split("/")[0]
        return CrawlResult(
            id=str(item.get("id") or full_name or f"gitee_{idx}"),
            url=url,
            title=full_name,
            description=item.get("description") or "",
            source=self.channel,
            author=author_name,
            language=item.get("language") or "",
            stars=int(item.get("stargazers_count") or item.get("stars_count") or 0),
            forks=int(item.get("forks_count") or 0),
            keywords=[],  # Gitee API v5 doesn't return topics for free search
            license=item.get("license") or "",
            last_updated=item.get("updated_at") or item.get("last_push_at") or "",
            extra={
                "private": bool(item.get("private", False)),
                "default_branch": item.get("default_branch") or "",
                "open_issues_count": int(item.get("open_issues_count") or 0),
                "watchers_count": int(item.get("watchers_count") or 0),
            },
        )

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Parse Gitee web search results page (HTML)."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        results: List[CrawlResult] = []
        # Gitee uses <a class="title" href="/owner/name">
        for idx, a in enumerate(soup.select(
            "a.title[href*='/'], "
            ".search-item a[href^='/'], "
            ".item .title a, "
            ".project-item .title a"
        )):
            href = a.get("href") or ""
            text = (a.get_text() or "").strip()
            if href.startswith("/"):
                url = f"https://gitee.com{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"https://gitee.com/{href}" if href else ""
            full_name = text or href.strip("/")
            parent = a.find_parent("div", class_="item") or a.find_parent("article") or a.parent
            desc = ""
            if parent:
                # Gitee puts description in .desc
                p = parent.select_one(".desc") or parent.find("p")
                if p:
                    desc = p.get_text(" ", strip=True)
            results.append(CrawlResult(
                id=full_name or f"gitee_{idx}",
                url=url,
                title=full_name,
                description=desc,
                source="gitee",
                author=full_name.split("/")[0] if "/" in full_name else "",
            ))
        return results


__all__ = ["GiteeChannel"]