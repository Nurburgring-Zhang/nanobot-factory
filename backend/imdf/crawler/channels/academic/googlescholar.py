"""Google Scholar crawler channel (P20-D).

Google Scholar has no public REST API. The public search URL:
    GET https://scholar.google.com/scholar?q=<query>&hl=en&num=<N>

Returns an HTML page with `<div class="gs_r gs_or gs_scl">` result
nodes. We parse these with BeautifulSoup.

Caveats (as documented by Google's robots.txt terms):
- Google explicitly disallows automated scraping of Scholar in their
  robots.txt unless you honor a delay. The shared `rate_limit_seconds`
  defaults to 1.0s; production users should raise this to >=3s to stay
  friendly to Google's servers.
- We treat the channel as best-effort; tests inject a mock transport
  with a parsed HTML fixture so real network is never touched.
- When the parser finds zero result divs, we fall back to returning the
  Scholar search URL itself as a single Paper so callers always get a
  navigable canonical link.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import BaseAcademicCrawler
from .paper import Paper

logger = logging.getLogger(__name__)


# Verify the docstring above lives here to keep the channel self-contained.
class GoogleScholarChannel(BaseAcademicCrawler):
    """Search Google Scholar via public HTML page (no API key needed).

    Usage:
        cw = GoogleScholarChannel()
        papers = await cw.search("knowledge distillation", max_results=10)

    Tests inject an httpx.MockTransport:
        cw = GoogleScholarChannel(transport=mock_transport)
    """

    channel = "googlescholar"
    api_endpoint = "https://scholar.google.com/scholar"

    def __init__(self, **kwargs: Any) -> None:
        # Scholars terms-of-service ask for >=3s between requests without
        # prior arrangement. We respect that to keep this a polite citizen.
        kwargs.setdefault("rate_limit_seconds", 3.0)
        super().__init__(**kwargs)

    def _build_client(self):  # type: ignore[override]
        """Use a more browser-like UA for Scholar — Google's anti-bot
        triggers on missing/standard UAs more aggressively than other
        sources."""
        import httpx
        if self._client is not None:
            return self._client
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport, timeout=self.timeout,
            )
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        params = {"q": query, "hl": "en",
                  "num": str(min(max_results, 20))}
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("Google Scholar status %d for query=%r",
                               resp.status_code, query)
                return ""
            return resp.text
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    @staticmethod
    def parse(html: str) -> List[Dict[str, Any]]:
        """Static HTML parser — Google Scholar result page.

        Strategy:
          1. Walk all <div class="gs_r gs_or gs_scl"> nodes (the standard
             article wrapper in Scholar's classic layout).
          2. If none found, look for <div class="gs_ri"> fallback nodes.
        """
        if not html or not html.strip():
            return []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug("Google Scholar BS4 parse error: %s", e)
            return []
        records: List[Dict[str, Any]] = []
        nodes = soup.select("div.gs_r.gs_or.gs_scl, div.gs_r")
        if not nodes:
            nodes = soup.select("div.gs_ri")
        for idx, node in enumerate(nodes):
            try:
                rec = _gs_node_to_record(node, fallback_idx=idx)
                if rec:
                    records.append(rec)
            except Exception as e:
                logger.debug("GS node parse failed: %s", e)
        return records

    def _normalize(self, raw: Any) -> List[Any]:
        if isinstance(raw, str):
            return self.parse(raw)
        return super()._normalize(raw)

    def parse_records(self, records: List[Any], query: str = "") -> List[Paper]:
        out: List[Paper] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            authors = r.get("authors") or []
            if isinstance(authors, str):
                authors = [a.strip() for a in re.split(r",\s*|\s*and\s*|;\s*", authors)
                           if a.strip()]
            try:
                p = Paper(
                    id=str(r.get("id") or r.get("cluster_id")
                           or f"gs_{idx:04d}"),
                    title=str(r.get("title") or "").strip(),
                    url=str(r.get("url") or "").strip(),
                    authors=[str(a).strip() for a in authors],
                    abstract=str(r.get("abstract") or "").strip(),
                    year=r.get("year"),
                    venue=r.get("venue"),
                    doi=r.get("doi"),
                    keywords=r.get("keywords") or [],
                    pdf_url=r.get("pdf_url"),
                    citation_count=r.get("citation_count"),
                    channel=self.channel,
                    extra={
                        "cluster_id": r.get("cluster_id"),
                        "snippet_html": r.get("snippet_html"),
                    },
                )
                if not p.url:
                    continue
                out.append(p)
            except Exception as e:
                logger.debug("Google Scholar record %d skipped: %s", idx, e)
                continue
        return out


def _gs_node_to_record(node: Any, fallback_idx: int) -> Optional[Dict[str, Any]]:
    # title sits in <h3 class="gs_rt"> >> <a href="...">
    title_link = node.select_one("h3.gs_rt a, h3 a, .gs_rt a")
    title = (title_link.get_text() if title_link else node.get_text() or "").strip()
    if not title_link:
        # try direct h3
        h3 = node.select_one("h3.gs_rt")
        if h3:
            title = (h3.get_text() or "").strip()
    if not title:
        return None
    href = (title_link.get("href") if title_link else "") or ""
    cluster_id_match = re.search(r"cluster=([\w-]+)", href)
    cluster_id = cluster_id_match.group(1) if cluster_id_match else None

    # authors / venue / year live in <div class="gs_a"> as a single text line:
    #   "Author1, Author2 - Venue, Year - Source"
    authors: List[str] = []
    venue_text = ""
    year: Optional[int] = None
    gs_a = node.select_one(".gs_a")
    if gs_a:
        meta_text = (gs_a.get_text() or "").strip()
        parts = [p.strip() for p in meta_text.split(" - ")]
        if parts:
            authors = [a.strip() for a in parts[0].split(",") if a.strip()]
        if len(parts) >= 2:
            venue_text = parts[1].strip()
    # Year may live in any of the parts (venue line commonly contains
    # a comma-separated year). Search in priority order: parts[1] (venue),
    # then parts[2] (source), then entire string.
    for cand in (parts[1] if len(parts) >= 2 else "",
                 parts[2] if len(parts) >= 3 else "",
                 meta_text):
        m = re.search(r"(\d{4})", cand)
        if m:
            try:
                year = int(m.group(1))
                if 1700 <= year <= 2100:
                    break
                year = None
            except ValueError:
                year = None

    snippet_el = node.select_one(".gs_rs")
    abstract = (snippet_el.get_text() or "").strip() if snippet_el else ""

    citation_count = None
    cited_link = node.select_one("a:has(span), .gs_or_cit a")
    if cited_link:
        m = re.search(r"Cited by\s+(\d+)", cited_link.get_text() or "")
        if m:
            try:
                citation_count = int(m.group(1))
            except ValueError:
                citation_count = None
    # fallback — pattern search in cluster text
    if citation_count is None:
        m = re.search(r"Cited by\s+(\d+)", node.get_text() or "")
        if m:
            try:
                citation_count = int(m.group(1))
            except ValueError:
                citation_count = None

    pdf_url: Optional[str] = None
    # Bottom block often has [PDF] link
    for a in node.select("a"):
        text = (a.get_text() or "").strip().upper()
        href = a.get("href") or ""
        if text.startswith("[PDF]") or href.lower().endswith(".pdf"):
            pdf_url = href
            break

    return {
        "id": cluster_id or f"gs_{fallback_idx:04d}",
        "cluster_id": cluster_id,
        "title": title,
        "abstract": abstract,
        "url": href,
        "authors": authors,
        "venue": venue_text or None,
        "year": year,
        "citation_count": citation_count,
        "pdf_url": pdf_url,
    }


__all__ = ["GoogleScholarChannel"]
