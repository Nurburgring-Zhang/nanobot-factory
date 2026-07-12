"""SourceForge project search channel (P20-E)

Public SourceForge project search via web interface:

    GET https://sourceforge.net/directory/?q={query}

Sample markup (simplified):
    <a class="project-name" href="/projects/owner/name/">
        <span>name</span>
    </a>
    <p class="description">...</p>
    <div class="project-stats">
        <span class="stars">123 stars</span>
        <span class="language">Python</span>
    </div>
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
class SourceForgeChannel(BaseCrawlerChannel):
    """Search public SourceForge projects via the directory listing."""
    channel = "sourceforge"
    web_endpoint = "https://sourceforge.net/directory/"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # ---------- search ----------

    async def _search_impl(self, query: str, max_results: int) -> List[CrawlResult]:
        params = {"q": query}
        url = f"{self.web_endpoint}?{urllib.parse.urlencode(params)}"
        body = await self._fetch(url)
        self._last_meta = {"url": url, "query": query, "max_results": max_results}
        if not body:
            return []
        results = self.parse(body)
        return results[:max_results]

    # ---------- parsing ----------

    @staticmethod
    def _coerce_int(text: str) -> int:
        if not text:
            return 0
        m = re.search(r"(\d+)", text.replace(",", ""))
        if m:
            try:
                return int(m.group(1))
            except (ValueError, TypeError):
                return 0
        return 0

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Parse SourceForge directory search results (HTML)."""
        if not html:
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        results: List[CrawlResult] = []
        # SourceForge uses cards with .project-name and various stats
        cards = soup.select(
            ".project-card, article.project, "
            ".directory-listing .item, "
            "li.project-item, .card.project"
        )
        if not cards:
            cards = soup.select("a[href*='/projects/']")
        for idx, card in enumerate(cards):
            # link
            link = card.select_one("a.project-name, a[href*='/projects/']")
            if link is None and card.name == "a":
                link = card
            if link is None:
                continue
            href = link.get("href") or ""
            if href.startswith("/"):
                url = f"https://sourceforge.net{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"https://sourceforge.net/{href}" if href else ""

            # project name + owner
            slug = ""
            m = re.search(r"/projects/([^/]+/[^/]+)", href)
            if m:
                slug = m.group(1)
            title_text = link.get_text(" ", strip=True) or slug

            # description
            desc = ""
            desc_el = card.select_one(".description, .project-description, p")
            if desc_el:
                desc = desc_el.get_text(" ", strip=True)

            # language
            language = ""
            lang_el = card.select_one(".language, .project-language")
            if lang_el:
                language = lang_el.get_text(strip=True)

            # stars / downloads / activity
            stars = 0
            stars_el = card.select_one(".stars, .stars-count, [data-qa='stars']")
            if stars_el:
                stars = SourceForgeChannel._coerce_int(stars_el.get_text())

            # description text for keywords extraction
            text_blob = card.get_text(" ", strip=True).lower()

            result = CrawlResult(
                id=slug or title_text or f"sourceforge_{idx}",
                url=url,
                title=title_text,
                description=desc,
                source="sourceforge",
                author=slug.split("/")[0] if "/" in slug else "",
                language=language,
                stars=stars,
                forks=0,
                keywords=[],
                license="",
                last_updated="",
                extra={"slug": slug},
            )
            results.append(result)
        return results


__all__ = ["SourceForgeChannel"]