"""GitHub repository search channel (P20-E)

GitHub exposes a public REST API for searching public repositories:

    GET https://api.github.com/search/repositories?q={query}&per_page={n}&page={p}

Authentication is optional (60 req/hour unauthenticated; 5000 req/hour with
a personal access token). For this channel we read GITHUB_TOKEN from env if
available but never require it.

Response shape:
    {
        "total_count": 12345,
        "incomplete_results": false,
        "items": [
            {
                "id": 12345,
                "full_name": "owner/name",
                "name": "name",
                "owner": {"login": "owner", "avatar_url": "..."},
                "html_url": "https://github.com/owner/name",
                "description": "...",
                "language": "Python",
                "stargazers_count": 100,
                "forks_count": 10,
                "license": {"spdx_id": "MIT"},
                "topics": ["..."],
                "updated_at": "2024-01-01T00:00:00Z",
                "default_branch": "main",
                "private": false,
                "archived": false,
                "open_issues_count": 0,
                "watchers_count": 100,
            },
            ...
        ]
    }
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup  # noqa: F401  (kept for consistency)

from . import BaseCrawlerChannel, CrawlResult, register

logger = logging.getLogger(__name__)


@register
class GitHubChannel(BaseCrawlerChannel):
    """Search public GitHub repositories via api.github.com.

    Usage:
        ch = GitHubChannel(rate_limit_seconds=2.0)
        results = asyncio.run(ch.search("openai", max_results=10))

    Tests inject httpx.MockTransport:
        ch = GitHubChannel(transport=httpx.MockTransport(handler))
    """
    channel = "github"
    api_endpoint = "https://api.github.com/search/repositories"

    def __init__(self, token: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.token = token or os.environ.get("GITHUB_TOKEN")

    # ---------- transport ----------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = super()._headers(extra)
        h["Accept"] = "application/vnd.github+json"
        h["X-GitHub-Api-Version"] = "2022-11-28"
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # ---------- search ----------

    async def _search_impl(self, query: str, max_results: int) -> List[CrawlResult]:
        per_page = min(max_results, 100)
        params = {
            "q": query,
            "per_page": per_page,
            "page": 1,
            "sort": "stars",
            "order": "desc",
        }
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query, "max_results": max_results}
        if not body:
            return []
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.warning("%s: invalid JSON: %s", self.channel, e)
            return []
        items = data.get("items") or []
        return [self._build_result(item, idx) for idx, item in enumerate(items)]

    # ---------- parsing ----------

    def _build_result(self, item: Dict[str, Any], idx: int) -> CrawlResult:
        owner = (item.get("owner") or {}).get("login") or ""
        full_name = item.get("full_name") or item.get("name") or f"github_{idx}"
        url = item.get("html_url") or (
            f"https://github.com/{full_name}" if full_name else ""
        )
        license_obj = item.get("license") or {}
        license_name = license_obj.get("spdx_id") or license_obj.get("name") or ""
        topics = item.get("topics") or []
        if isinstance(topics, list):
            topics = [str(t).strip() for t in topics if t]
        return CrawlResult(
            id=str(item.get("id") or full_name or f"github_{idx}"),
            url=url,
            title=full_name,
            description=item.get("description") or "",
            source=self.channel,
            author=owner,
            language=item.get("language") or "",
            stars=int(item.get("stargazers_count") or 0),
            forks=int(item.get("forks_count") or 0),
            keywords=topics,
            license=license_name,
            last_updated=item.get("updated_at") or "",
            extra={
                "default_branch": item.get("default_branch") or "",
                "archived": bool(item.get("archived", False)),
                "private": bool(item.get("private", False)),
                "open_issues_count": int(item.get("open_issues_count") or 0),
                "watchers_count": int(item.get("watchers_count") or 0),
                "visibility": "public" if not item.get("private") else "private",
            },
        )

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Parse a GitHub web search results page (HTML fallback).

        Returns [] if html is empty. We do best-effort extraction from the
        <a class="Link--primary" itemprop="name codeRepository"> markup
        GitHub uses in its HTML search page.
        """
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        results: List[CrawlResult] = []
        for idx, a in enumerate(soup.select("a.Link--primary[itemprop='name codeRepository']")):
            full_name = (a.get_text() or "").strip()
            if not full_name:
                continue
            href = a.get("href") or ""
            url = f"https://github.com{href}" if href.startswith("/") else href
            parent = a.find_parent("article") or a.find_parent("div")
            desc = ""
            if parent:
                p = parent.find("p")
                if p:
                    desc = p.get_text(" ", strip=True)
            results.append(CrawlResult(
                id=full_name,
                url=url,
                title=full_name,
                description=desc,
                source="github",
                author=full_name.split("/")[0] if "/" in full_name else "",
            ))
        return results


__all__ = ["GitHubChannel"]