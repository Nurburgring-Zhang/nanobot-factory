"""智影 V4 — 学术爬虫: arXiv/PubMed/Semantic Scholar/OpenReview/PapersWithCode"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class AcademicCrawler(BaseCrawler):
    """学术论文爬虫 — 5 大公开源"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    async def _ensure_client(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装")
            self._client = httpx.AsyncClient(
                timeout=60.0, follow_redirects=True, headers={"User-Agent": "IMDF-Crawler/4.0 (+academic)"}
            )
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """根据 url 域名自动路由"""
        start = time.time()
        if "arxiv.org" in url:
            return await self._fetch_arxiv(url, start)
        if "pubmed.ncbi.nlm.nih.gov" in url or "ncbi.nlm.nih.gov" in url:
            return await self._fetch_pubmed(url, start)
        if "api.semanticscholar.org" in url or "semanticscholar.org" in url:
            return await self._fetch_semantic_scholar(url, start)
        if "openreview.net" in url:
            return await self._fetch_openreview(url, start)
        if "paperswithcode.com" in url:
            return await self._fetch_paperswithcode(url, start)
        # 默认: arxiv
        return await self._fetch_arxiv(url, start)

    async def _fetch_arxiv(self, url: str, start: float) -> RawDocument:
        """arXiv — RSS 列表 or 单篇摘要"""
        client = await self._ensure_client()
        # 检测单篇 ID
        m = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", url)
        if m and not url.endswith(".rss"):
            arxiv_id = m.group(1)
            url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        elif "export.arxiv.org" not in url and "arxiv.org/list" not in url and "arxiv.org/rss" not in url:
            # 当作搜索
            query = self.config.selectors.get("query", url)
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={min(self.config.max_pages, 50)}"
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
        papers = self._parse_arxiv_xml(text)
        return RawDocument(
            url=url,
            type="xml",
            title=f"arXiv: {len(papers)} papers",
            text="\n\n".join(
                f"[{p['id']}] {p['title']}\n{p['authors']}\n{p['summary'][:500]}" for p in papers[:10]
            ),
            json={"papers": papers, "raw_xml": text[:10000]},
            source_metadata={"source": "arxiv", "count": len(papers)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    def _parse_arxiv_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """解析 arXiv API 返回的 Atom XML"""
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"arXiv XML parse failed: {e}")
            return []
        papers: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            paper = {
                "id": entry.findtext("atom:id", "", ns).split("/")[-1],
                "title": " ".join(entry.findtext("atom:title", "", ns).split()),
                "summary": " ".join(entry.findtext("atom:summary", "", ns).split()),
                "published": entry.findtext("atom:published", "", ns),
                "updated": entry.findtext("atom:updated", "", ns),
                "authors": ", ".join(
                    a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)
                ),
                "categories": [
                    c.get("term", "") for c in entry.findall("atom:category", ns)
                ],
                "pdf_url": "",
                "doi": entry.findtext("arxiv:doi", "", ns) or "",
                "journal_ref": entry.findtext("arxiv:journal_ref", "", ns) or "",
            }
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                    paper["pdf_url"] = link.get("href", "")
            papers.append(paper)
        return papers

    async def _fetch_pubmed(self, url: str, start: float) -> RawDocument:
        """PubMed E-utilities API"""
        client = await self._ensure_client()
        # 解析 PMID
        m = re.search(r"/(\d{6,9})(?:/|$|\?)", url)
        if m:
            pmid = m.group(1)
            # eFetch
            url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
        elif "eutils" not in url:
            # esearch
            query = self.config.selectors.get("query", "")
            if query:
                url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmax={min(self.config.max_pages, 50)}"
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
        # 简单解析: eFetch XML 提取 title/abstract
        papers: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            root = None
        if root is not None:
            tag = root.tag.split("}")[-1]
            if tag in ("PubmedArticleSet", "PubmedArticle"):
                # eFetch XML
                for art in root.iter("PubmedArticle"):
                    pmid_el = art.find(".//PMID")
                    title_el = art.find(".//ArticleTitle")
                    abst_el = art.find(".//Abstract/AbstractText")
                    authors = [
                        f"{a.findtext('ForeName', '')} {a.findtext('LastName', '')}"
                        for a in art.findall(".//AuthorList/Author")
                    ]
                    papers.append(
                        {
                            "pmid": pmid_el.text if pmid_el is not None else "",
                            "title": "".join(title_el.itertext()) if title_el is not None else "",
                            "abstract": "".join(abst_el.itertext()) if abst_el is not None else "",
                            "authors": ", ".join(a for a in authors if a.strip()),
                        }
                    )
            elif tag == "eSearchResult":
                # esearch XML → IdList
                id_list = [el.text for el in root.iter("Id")]
                papers = [{"pmid": pid} for pid in id_list]
        return RawDocument(
            url=url,
            type="xml",
            title=f"PubMed: {len(papers)} entries",
            text="\n\n".join(
                f"[{p.get('pmid', '?')}] {p.get('title', '')}\n{p.get('abstract', '')[:500]}" for p in papers[:10]
            ),
            json={"papers": papers, "raw_xml": text[:10000]},
            source_metadata={"source": "pubmed", "count": len(papers)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_semantic_scholar(self, url: str, start: float) -> RawDocument:
        """Semantic Scholar Graph API"""
        client = await self._ensure_client()
        api_key = self.config.selectors.get("api_key", os.getenv("S2_API_KEY", ""))
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        # 解析 paperId
        m = re.search(r"/paper/([^/?#]+)", url)
        if not m and "api.semanticscholar.org" not in url:
            query = self.config.selectors.get("query", "")
            url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit={min(self.config.max_pages, 100)}&fields=title,abstract,authors,year,venue,citationCount,referenceCount,externalIds,url"
        else:
            paper_id = m.group(1) if m else None
            if paper_id:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=title,abstract,authors,year,venue,citationCount,referenceCount,references.title,references.year,citations.title,citations.year,externalIds,url,tldr"
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        papers: List[Dict[str, Any]] = []
        if "data" in data:
            # 搜索
            for item in data.get("data", []):
                papers.append(
                    {
                        "paperId": item.get("paperId", ""),
                        "title": item.get("title", ""),
                        "abstract": item.get("abstract", ""),
                        "year": item.get("year"),
                        "venue": item.get("venue", ""),
                        "citationCount": item.get("citationCount", 0),
                        "authors": [a.get("name", "") for a in item.get("authors", [])],
                        "externalIds": item.get("externalIds", {}),
                    }
                )
        else:
            # 单篇
            papers.append(
                {
                    "paperId": data.get("paperId", ""),
                    "title": data.get("title", ""),
                    "abstract": data.get("abstract", "") or (data.get("tldr", {}) or {}).get("text", ""),
                    "year": data.get("year"),
                    "venue": data.get("venue", ""),
                    "citationCount": data.get("citationCount", 0),
                    "authors": [a.get("name", "") for a in data.get("authors", [])],
                    "references": [r.get("title", "") for r in data.get("references", [])],
                    "citations": [c.get("title", "") for c in data.get("citations", [])],
                    "externalIds": data.get("externalIds", {}),
                }
            )
        return RawDocument(
            url=url,
            type="json",
            title=f"Semantic Scholar: {len(papers)} papers",
            text="\n\n".join(
                f"[{p.get('year', '?')}] {p.get('title', '')}\n{p.get('abstract', '')[:500]}" for p in papers[:10]
            ),
            json={"papers": papers, "raw": data},
            source_metadata={"source": "semantic_scholar", "count": len(papers)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_openreview(self, url: str, start: float) -> RawDocument:
        """OpenReview API v2"""
        client = await self._ensure_client()
        # 提取 forum id
        m = re.search(r"forum=([A-Za-z0-9_-]+)", url) or re.search(r"/forum/([A-Za-z0-9_-]+)", url) or re.search(
            r"/id/([A-Za-z0-9_-]+)", url
        )
        if m:
            forum_id = m.group(1)
            url = f"https://api.openreview.net/notes?forum={forum_id}"
        elif "api.openreview.net" not in url:
            # 搜索
            query = self.config.selectors.get("query", "")
            url = f"https://api.openreview.net/notes/search?query={query}&limit={min(self.config.max_pages, 50)}"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        notes = data.get("notes", []) if isinstance(data, dict) else data
        papers: List[Dict[str, Any]] = []
        for n in notes[: self.config.max_pages]:
            content = n.get("content", {})
            papers.append(
                {
                    "id": n.get("id", ""),
                    "title": content.get("title", ""),
                    "abstract": content.get("abstract", ""),
                    "authors": content.get("authors", []),
                    "venue": content.get("venue", ""),
                    "year": content.get("year", ""),
                    "keywords": content.get("keywords", []),
                }
            )
        return RawDocument(
            url=url,
            type="json",
            title=f"OpenReview: {len(papers)} papers",
            text="\n\n".join(
                f"[{p.get('year', '?')}] {p.get('title', '')}\n{p.get('abstract', '')[:500]}" for p in papers[:10]
            ),
            json={"papers": papers, "raw": data},
            source_metadata={"source": "openreview", "count": len(papers)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_paperswithcode(self, url: str, start: float) -> RawDocument:
        """Papers with Code API"""
        client = await self._ensure_client()
        # 简单 graphQL 风格 → PWC 实际是 REST
        if "paperswithcode.com/api" not in url:
            query = self.config.selectors.get("query", "")
            url = f"https://paperswithcode.com/api/v1/papers/?q={query}&page_size={min(self.config.max_pages, 50)}"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        papers: List[Dict[str, Any]] = []
        for item in results:
            papers.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "abstract": item.get("abstract", ""),
                    "url_abs": item.get("url_abs", ""),
                    "url_pdf": item.get("url_pdf", ""),
                    "proceeding": item.get("proceeding", ""),
                    "authors": [a.get("name", "") for a in item.get("authors", [])],
                    "published": item.get("published", ""),
                }
            )
        return RawDocument(
            url=url,
            type="json",
            title=f"PapersWithCode: {len(papers)} papers",
            text="\n\n".join(
                f"[{p.get('published', '?')[:10]}] {p.get('title', '')}\n{p.get('abstract', '')[:500]}" for p in papers[:10]
            ),
            json={"papers": papers, "raw": data},
            source_metadata={"source": "paperswithcode", "count": len(papers)},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
