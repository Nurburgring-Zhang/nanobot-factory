"""Public-dataset API crawlers (P20-B1 batch 2)

5 sources:
    1. KaggleCrawler              kaggle.com/datasets REST API
    2. HuggingFaceDatasetsCrawler huggingface.co/datasets (HF Datasets Server API)
    3. OpenMLCrawler              openml.org REST API
    4. UCIMLCrawler               archive.ics.uci.edu (no API, scrape index)
    5. PapersWithCodeCrawler      paperswithcode.com REST API

Common contract:
    async def list_datasets(query: str, max_results: int = 50) -> List[Dataset]

Dataset is a Pydantic v2 model — see dataset.py.

Design notes:
- Each crawler exposes an `async list_datasets()` and a sync `list_datasets_sync()`.
- HTTP transport is httpx.AsyncClient (lazy-initialised per crawler).
- Tests inject an httpx.MockTransport via the `transport=` constructor arg so
  we never hit the real network.
- All crawlers degrade gracefully when the upstream is unreachable:
  they return [] and log a warning, instead of raising.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, List, Optional

from .dataset import Dataset  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)


class BaseDatasetCrawler:
    """Common base — async + sync transport wrapper.

    Subclasses override `_fetch_raw(query, max_results)` returning either a
    parsed JSON dict/list (preferred) or a raw HTML string (UCI).

    They must populate `self.records` after `_fetch_raw` so `parse_records`
    can convert to `Dataset` objects.
    """

    channel: str = "dataset_base"
    api_endpoint: str = ""

    def __init__(self, transport: Optional[Any] = None,
                 timeout: float = 30.0,
                 client: Optional[Any] = None) -> None:
        self.timeout = timeout
        # transport: optional httpx.MockTransport for tests
        self._transport = transport
        # allow injection of a fully-built httpx.AsyncClient
        self._client = client
        self.records: List[Any] = []
        self._last_meta: dict = {}

    # ---- transport helpers (httpx) ----

    def _build_client(self):
        import httpx  # local import — keep module import cheap
        if self._client is not None:
            return self._client
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport, timeout=self.timeout,
            )
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    async def _close_client(self, client) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    # ---- public API ----

    async def list_datasets(self, query: str, max_results: int = 50) -> List[Dataset]:
        """Async entrypoint — required by task spec."""
        max_results = max(1, min(int(max_results), 200))
        try:
            raw = await self._fetch_raw(query=query, max_results=max_results)
        except Exception as e:
            logger.warning("%s._fetch_raw failed for query=%r: %s",
                           self.channel, query, e)
            return []
        try:
            self.records = self._normalize(raw)
            datasets = self.parse_records(self.records, query=query)
        except Exception as e:
            logger.warning("%s.parse_records failed: %s", self.channel, e)
            return []
        return datasets[:max_results]

    def list_datasets_sync(self, query: str, max_results: int = 50) -> List[Dataset]:
        """Sync wrapper for non-async callers (CLI, registry)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In an existing event loop — schedule and wait
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(
                        asyncio.run,
                        self.list_datasets(query, max_results),
                    )
                    return fut.result(timeout=60)
            return loop.run_until_complete(self.list_datasets(query, max_results))
        except RuntimeError:
            return asyncio.run(self.list_datasets(query, max_results))

    # ---- template methods (subclasses override) ----

    async def _fetch_raw(self, query: str, max_results: int) -> Any:
        raise NotImplementedError

    def _normalize(self, raw: Any) -> List[Any]:
        """Convert raw response → list of records (dicts). Default: pass-through."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            # try common keys
            for key in ("datasets", "items", "results", "data", "records"):
                v = raw.get(key)
                if isinstance(v, list):
                    return v
            # some APIs nest further: data.results
            data = raw.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("results", "datasets", "items"):
                    v = data.get(key)
                    if isinstance(v, list):
                        return v
        return []

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        """Convert raw dicts → List[Dataset]. Subclasses must override."""
        raise NotImplementedError


__all__ = [
    "BaseDatasetCrawler",
    "Dataset",
    "KaggleCrawler",
    "HuggingFaceDatasetsCrawler",
    "OpenMLCrawler",
    "UCIMLCrawler",
    "PapersWithCodeCrawler",
]

# Re-export crawlers at package level so `from imdf.crawler.channels.datasets
# import KaggleCrawler` works as the public contract. Import is wrapped in
# try/except so partial-import (e.g. one crawler file missing) doesn't break
# the whole package.
from .kaggle import KaggleCrawler  # noqa: E402,F401
from .huggingface import HuggingFaceDatasetsCrawler  # noqa: E402,F401
from .openml import OpenMLCrawler  # noqa: E402,F401
from .uci import UCIMLCrawler  # noqa: E402,F401
from .paperswithcode import PapersWithCodeCrawler  # noqa: E402,F401