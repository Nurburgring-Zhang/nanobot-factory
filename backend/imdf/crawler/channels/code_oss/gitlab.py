"""GitLab project search channel (P20-E)

Public GitLab search via web interface:

    GET https://gitlab.com/search?search={query}&nav_source=navbar

GitLab also offers a REST API for project search:

    GET https://gitlab.com/api/v4/projects?search={query}&per_page={n}

We default to the REST API (more stable markup) but fall back to HTML
parsing if the API endpoint returns empty or errors out.
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
class GitLabChannel(BaseCrawlerChannel):
    """Search public GitLab.com projects.

    Default endpoint: GitLab REST API (api/v4/projects).
    `use_html_fallback=True` switches to the web search page.
    """
    channel = "gitlab"
    api_endpoint = "https://gitlab.com/api/v4/projects"
    web_endpoint = "https://gitlab.com/search"

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
            "search": query,
            "per_page": per_page,
            "page": 1,
            "order_by": "star_count",
            "sort": "desc",
            "visibility": "public",
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
        if not isinstance(data, list):
            return []
        return [self._build_from_api(item, idx) for idx, item in enumerate(data)]

    async def _search_html(self, query: str, max_results: int) -> List[CrawlResult]:
        params = {
            "search": query,
            "nav_source": "navbar",
            "project_id": "",
        }
        url = f"{self.web_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query, "max_results": max_results}
        if not body:
            return []
        results = self.parse(body)
        return results[:max_results]

    # ---------- parsing ----------

    def _build_from_api(self, item: Dict[str, Any], idx: int) -> CrawlResult:
        path = item.get("path_with_namespace") or item.get("name") or f"gitlab_{idx}"
        url = item.get("web_url") or (
            f"https://gitlab.com/{path}" if path else ""
        )
        topics = item.get("topics") or item.get("tag_list") or []
        if isinstance(topics, list):
            topics = [str(t).strip() for t in topics if t]
        elif isinstance(topics, str):
            topics = [t.strip() for t in topics.split(",") if t.strip()]
        license_name = ""
        license_info = item.get("license") or {}
        if isinstance(license_info, dict):
            license_name = license_info.get("name") or license_info.get("key") or ""
        elif isinstance(license_info, str):
            license_name = license_info
        namespace = item.get("namespace") or {}
        author = (
            namespace.get("full_path") if isinstance(namespace, dict) else ""
        ) or item.get("owner", {}).get("username", "") if isinstance(item.get("owner"), dict) else ""
        if not author:
            author = path.split("/")[0] if "/" in path else ""
        return CrawlResult(
            id=str(item.get("id") or path or f"gitlab_{idx}"),
            url=url,
            title=path,
            description=item.get("description") or "",
            source=self.channel,
            author=author,
            language=item.get("programming_language") or "",
            stars=int(item.get("star_count") or 0),
            forks=int(item.get("forks_count") or 0),
            keywords=topics,
            license=license_name,
            last_updated=item.get("last_activity_at") or "",
            extra={
                "default_branch": item.get("default_branch") or "",
                "visibility": item.get("visibility") or "public",
                "open_issues_count": int(item.get("open_issues_count") or 0),
            },
        )

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Parse GitLab web search results page (HTML)."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        results: List[CrawlResult] = []
        # GitLab uses <a class="gl-link" data-testid="project-name-link" href="/owner/name">
        for idx, a in enumerate(soup.select(
            "a.gl-link[data-testid='project-name-link'], "
            "a[data-testid='project-name-link'], "
            "a.project-name, "
            "li.project-row a"
        )):
            href = a.get("href") or ""
            text = (a.get_text() or "").strip()
            if href.startswith("/"):
                url = f"https://gitlab.com{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"https://gitlab.com/{href}" if href else ""
            full_name = text or href.strip("/")
            parent = a.find_parent("li") or a.find_parent("article")
            desc = ""
            if parent:
                p = parent.find("p")
                if p:
                    desc = p.get_text(" ", strip=True)
            results.append(CrawlResult(
                id=full_name or f"gitlab_{idx}",
                url=url,
                title=full_name,
                description=desc,
                source="gitlab",
                author=full_name.split("/")[0] if "/" in full_name else "",
            ))
        return results


__all__ = ["GitLabChannel"]