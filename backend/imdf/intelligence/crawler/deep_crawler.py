"""智影 V4 — 深度爬虫: BFS/DFS 站点遍历 + 学术引用链"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from typing import Any, AsyncIterator, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, ChannelType, RawDocument

logger = logging.getLogger(__name__)


class DeepCrawler(BaseCrawler):
    """深度爬虫 — BFS/DFS 全站遍历 + 引用链追踪"""

    STRATEGIES = ("bfs", "dfs", "citation")

    def __init__(self, config: CrawlerConfig):
        if config.channel_type == ChannelType.DEEP_BFS:
            config.channel_type = ChannelType.WEB_GENERIC
        super().__init__(config)
        self._client: Optional[Any] = None
        self._strategy: str = config.selectors.get("strategy", "bfs")
        self._seen: Set[str] = set()
        self._max_depth = config.max_depth or 3
        self._max_pages = config.max_pages or 100

    async def _ensure_client(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装")
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """单 URL 抓取 — 由 deep_crawl 调度"""
        start = time.time()
        client = await self._ensure_client()
        resp = await client.get(url, headers={"User-Agent": "IMDF-Crawler/4.0 (+deep)"})
        resp.raise_for_status()
        html = resp.text
        doc = RawDocument(
            url=url,
            type="html",
            html=html,
            http_status=resp.status_code,
            crawl_duration_ms=(time.time() - start) * 1000,
        )
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "lxml")
            if soup.title:
                doc.title = (soup.title.string or "").strip()[:500]
            body = soup.find("body")
            if body:
                doc.text = body.get_text(separator="\n", strip=True)[:50000]
            if self.config.extract_links:
                doc.links = _extract_links_bs(soup, url)
        return doc

    async def deep_crawl(self, seed_urls: List[str]) -> AsyncIterator[RawDocument]:
        """深度遍历 — BFS/DFS/citation"""
        if self._strategy == "citation":
            async for d in self._crawl_citation(seed_urls):
                yield d
            return
        if self._strategy == "dfs":
            async for d in self._crawl_dfs(seed_urls):
                yield d
            return
        # 默认 BFS
        async for d in self._crawl_bfs(seed_urls):
            yield d

    async def _crawl_bfs(self, seed_urls: List[str]) -> AsyncIterator[RawDocument]:
        queue: deque = deque([(u, 0) for u in seed_urls])
        while queue and self.metrics.pages_crawled < self._max_pages:
            url, depth = queue.popleft()
            if url in self._seen or depth > self._max_depth:
                continue
            if not self._compliance_check(url):
                self.metrics.pages_blocked += 1
                continue
            self._seen.add(url)
            await self._rate_limit()
            try:
                doc = await self.fetch(url)
                doc.crawled_at = _now()
                doc.source_channel = self.config.channel_type.value
                doc.compute_hash()
                self.metrics.pages_crawled += 1
                self.metrics.unique_domains.add(urlparse(url).netloc)
                yield doc
                if depth < self._max_depth:
                    for link in doc.links:
                        if link not in self._seen and self._should_follow(link, url):
                            queue.append((link, depth + 1))
            except Exception as e:
                self.metrics.pages_failed += 1
                self.metrics.errors.append(f"{url}: {e}")
                logger.warning(f"Deep BFS failed {url}: {e}")

    async def _crawl_dfs(self, seed_urls: List[str]) -> AsyncIterator[RawDocument]:
        stack: List[tuple] = [(u, 0) for u in seed_urls]
        while stack and self.metrics.pages_crawled < self._max_pages:
            url, depth = stack.pop()
            if url in self._seen or depth > self._max_depth:
                continue
            if not self._compliance_check(url):
                self.metrics.pages_blocked += 1
                continue
            self._seen.add(url)
            await self._rate_limit()
            try:
                doc = await self.fetch(url)
                doc.crawled_at = _now()
                doc.source_channel = self.config.channel_type.value
                doc.compute_hash()
                self.metrics.pages_crawled += 1
                self.metrics.unique_domains.add(urlparse(url).netloc)
                yield doc
                if depth < self._max_depth:
                    for link in doc.links:
                        if link not in self._seen and self._should_follow(link, url):
                            stack.append((link, depth + 1))
            except Exception as e:
                self.metrics.pages_failed += 1
                self.metrics.errors.append(f"{url}: {e}")
                logger.warning(f"Deep DFS failed {url}: {e}")

    async def _crawl_citation(self, seed_urls: List[str]) -> AsyncIterator[RawDocument]:
        """引用链追踪 — 提取页面中的 DOI/arXiv 链接,递归拉摘要"""
        from .academic_crawler import AcademicCrawler
        for url in seed_urls:
            doc = await self.fetch(url)
            doc.source_channel = self.config.channel_type.value
            yield doc
            # 提取 DOI
            dois = re.findall(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", doc.html, re.IGNORECASE)
            dois = list(set(dois))[: self.config.max_pages]
            # 提取 arXiv
            arxiv_ids = re.findall(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", doc.html, re.IGNORECASE)
            arxiv_ids = list(set(arxiv_ids))[: self.config.max_pages]
            # 学术接口拉取
            academic_config = CrawlerConfig(
                name="citation",
                channel_type=ChannelType.ACADEMIC_ARXIV,
                max_pages=5,
            )
            academic = AcademicCrawler(academic_config)
            for aid in arxiv_ids:
                try:
                    abs_doc = await academic.fetch(f"https://arxiv.org/abs/{aid}")
                    abs_doc.source_metadata["via_citation_from"] = url
                    yield abs_doc
                except Exception as e:
                    logger.debug(f"Citation {aid} failed: {e}")
            await academic.close()

    def _should_follow(self, link: str, source_url: str) -> bool:
        """是否跟随链接 — 同域过滤 + 模式匹配"""
        if self.config.same_domain_only:
            if urlparse(link).netloc != urlparse(source_url).netloc:
                return False
        if self.config.url_include_patterns:
            if not any(re.search(p, link) for p in self.config.url_include_patterns):
                return False
        if self.config.url_exclude_patterns:
            if any(re.search(p, link) for p in self.config.url_exclude_patterns):
                return False
        # 跳过非内容
        if any(link.lower().endswith(ext) for ext in (".pdf", ".zip", ".jpg", ".png", ".gif", ".mp4", ".mp3", ".css", ".js")):
            return False
        return True

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def _extract_links_bs(soup: Any, base_url: str) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(base_url, href)
        elif not href.startswith(("http://", "https://")):
            href = urljoin(base_url, href)
        if href not in seen:
            seen.add(href)
            result.append(href)
    return result[:500]


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
