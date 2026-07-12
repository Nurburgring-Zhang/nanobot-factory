"""Academic paper crawler channels (P20-D).

5 channels for academic-paper search:
    1. ArxivChannel               arxiv.org Atom API (export.arxiv.org/api)
    2. PubMedChannel              eutils.ncbi.nlm.nih.gov (NCBI Entrez)
    3. IEEEChannel                ieeexplore.ieee.org (REST search)
    4. SemanticScholarChannel     api.semanticscholar.org (graph v1)
    5. GoogleScholarChannel       scholar.google.com (HTML scrape)

Common contract:
    async def search(query: str, max_results: int = 20) -> List[Paper]

`Paper` is a Pydantic v2 model — see paper.py.

Design notes:
- All crawlers expose async `search()` returning List[Paper].
- Transport is httpx.AsyncClient (lazy-initialised per crawler).
- Tests inject an httpx.MockTransport via the `transport=` constructor arg
  so we never hit the real network during pytest.
- A simple per-instance rate limiter enforces >=1 req/sec between calls.
- Crawlers degrade gracefully when the upstream is unreachable: they
  return [] and log a warning, instead of raising.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .paper import Paper  # noqa: F401

logger = logging.getLogger(__name__)


# Default user-agents per channel family. Real academic APIs are usually
# happy with any modern UA; some (Google Scholar in particular) gate based
# on the UA fingerprint. Channels pick from this pool when not overridden.
_USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


class BaseAcademicCrawler:
    """Common base — async + sync transport wrapper with rate limiting.

    Subclasses override `_fetch_raw(query, max_results)` returning either a
    parsed JSON dict/list (preferred) or a raw HTML string (GoogleScholar).

    They must populate `self.records` after `_fetch_raw` so `parse_records`
    can convert to `Paper` objects.
    """

    channel: str = "academic_base"
    api_endpoint: str = ""

    def __init__(self, transport: Optional[Any] = None,
                 timeout: float = 30.0,
                 client: Optional[Any] = None,
                 rate_limit_seconds: float = 1.0) -> None:
        self.timeout = timeout
        # transport: optional httpx.MockTransport for tests
        self._transport = transport
        # allow injection of a fully-built httpx.AsyncClient
        self._client = client
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request_ts: float = 0.0
        self._rate_lock = asyncio.Lock()
        self.records: List[Any] = []
        self._last_meta: Dict[str, Any] = {}

    # ---- transport helpers (httpx) ----

    def _build_client(self):
        import httpx  # local import — keep module import cheap
        if self._client is not None:
            return self._client
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport, timeout=self.timeout,
            )
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENTS[0]},
        )

    async def _close_client(self, client) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    async def _rate_limit(self) -> None:
        """Per-instance simple rate limiter — sleep until >= rate_limit_seconds
        has passed since the previous call."""
        if self.rate_limit_seconds <= 0:
            return
        async with self._rate_lock:
            now = time.monotonic()
            wait = self.rate_limit_seconds - (now - self._last_request_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts = time.monotonic()

    # ---- public API ----

    async def search(self, query: str, max_results: int = 20) -> List[Paper]:
        """Async entrypoint — required by task spec."""
        max_results = max(1, min(int(max_results), 100))
        try:
            await self._rate_limit()
            raw = await self._fetch_raw(query=query, max_results=max_results)
        except Exception as e:
            logger.warning("%s._fetch_raw failed for query=%r: %s",
                           self.channel, query, e)
            return []
        try:
            self.records = self._normalize(raw)
            papers = self.parse_records(self.records, query=query)
        except Exception as e:
            logger.warning("%s.parse_records failed: %s", self.channel, e)
            return []
        return papers[:max_results]

    def search_sync(self, query: str, max_results: int = 20) -> List[Paper]:
        """Sync wrapper for non-async callers."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(
                        asyncio.run,
                        self.search(query, max_results),
                    )
                    return fut.result(timeout=60)
            return loop.run_until_complete(self.search(query, max_results))
        except RuntimeError:
            return asyncio.run(self.search(query, max_results))

    # ---- template methods (subclasses override) ----

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        raise NotImplementedError

    def _normalize(self, raw: Any) -> List[Any]:
        """Convert raw response -> list of records (dicts). Default pass-through
        with a few common unwrappings."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("results", "data", "items", "records", "papers",
                        "response", "articles"):
                v = raw.get(key)
                if isinstance(v, list):
                    return v
            # nested data.results (Semantic Scholar)
            data = raw.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("results", "items", "papers"):
                    v = data.get(key)
                    if isinstance(v, list):
                        return v
            # PubMed returns {esearchresult: {idlist: [...]}} — string ids
            res = raw.get("esearchresult")
            if isinstance(res, dict):
                idlist = res.get("idlist")
                if isinstance(idlist, list):
                    return [{"pmid": str(x)} for x in idlist if x]
            # arxiv API: {entries: [{...}]}  — already top-level
        return []

    def parse_records(self, records: List[Any], query: str = "") -> List[Paper]:
        """Convert raw dicts -> List[Paper]. Subclasses must override."""
        raise NotImplementedError


__all__ = [
    "BaseAcademicCrawler",
    "Paper",
    "ArxivChannel",
    "PubMedChannel",
    "IEEEChannel",
    "SemanticScholarChannel",
    "GoogleScholarChannel",
]


# Re-export crawlers at package level so
# `from imdf.crawler.channels.academic import ArxivChannel` works.
# Tolerate missing files so partial-import doesn't break the package.
try:
    from .arxiv import ArxivChannel  # noqa: F401
except Exception as _e:  # pragma: no cover - defensive
    logger.warning("academic: failed to import ArxivChannel from .arxiv: %s", _e)

try:
    from .pubmed import PubMedChannel  # noqa: F401
except Exception as _e:  # pragma: no cover - defensive
    logger.warning("academic: failed to import PubMedChannel from .pubmed: %s", _e)

try:
    from .ieee import IEEEChannel  # noqa: F401
except Exception as _e:  # pragma: no cover - defensive
    logger.warning("academic: failed to import IEEEChannel from .ieee: %s", _e)

try:
    from .semanticscholar import SemanticScholarChannel  # noqa: F401
except Exception as _e:  # pragma: no cover - defensive
    logger.warning("academic: failed to import SemanticScholarChannel from .semanticscholar: %s", _e)

try:
    from .googlescholar import GoogleScholarChannel  # noqa: F401
except Exception as _e:  # pragma: no cover - defensive
    logger.warning("academic: failed to import GoogleScholarChannel from .googlescholar: %s", _e)
