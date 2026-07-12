"""PubMed crawler channel (P20-D).

NCBI E-utilities API — no key required for low-volume use.

Two-step lookup:
    Step 1 — esearch
        GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
            ?db=pubmed&term={query}&retmax={N}&retmode=json
        Returns: {"esearchresult": {"idlist": ["12345", ...]}}

    Step 2 — esummary (optional, batched in one call for multiple ids)
        GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi
            ?db=pubmed&id=123,124,125&retmode=json
        Returns: {"result": {"12345": {title, sortfirstauthor, ...},
                              "uids": [...]}}

We always do the second step because the title alone is not useful — the
esummary output is what powers parse_records().

Rate limit: per NCBI guideline, no more than 3 requests/sec without an
API key. We use 1.0s to be safe + respect the no-key path.

We accept an optional `email` constructor arg which NCBI requests when an
API key is also provided — without a key, the email is ignored by NCBI
but we forward it as a courtesy.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import BaseAcademicCrawler
from .paper import Paper

logger = logging.getLogger(__name__)


class PubMedChannel(BaseAcademicCrawler):
    """Search PubMed via NCBI E-utilities.

    Usage:
        cw = PubMedChannel(email="me@example.com")  # email is optional
        papers = await cw.search("covid vaccine", max_results=10)
    """

    channel = "pubmed"
    api_endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    def __init__(self, email: Optional[str] = None,
                 tool: str = "nanobot-factory",
                 **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_seconds", 1.0)
        super().__init__(**kwargs)
        self.email = email
        self.tool = tool

    def _common_params(self) -> Dict[str, str]:
        p: Dict[str, str] = {"db": "pubmed", "retmode": "json"}
        if self.email:
            p["email"] = self.email
        if self.tool:
            p["tool"] = self.tool
        return p

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        # step 1: search for ids
        ids = await self._esearch(query, max_results)
        if not ids:
            return []
        # step 2: summary for ids
        records = await self._esummary(ids)
        return records

    async def _esearch(self, query: str, max_results: int) -> List[str]:
        params = self._common_params()
        params.update({
            "term": query,
            "retmax": str(max_results),
        })
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("PubMed esearch status %d for query=%r",
                               resp.status_code, query)
                return []
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("PubMed esearch failed for query=%r: %s", query, e)
            return []
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)
        if not isinstance(data, dict):
            return []
        res = data.get("esearchresult") or {}
        if isinstance(res, dict):
            idlist = res.get("idlist") or []
            if isinstance(idlist, list):
                return [str(x) for x in idlist if x]
        return []

    async def _esummary(self, ids: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        params = self._common_params()
        params["id"] = ",".join(ids)
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?{urllib.parse.urlencode(params)}"
        )
        client = self._build_client()
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("PubMed esummary status %d for ids=%s",
                               resp.status_code, ids[:3])
                return []
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("PubMed esummary failed: %s", e)
            return []
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)
        if not isinstance(data, dict):
            return []
        result = data.get("result") or {}
        if not isinstance(result, dict):
            return []
        uids = result.get("uids") or []
        out: List[Dict[str, Any]] = []
        for uid in uids:
            record = result.get(str(uid))
            if isinstance(record, dict):
                record["_pmid"] = str(uid)
                out.append(record)
        return out

    def _normalize(self, raw: Any) -> List[Any]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            res = raw.get("esearchresult")
            if isinstance(res, dict):
                idlist = res.get("idlist")
                if isinstance(idlist, list):
                    return [{"pmid": str(x)} for x in idlist if x]
        return []

    def parse_records(self, records: List[Any], query: str = "") -> List[Paper]:
        out: List[Paper] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            pmid = (
                r.get("_pmid")
                or r.get("pmid")
                or r.get("uid")
                or ""
            )
            if isinstance(pmid, list):
                pmid = pmid[0] if pmid else ""
            pmid = str(pmid).strip()
            title = (r.get("title") or "").strip()
            if pmid:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            else:
                url = ""
            authors = _parse_pubmed_authors(r)
            # PubMed esummary rarely includes abstract; we leave empty.
            abstract = ""
            year = _extract_year(r.get("pubdate") or r.get("sortpubdate"))
            venue = str(r.get("fulljournalname") or r.get("source") or "").strip() or None
            doi = _extract_doi(r.get("articleids") or [])
            keywords_raw = r.get("keywords")
            if isinstance(keywords_raw, list):
                keywords = [_mesh_label(k) for k in keywords_raw if k]
            elif isinstance(keywords_raw, str):
                keywords = [t.strip() for t in keywords_raw.split(";") if t.strip()]
            else:
                keywords = []
            try:
                p = Paper(
                    id=f"pmid:{pmid}" if pmid else f"pubmed_{idx}",
                    title=title or f"PMID:{pmid}",
                    url=url,
                    authors=authors,
                    abstract=str(abstract or "").strip(),
                    year=year,
                    venue=venue,
                    doi=doi,
                    keywords=keywords,
                    channel=self.channel,
                    extra={
                        "pmid": pmid,
                        "pubdate": r.get("pubdate"),
                        "sortpubdate": r.get("sortpubdate"),
                        "issue": r.get("issue"),
                        "volume": r.get("volume"),
                        "pages": r.get("pages"),
                        "language": r.get("lang"),
                        "publication_types": r.get("pubtype") or [],
                    },
                )
                if not p.url:
                    continue
                out.append(p)
            except Exception as e:
                logger.debug("PubMed record %d skipped: %s", idx, e)
                continue
        return out


def _parse_pubmed_authors(r: Dict[str, Any]) -> List[str]:
    authors = r.get("authors") or []
    if isinstance(authors, list):
        names: List[str] = []
        for a in authors:
            if isinstance(a, dict):
                nm = a.get("name") or a.get("authtype")
                if nm:
                    names.append(str(nm).strip())
            elif isinstance(a, str) and a.strip():
                names.append(a.strip())
        if names:
            return [n for n in names if n]
    authorlist = r.get("authorlist")
    if isinstance(authorlist, dict):
        complete = authorlist.get("complete")
        if isinstance(complete, str) and complete:
            return [a.strip() for a in complete.split(";") if a.strip()]
    return []


def _extract_year(s: Any) -> Optional[int]:
    if not s:
        return None
    if not isinstance(s, str):
        s = str(s)
    m = re.search(r"(\d{4})", s)
    if m:
        try:
            y = int(m.group(1))
            if 1700 <= y <= 2100:
                return y
        except ValueError:
            return None
    return None


def _extract_doi(ids: Any) -> Optional[str]:
    if not isinstance(ids, list):
        return None
    for it in ids:
        if not isinstance(it, dict):
            continue
        idtype = (it.get("idtype") or "").lower()
        value = (it.get("value") or "").strip()
        if idtype == "doi" and value:
            return value
    return None


def _mesh_label(k: Any) -> str:
    if isinstance(k, dict):
        return str(k.get("name") or k.get("descriptorname") or "").strip()
    return str(k).strip()


__all__ = ["PubMedChannel"]
