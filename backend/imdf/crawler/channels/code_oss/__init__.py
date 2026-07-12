"""Code-OSS public repository crawlers (P20-E batch)

Five channels for searching public code repositories across major hosting
platforms. Each channel follows the same public contract:

    async search(query, max_results=20) -> list[CrawlResult]
    static  parse(html)                 -> list[CrawlResult]

All channels are public (no API key required), respect rate-limiting
(1 req/sec), use httpx async client + BeautifulSoup, and gracefully
degrade to an empty list when the upstream is unreachable.

Channels:
    1. GitHubChannel          — api.github.com/search/repositories (JSON API)
    2. GitLabChannel          — gitlab.com/explore (HTML scrape)
    3. GiteeChannel           — gitee.com/search (HTML scrape)
    4. BitbucketChannel       — bitbucket.org/search (HTML scrape)
    5. SourceForgeChannel     — sourceforge.net/directory (HTML scrape)

Cross-cutting design:
    - httpx.AsyncClient + httpx.MockTransport (for tests)
    - 1 req/sec rate limiter per channel (configurable via `rate_limit_seconds`)
    - User-Agent: realistic browser UA so basic anti-bot defences don't block
    - robots.txt: opt-in via `respect_robots=True` (skipped by default for
      public search APIs / aggregators which already publish listings).
    - All channels degrade gracefully: network errors return [] + log warning.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================================
# Pydantic v2 model — unified code-repo result
# ============================================================

class CrawlResult(BaseModel):
    """Pydantic v2 — one code repository search result.

    Common fields surfaced by every channel. Channel-specific extras go
    into `extra` (e.g. default_branch, archived flag).
    """
    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        validate_assignment=False,
    )

    # core identity
    id: str = Field(..., description="Repository id (channel-specific, e.g. 'owner/name')")
    url: str = Field(..., description="Canonical repository URL")
    title: str = Field(default="", description="Repository display name (owner/name)")
    description: str = Field(default="", max_length=2000)
    source: str = Field(..., description="Channel name (e.g. 'github', 'gitee')")

    # authorship
    author: str = Field(default="", description="Repository owner / namespace")
    language: str = Field(default="", description="Primary language")

    # engagement
    stars: int = Field(default=0, ge=0, description="Star / like count")
    forks: int = Field(default=0, ge=0, description="Fork count")

    # taxonomy
    keywords: List[str] = Field(default_factory=list, description="Topics / tags")
    license: str = Field(default="", description="SPDX-like license name")
    last_updated: str = Field(default="", description="Last-updated ISO timestamp")

    # housekeeping
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Ingestion timestamp (UTC)",
    )
    extra: Dict[str, Any] = Field(default_factory=dict)

    # ---- validators ----

    @field_validator("id", "url", "source", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("stars", "forks", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        try:
            n = int(v)
            return n if n >= 0 else 0
        except (TypeError, ValueError):
            return 0

    @field_validator("keywords", mode="before")
    @classmethod
    def _coerce_keywords(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip()]
        if isinstance(v, str):
            return [p.strip() for p in v.replace("|", ",").split(",") if p.strip()]
        return [str(v)]

    # ---- helpers ----

    def to_dict(self) -> Dict[str, Any]:
        out = self.model_dump()
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].isoformat()
        return out


# ============================================================
# Base channel — async transport + rate limiting + error handling
# ============================================================

class BaseCrawlerChannel:
    """Base class for code-OSS crawler channels.

    Subclasses override:
        async search(query, max_results) -> list[CrawlResult]
        static  parse(html)               -> list[CrawlResult]

    Transport is httpx.AsyncClient — tests can inject `transport=` (an
    httpx.MockTransport) or `client=` (a fully built AsyncClient).
    """
    channel: str = "code_oss_base"
    api_endpoint: str = ""

    def __init__(
        self,
        transport: Optional[Any] = None,
        client: Optional[Any] = None,
        timeout: float = 30.0,
        rate_limit_seconds: float = 1.0,
        user_agent: Optional[str] = None,
        respect_robots: bool = False,
    ) -> None:
        self.timeout = timeout
        self._transport = transport
        self._client = client
        self._rate_limit_seconds = max(0.0, float(rate_limit_seconds))
        self._user_agent = user_agent or self._default_user_agent()
        self._respect_robots = bool(respect_robots)
        self._last_request_at: float = 0.0
        self._last_meta: Dict[str, Any] = {}

    # ---------- UA / headers ----------

    @staticmethod
    def _default_user_agent() -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {"User-Agent": self._user_agent, "Accept": "text/html,application/json"}
        if extra:
            h.update(extra)
        return h

    # ---------- transport helpers ----------

    def _build_client(self):
        if self._client is not None:
            return self._client
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport, timeout=self.timeout, follow_redirects=True,
            )
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self._headers(),
        )

    async def _close_client(self, client: Any) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    async def _rate_limit_wait(self) -> None:
        """Sleep at least `rate_limit_seconds` between successive requests.

        Uses `time.perf_counter()` (process-wide, microsecond resolution on
        Windows). The limiter survives across multiple event loops — tests
        typically create a fresh loop per call.
        """
        if self._rate_limit_seconds <= 0:
            return
        now = time.perf_counter()
        delta = now - self._last_request_at
        if delta < self._rate_limit_seconds:
            await asyncio.sleep(max(0.0, self._rate_limit_seconds - delta))
        self._last_request_at = time.perf_counter()

    async def _fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> str:
        """Fetch URL with rate-limiting. Returns body text. '' on failure."""
        await self._rate_limit_wait()
        merged = self._headers(headers)
        client = self._build_client()
        own_client = self._client is None
        try:
            resp = await client.request(method, url, headers=merged, **kwargs)
            if resp.status_code != 200:
                logger.warning(
                    "%s.fetch %s status=%d",
                    self.channel, url, resp.status_code,
                )
                return ""
            return resp.text
        except Exception as e:
            logger.warning("%s.fetch %s error: %s", self.channel, url, e)
            return ""
        finally:
            if own_client and self._client is None and self._transport is None:
                await self._close_client(client)

    # ---------- public contract ----------

    async def search(self, query: str, max_results: int = 20) -> List[CrawlResult]:
        """Async search — required by task spec. Returns [] on any error."""
        max_results = max(1, min(int(max_results), 100))
        try:
            return await self._search_impl(query=query, max_results=max_results)
        except Exception as e:
            logger.warning("%s.search(%r) error: %s", self.channel, query, e)
            return []

    async def _search_impl(self, query: str, max_results: int) -> List[CrawlResult]:
        raise NotImplementedError

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """Static HTML parser. Subclasses override to handle their own markup."""
        raise NotImplementedError

    def search_sync(self, query: str, max_results: int = 20) -> List[CrawlResult]:
        """Sync wrapper — for CLI / non-async callers."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(asyncio.run, self.search(query, max_results))
                    return fut.result(timeout=60)
            return loop.run_until_complete(self.search(query, max_results))
        except RuntimeError:
            return asyncio.run(self.search(query, max_results))


# ============================================================
# Public registry — `from imdf.crawler.channels.code_oss import CHANNELS`
# ============================================================

CHANNELS: Dict[str, type] = {}


def register(cls: type) -> type:
    """Class decorator — adds a channel class to the public registry."""
    name = getattr(cls, "channel", cls.__name__.lower())
    CHANNELS[name] = cls
    return cls


# Lazy imports — wrapped in try/except so one broken module doesn't break the
# package. Real imports happen when callers actually need them.
def _import_all() -> None:
    global CHANNELS
    if CHANNELS:
        return
    for mod_name in ("github", "gitlab", "gitee", "bitbucket", "sourceforge"):
        try:
            module = __import__(f"{__name__}.{mod_name}", fromlist=[mod_name])
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseCrawlerChannel) \
                        and attr is not BaseCrawlerChannel:
                    register(attr)
        except Exception as e:
            logger.warning("code_oss: failed to import %s: %s", mod_name, e)


_import_all()


__all__ = [
    "CrawlResult",
    "BaseCrawlerChannel",
    "CHANNELS",
    "register",
]