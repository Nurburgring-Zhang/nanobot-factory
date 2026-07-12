"""ArXiv paper crawler channel (P20-D).

ArXiv public Atom API:
    GET http://export.arxiv.org/api/query?search_query=all:<q>&start=0&max_results=N

Response shape (real API):
    Atom XML feed. Each <entry> contains:
        - <id>            e.g. "http://arxiv.org/abs/1234.5678v1"
        - <title>         paper title (possibly with embedded newlines / spaces)
        - <summary>       abstract
        - <author><name>  author names
        - <published>     ISO datetime
        - <updated>       ISO datetime
        - <arxiv:doi>     optional DOI
        - <arxiv:journal_ref> optional journal ref
        - <category>      arxiv category term

No API key required; rate limit per arxiv.org guideline is 1 request every
3 seconds. We use 1.0s to keep tests fast; production users should raise
this to 3.0+ to stay friendly.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import BaseAcademicCrawler
from .paper import Paper

logger = logging.getLogger(__name__)

_ARXIV_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivChannel(BaseAcademicCrawler):
    """Search arXiv via the public Atom API.

    Usage:
        cw = ArxivChannel()
        papers = await cw.search("diffusion model", max_results=10)

    Tests inject an httpx.MockTransport:
        cw = ArxivChannel(transport=mock_transport)
    """

    channel = "arxiv"
    api_endpoint = "http://export.arxiv.org/api/query"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_seconds", 1.0)
        super().__init__(**kwargs)

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("arXiv API status %d for query=%r",
                               resp.status_code, query)
                return ""
            return resp.text
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    @staticmethod
    def parse(html: str) -> List[Dict[str, Any]]:
        """Static parser — turn a raw Atom XML feed body into a list of dict
        records. This is split out so tests can call it without spinning up
        an httpx client."""
        if not html or not html.strip():
            return []
        records: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(html)
        except ET.ParseError as e:
            logger.debug("arXiv: atom parse error: %s", e)
            return records
        for entry in root.findall(f"{_ARXIV_ATOM_NS}entry"):
            try:
                rec = _entry_to_record(entry)
                if rec:
                    records.append(rec)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("arXiv entry parse failed: %s", e)
                continue
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
            authors = list(r.get("authors") or [])
            keywords = list(r.get("categories") or [])
            try:
                p = Paper(
                    id=str(r.get("id") or r.get("arxiv_id") or f"arxiv_{idx}"),
                    title=str(r.get("title") or "").strip(),
                    url=str(r.get("url") or "").strip(),
                    authors=authors,
                    abstract=str(r.get("abstract") or "").strip(),
                    year=_safe_year(r.get("published")),
                    venue="arXiv",
                    doi=r.get("doi") or None,
                    keywords=keywords,
                    pdf_url=r.get("pdf_url") or None,
                    channel=self.channel,
                    extra={
                        "arxiv_id": r.get("arxiv_id"),
                        "updated": r.get("updated"),
                        "journal_ref": r.get("journal_ref"),
                        "comment": r.get("comment"),
                    },
                )
                if not p.id or not p.url:
                    continue
                out.append(p)
            except Exception as e:
                logger.debug("arXiv record %d skipped: %s", idx, e)
                continue
        return out


def _entry_to_record(entry: Any) -> Optional[Dict[str, Any]]:
    """Convert one arxiv Atom entry element into a flat dict."""
    raw_id = (entry.findtext(f"{_ARXIV_ATOM_NS}id") or "").strip()
    if not raw_id:
        return None
    # The id form is http://arxiv.org/abs/1234.5678vN
    arxiv_id = raw_id.rsplit("/", 1)[-1]
    url = f"https://arxiv.org/abs/{arxiv_id}"

    title = (entry.findtext(f"{_ARXIV_ATOM_NS}title") or "").strip()
    # arxiv title may contain double newlines; collapse to single space.
    title = re.sub(r"\s+", " ", title)

    abstract = (entry.findtext(f"{_ARXIV_ATOM_NS}summary") or "").strip()
    abstract = re.sub(r"\s+", " ", abstract)

    authors: List[str] = []
    for a in entry.findall(f"{_ARXIV_ATOM_NS}author"):
        nm = (a.findtext(f"{_ARXIV_ATOM_NS}name") or "").strip()
        if nm:
            authors.append(nm)

    cats: List[str] = []
    for c in entry.findall(f"{_ARXIV_ATOM_NS}category"):
        term = c.attrib.get("term") if hasattr(c, "attrib") else None
        if term:
            cats.append(term)

    doi_el = entry.find(f"{_ARXIV_NS}doi")
    doi = (doi_el.text or "").strip() if doi_el is not None and doi_el.text else ""

    jref_el = entry.find(f"{_ARXIV_NS}journal_ref")
    jref = (jref_el.text or "").strip() if jref_el is not None and jref_el.text else ""

    comment_el = entry.find(f"{_ARXIV_NS}comment")
    comment = (comment_el.text or "").strip() if comment_el is not None and comment_el.text else ""

    pdf_url = ""
    for link in entry.findall(f"{_ARXIV_ATOM_NS}link"):
        href = link.attrib.get("href", "")
        title_attr = link.attrib.get("title", "")
        if title_attr.lower() == "pdf" or href.endswith(".pdf"):
            pdf_url = href
            break

    published = (entry.findtext(f"{_ARXIV_ATOM_NS}published") or "").strip()
    updated = (entry.findtext(f"{_ARXIV_ATOM_NS}updated") or "").strip()

    return {
        "id": arxiv_id,
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "url": url,
        "authors": authors,
        "categories": cats,
        "doi": doi or None,
        "journal_ref": jref or None,
        "comment": comment or None,
        "pdf_url": pdf_url or None,
        "published": published,
        "updated": updated,
    }


def _safe_year(s: Any) -> Optional[int]:
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).year
    except (ValueError, TypeError):
        m = re.search(r"(\d{4})", s)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None


__all__ = ["ArxivChannel"]
