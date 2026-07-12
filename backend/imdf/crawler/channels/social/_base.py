"""Shared primitives for public social search crawler channels.

The social channels in this package intentionally use only public search pages or
read-only public endpoints. They collect metadata snippets for discovery and data
triage; callers remain responsible for source-site terms, attribution, and any
follow-up licensing checks before downloading or reusing content.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime
from typing import Any, ClassVar, Iterable

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

try:  # Task spec names these symbols in _schemas; older repo only has CrawledItemModel.
    from .._schemas import BaseCrawlerChannel as BaseCrawlerChannel  # type: ignore
except ImportError:  # pragma: no cover - compatibility shim for this codebase snapshot
    class BaseCrawlerChannel:  # type: ignore[no-redef]
        """Small compatibility base when channels._schemas has no async base class yet."""

        pass

from .._schemas import CrawledItemModel

logger = logging.getLogger(__name__)

CrawlResult = CrawledItemModel

DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)


class SocialSearchInput(BaseModel):
    """Validated input for one social-channel search request."""

    query: str = Field(..., min_length=1, max_length=200)
    max_results: int = Field(default=20, ge=1, le=100)


class SocialSearchOutput(BaseModel):
    """Typed output wrapper for callers that prefer a Pydantic response object."""

    channel: str
    query: str
    count: int = 0
    items: list[CrawlResult] = Field(default_factory=list)


class SocialCrawlerBase(BaseCrawlerChannel):
    """Async httpx crawler base with robots.txt and 1 req/sec channel limiting."""

    channel: ClassVar[str] = "social"
    base_url: ClassVar[str] = ""
    default_headers: ClassVar[dict[str, str]] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
    }

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        transport: Any | None = None,
        timeout: float = 10.0,
        rate_limit_seconds: float = 1.0,
        user_agents: Iterable[str] | None = None,
    ) -> None:
        self._client = client
        self._transport = transport
        self.timeout = timeout
        self.rate_limit_seconds = max(float(rate_limit_seconds), 0.0)
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._robots_cache: dict[str, bool] = {}
        self._user_agents = tuple(user_agents or DEFAULT_USER_AGENTS)
        self._ua_index = 0

    def _headers(self) -> dict[str, str]:
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return {**self.default_headers, "User-Agent": ua}

    async def _rate_limit(self) -> None:
        """Enforce one search request per second for this channel instance."""
        async with self._rate_lock:
            now = time.monotonic()
            wait_for = self.rate_limit_seconds - (now - self._last_request_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
                now = time.monotonic()
            self._last_request_at = now

    async def _request(self, url: str) -> str:
        headers = self._headers()
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            transport=self._transport,
        )
        try:
            if not await self._robots_allowed(client, url, headers):
                logger.warning("%s search blocked by robots.txt: %s", self.channel, url)
                return ""
            await self._rate_limit()
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("%s search request failed: %s", self.channel, exc)
            return ""
        except Exception as exc:  # defensive: parsing callers should never see network errors
            logger.warning("%s search unexpected failure: %s", self.channel, exc)
            return ""
        finally:
            if self._client is None:
                await client.aclose()

    async def _robots_allowed(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> bool:
        """Respect robots.txt when available; allow when unavailable or malformed."""
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._robots_cache:
            return self._robots_cache[host_key]

        robots_url = f"{host_key}/robots.txt"
        try:
            response = await client.get(robots_url, headers=headers)
            if response.status_code >= 400:
                self._robots_cache[host_key] = True
                return True
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch(headers.get("User-Agent", "*"), url)
            self._robots_cache[host_key] = allowed
            return allowed
        except Exception as exc:
            logger.debug("%s robots.txt unavailable for %s: %s", self.channel, host_key, exc)
            self._robots_cache[host_key] = True
            return True

    async def search_output(self, query: str, max_results: int = 20) -> SocialSearchOutput:
        items = await self.search(query=query, max_results=max_results)  # type: ignore[attr-defined]
        return SocialSearchOutput(channel=self.channel, query=query, count=len(items), items=items)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def first_text(root: Any, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = root.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def first_attr(root: Any, selectors: Iterable[str], attrs: Iterable[str]) -> str:
    for selector in selectors:
        node = root.select_one(selector)
        if not node:
            continue
        for attr in attrs:
            value = node.get(attr)
            if value:
                return str(value)
    return ""


def safe_url(url: Any, base_url: str) -> str:
    if not url:
        return base_url
    value = str(url).strip()
    if value.startswith("//"):
        return f"https:{value}"
    return urllib.parse.urljoin(base_url, value)


def stable_id(source: str, *parts: Any) -> str:
    seed = "|".join(str(part) for part in parts if part)
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{source}_{digest}"


def build_crawl_result(
    *,
    source: str,
    url: str,
    title: str,
    description: str = "",
    author: str = "",
    thumbnail_url: str = "",
    keyword: str = "",
    extra: dict[str, Any] | None = None,
) -> CrawlResult:
    """Create the standard Pydantic crawler item used by async social search."""
    clean_url = url or f"https://example.com/{source}"
    clean_title = clean_text(title) or clean_text(description)[:80] or f"{source} result"
    merged_extra = {
        "platform": source,
        "copyright": "metadata-only; respect source terms and robots.txt",
    }
    if extra:
        merged_extra.update(extra)
    return CrawlResult(
        id=stable_id(source, clean_url, clean_title),
        url=clean_url,
        title=clean_title[:500],
        description=clean_text(description)[:2000],
        source=source,
        author=clean_text(author)[:200],
        keywords=[keyword] if keyword else [],
        created_at=datetime.utcnow(),
        thumbnail_url=thumbnail_url or "",
        extra=merged_extra,
    )


__all__ = [
    "BaseCrawlerChannel",
    "CrawlResult",
    "SocialCrawlerBase",
    "SocialSearchInput",
    "SocialSearchOutput",
    "build_crawl_result",
    "clean_text",
    "first_attr",
    "first_text",
    "safe_url",
]
