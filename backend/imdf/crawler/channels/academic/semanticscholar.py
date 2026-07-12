"""Semantic Scholar crawler channel (P20-D).

Public API:
    GET https://api.semanticscholar.org/graph/v1/paper/search
        ?query=<query>&limit=<N>&fields=title,abstract,authors,year,venue,
                            externalIds,url,citationCount,openAccessPdf

No API key required for the `paper/search` endpoint at modest volume.
We use this entrypoint; rate limit per the public docs is around 1 req/sec
without a key.

Response shape:
    {
      "total": 1234,
      "offset": 0,
      "next": 25,
      "data": [
        {
          "paperId": "...",
          "title": "...",
          "abstract": "...",   (may be missing for newer entries)
          "year": 2023,
          "venue": "ACL",
          "externalIds": {"DOI": "10.1234/...", "ArXiv": "..."},
          "url": "https://www.semanticscholar.org/paper/<hash>",
          "citationCount": 12,
          "authors": [{"authorId": "...", "name": "..."}, ...],
          "openAccessPdf": {"url": "https://..."}
        },
        ...
      ]
    }
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from . import BaseAcademicCrawler
from .paper import Paper

logger = logging.getLogger(__name__)


# Fields we request from the API — keeps the response payload small.
_FIELDS = (
    "title,abstract,authors,year,venue,externalIds,"
    "url,citationCount,openAccessPdf,publicationDate"
)


class SemanticScholarChannel(BaseAcademicCrawler):
    """Search Semantic Scholar via the public Graph API.

    Usage:
        cw = SemanticScholarChannel()
        papers = await cw.search("transformer architecture", max_results=10)

    Tests inject an httpx.MockTransport:
        cw = SemanticScholarChannel(transport=mock_transport)
    """

    channel = "semanticscholar"
    api_endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_seconds", 1.0)
        super().__init__(**kwargs)

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        params = {
            "query": query,
            "limit": str(max_results),
            "fields": _FIELDS,
        }
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("Semantic Scholar API status %d for query=%r",
                               resp.status_code, query)
                return {}
            try:
                return resp.json()
            except Exception as e:
                logger.warning("Semantic Scholar JSON parse failed: %s", e)
                return {}
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    def parse_records(self, records: List[Any], query: str = "") -> List[Paper]:
        out: List[Paper] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            paper_id = str(r.get("paperId") or r.get("corpusId")
                           or f"ss_{idx:04d}")
            title = str(r.get("title") or "").strip()
            if not title:
                continue
            url = str(r.get("url") or r.get("openAccessPdf", {}).get("url")
                      or f"https://www.semanticscholar.org/paper/{paper_id}")

            authors_raw = r.get("authors") or []
            authors: List[str] = []
            if isinstance(authors_raw, list):
                for a in authors_raw:
                    if isinstance(a, dict):
                        nm = a.get("name")
                        if nm:
                            authors.append(str(nm).strip())
                    elif isinstance(a, str):
                        if a.strip():
                            authors.append(a.strip())

            abstract = str(r.get("abstract") or "").strip()

            year = r.get("year")
            try:
                year_int = int(year) if year is not None and year != "" else None
            except (TypeError, ValueError):
                year_int = None

            venue = str(r.get("venue") or "").strip() or None

            external = r.get("externalIds") or {}
            doi = None
            arxiv_id = None
            if isinstance(external, dict):
                doi = external.get("DOI") or None
                arxiv_id = external.get("ArXiv") or None

            open_pdf = r.get("openAccessPdf") or {}
            pdf_url = None
            if isinstance(open_pdf, dict):
                pdf_url = open_pdf.get("url") or None

            citation_count = r.get("citationCount")

            try:
                p = Paper(
                    id=f"ss:{paper_id}" if paper_id else f"semanticscholar_{idx}",
                    title=title,
                    url=url,
                    authors=authors,
                    abstract=abstract,
                    year=year_int,
                    venue=venue,
                    doi=doi,
                    keywords=[],  # S2 search endpoint does not return tags
                    pdf_url=pdf_url,
                    citation_count=citation_count,
                    channel=self.channel,
                    extra={
                        "paper_id": paper_id,
                        "arxiv_id": arxiv_id,
                        "publication_date": r.get("publicationDate"),
                        "corpus_id": r.get("corpusId"),
                    },
                )
                out.append(p)
            except Exception as e:
                logger.debug("Semantic Scholar record %d skipped: %s", idx, e)
                continue
        return out


__all__ = ["SemanticScholarChannel"]
