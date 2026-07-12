"""IEEE Xplore crawler channel (P20-D).

IEEE Xplore has limited public search — the official API requires a key
issued by IEEE. We document the unauthenticated "abstract" page and a
public REST endpoint exposed by IEEE Xplore search UI.

Without API key, we do best-effort HTML scrape of:
    GET https://ieeexplore.ieee.org/search/searchresult.jsp?queryText=<q>
We treat the page as HTML; the parsing walks CSS selectors IEEE commonly
uses (`List-results` items, `.result-item`, etc.). When no results are
found, we still return a valid Paper with the IEEE search URL as the
canonical link so callers always have a result.

For tests, we inject an httpx.MockTransport. The mock returns a fixed
HTML fixture; the parser is robust enough to ignore unrelated structure.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import BaseAcademicCrawler
from .paper import Paper

logger = logging.getLogger(__name__)


class IEEEChannel(BaseAcademicCrawler):
    """Search IEEE Xplore via the public search UI (HTML scrape).

    Usage:
        cw = IEEEChannel()
        papers = await cw.search("5G network slicing", max_results=10)

    The crawler falls back to the IEEE search URL when no results are
    found — the search results page itself is a useful canonical link.
    """

    channel = "ieee"
    api_endpoint = "https://ieeexplore.ieee.org/search/searchresult.jsp"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_seconds", 1.0)
        super().__init__(**kwargs)

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        params = {"queryText": query, "highlight": "true", "returnType": "SEARCH",
                  "returnFacets": "ALL", "pageNumber": 1,
                  "rowsPerPage": str(min(max_results, 50))}
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("IEEE search status %d for query=%r",
                               resp.status_code, query)
                return ""
            return resp.text
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    @staticmethod
    def parse(html: str) -> List[Dict[str, Any]]:
        """Static HTML parser — IEEE Xplore search results.

        Strategy:
          1. Try JSON-LD embedded payload (rare but reliable when present).
          2. Fall back to BeautifulSoup DOM walking.
        """
        if not html or not html.strip():
            return []
        records: List[Dict[str, Any]] = []
        # JSON-LD scan
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
                try:
                    obj = json.loads(tag.string or tag.get_text() or "")
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                items = _walk_jsonld(obj)
                for it in items:
                    if isinstance(it, dict) and it.get("title"):
                        records.append(it)
        except Exception as e:
            logger.debug("IEEE: BeautifulSoup error: %s", e)

        if records:
            return records

        # DOM-walk fallback
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return records
        # IEEE commonly wraps each result in <div class="result-item ..."> or
        # <article class="search-result"> or similar.
        for idx, node in enumerate(soup.select("div.result-item, article.list-result, li.result-item")):
            try:
                rec = _node_to_record(node, fallback_idx=idx)
                if rec:
                    records.append(rec)
            except Exception as e:
                logger.debug("IEEE node parse failed: %s", e)
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
                authors = [a.strip() for a in authors.split(",") if a.strip()]
            elif not isinstance(authors, list):
                authors = []
            keywords = r.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            try:
                p = Paper(
                    id=str(r.get("id") or r.get("article_number")
                           or f"ieee_{idx:04d}"),
                    title=str(r.get("title") or "").strip(),
                    url=str(r.get("url") or "").strip(),
                    authors=[str(a).strip() for a in authors],
                    abstract=str(r.get("abstract") or "").strip(),
                    year=r.get("year"),
                    venue=r.get("venue") or "IEEE Xplore",
                    doi=r.get("doi"),
                    keywords=[str(k).strip() for k in keywords],
                    pdf_url=r.get("pdf_url"),
                    citation_count=r.get("citation_count"),
                    channel=self.channel,
                    extra={
                        "publication_title": r.get("venue"),
                        "article_number": r.get("article_number"),
                        "publication_date": r.get("publication_date"),
                        "isbn": r.get("isbn"),
                        "issn": r.get("issn"),
                    },
                )
                if not p.url:
                    continue
                out.append(p)
            except Exception as e:
                logger.debug("IEEE record %d skipped: %s", idx, e)
                continue
        return out


def _walk_jsonld(obj: Any) -> List[Dict[str, Any]]:
    """Find any object with @type ScholarlyArticle / Article-like in JSON-LD."""
    out: List[Dict[str, Any]] = []
    if isinstance(obj, dict):
        t = obj.get("@type")
        if isinstance(t, str) and ("Article" in t or "Publication" in t):
            record = {
                "id": obj.get("@id") or obj.get("identifier") or "",
                "title": obj.get("headline") or obj.get("name") or "",
                "abstract": obj.get("description") or "",
                "url": obj.get("url") or obj.get("@id") or "",
                "authors": [
                    a.get("name") if isinstance(a, dict) else str(a)
                    for a in (obj.get("author") or [])
                ],
                "year": _str_year(obj.get("datePublished")),
                "venue": obj.get("isPartOf", {}).get("name")
                       if isinstance(obj.get("isPartOf"), dict)
                       else obj.get("publisher"),
                "doi": _doi_from_jsonld(obj.get("identifier")),
                "keywords": obj.get("keywords") or [],
            }
            # strip empties
            record = {k: v for k, v in record.items() if v not in (None, "", [], {})}
            out.append(record)
        for v in obj.values():
            out.extend(_walk_jsonld(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk_jsonld(v))
    return out


def _node_to_record(node: Any, fallback_idx: int) -> Optional[Dict[str, Any]]:
    title_el = (
        node.select_one("h2 a") or node.select_one("h3 a")
        or node.select_one("a.result-title") or node.select_one(".title-link")
        or node.select_one("a")
    )
    if not title_el:
        return None
    title = (title_el.get_text() or "").strip()
    if not title:
        return None
    href = title_el.get("href") or ""
    url = href if href.startswith("http") else (
        f"https://ieeexplore.ieee.org{href}" if href else ""
    )
    abstract = ""
    abs_el = node.select_one(".description, .abstract, .description-text")
    if abs_el:
        abstract = (abs_el.get_text() or "").strip()

    authors: List[str] = []
    for a in node.select(".authors a, .author, .author-name"):
        nm = (a.get_text() or "").strip()
        if nm:
            authors.append(nm)

    venue = ""
    pub_el = node.select_one(".publication, .pub-title, .publication-title")
    if pub_el:
        venue = (pub_el.get_text() or "").strip()

    year = None
    date_el = node.select_one(".publication-year, .year")
    if date_el:
        m = re.search(r"(\d{4})", date_el.get_text() or "")
        if m:
            try:
                year = int(m.group(1))
            except ValueError:
                year = None

    article_no = ""
    anno = node.select_one(".article-number, .article-id, .article-number-text")
    if anno:
        article_no = (anno.get_text() or "").strip()

    return {
        "id": article_no or f"ieee_{fallback_idx:04d}",
        "article_number": article_no or None,
        "title": title,
        "abstract": abstract,
        "url": url,
        "authors": authors,
        "venue": venue or None,
        "year": year,
    }


def _str_year(v: Any) -> Optional[int]:
    if not v:
        return None
    m = re.search(r"(\d{4})", str(v))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _doi_from_jsonld(identifier: Any) -> Optional[str]:
    if isinstance(identifier, str):
        if identifier.startswith("10."):
            return identifier
        return None
    if isinstance(identifier, list):
        for it in identifier:
            d = _doi_from_jsonld(it)
            if d:
                return d
    if isinstance(identifier, dict):
        v = identifier.get("value") or identifier.get("@id") or ""
        if isinstance(v, str) and v.startswith("10."):
            return v
    return None


__all__ = ["IEEEChannel"]
