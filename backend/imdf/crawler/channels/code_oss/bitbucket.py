"""Bitbucket repository search channel (P20-E)

Public Bitbucket search via web interface:

    GET https://bitbucket.org/search?q={query}&target=repositories

Bitbucket's legacy REST API 1.0 was deprecated in 2023 and the new
2.0 API requires authentication for searches. We default to the HTML
search page, which works without authentication.

Sample markup (simplified):
    <a class="repo-link" href="/owner/name">
        <span class="repo-name">name</span>
        <span class="owner-name">owner</span>
        <p class="repo-description">...</p>
    </a>
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import BaseCrawlerChannel, CrawlResult, register

logger = logging.getLogger(__name__)


@register
class BitbucketChannel(BaseCrawlerChannel):
    """Search public Bitbucket repositories via the web search page."""
    channel = "bitbucket"
    web_endpoint = "https://bitbucket.org/search"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # ---------- search ----------

    async def _search_impl(self, query: str, max_results: int) -> List[CrawlResult]:
        params = {
            "q": query,
            "target": "repositories",
            "sort": "score",
        }
        url = f"{self.web_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query, "max_results": max_results}
        if not body:
            return []
        results = self.parse(body)
        return results[:max_results]

    # ---------- parsing ----------

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Parse Bitbucket web search results (HTML)."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        results: List[CrawlResult] = []
        # Bitbucket uses <a class="repo-link" href="/owner/name">
        for idx, a in enumerate(soup.select(
            "a.repo-link, "
            "a[data-qa='repo-link'], "
            "article.search-result a[href^='/'], "
            ".repo-list a[href*='/']"
        )):
            href = a.get("href") or ""
            text = (a.get_text(" ", strip=True) or "").strip()
            if href.startswith("/"):
                url = f"https://bitbucket.org{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"https://bitbucket.org/{href}" if href else ""

            # extract owner/name from href or text
            full_name = ""
            if href:
                m = re.search(r"/([^/]+/[^/]+)/?(?:[?#].*)?$", href)
                if m:
                    full_name = m.group(1)
            if not full_name:
                # try text
                parts = text.split()
                if len(parts) >= 2:
                    full_name = "/".join(parts[:2])
                elif parts:
                    full_name = parts[0]
            if not full_name:
                full_name = f"bitbucket_{idx}"

            parent = a.find_parent("article") or a.find_parent("div", class_="repo-list") or a.parent
            desc = ""
            if parent:
                p = parent.select_one(".description, .repo-description, p")
                if p:
                    desc = p.get_text(" ", strip=True)
            results.append(CrawlResult(
                id=full_name,
                url=url,
                title=full_name,
                description=desc,
                source="bitbucket",
                author=full_name.split("/")[0] if "/" in full_name else "",
                keywords=[],
                extra={"slug": full_name.split("/")[1] if "/" in full_name else full_name},
            ))
        return results


__all__ = ["BitbucketChannel"]