"""智影 V4 — API 爬虫: REST + GraphQL + gRPC"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore
try:
    import grpc  # type: ignore
except ImportError:
    grpc = None  # type: ignore

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class APICrawler(BaseCrawler):
    """公开 API 爬虫 — REST (JSON) + GraphQL + gRPC"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._client: Optional[Any] = None

    async def _ensure_client(self):
        if self._client is None:
            if httpx is None:
                raise RuntimeError("httpx 未安装: pip install httpx")
            self._client = httpx.AsyncClient(
                timeout=30.0,
                http2=True,
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, url: str) -> RawDocument:
        """抓取 API 端点 — 根据 config.graphql_query 决定 REST 或 GraphQL"""
        start = time.time()
        client = await self._ensure_client()
        gql_query = self.config.selectors.get("graphql_query")
        if gql_query:
            return await self._fetch_graphql(url, gql_query, client, start)
        return await self._fetch_rest(url, client, start)

    async def _fetch_rest(self, url: str, client: Any, start: float) -> RawDocument:
        method = self.config.selectors.get("method", "GET").upper()
        body_str = self.config.selectors.get("body", "")
        body = json.loads(body_str) if body_str else None
        headers = self.config.selectors.get("headers", {})
        # 自动添加 UA
        headers.setdefault("User-Agent", "IMDF-Crawler/4.0")
        if body is not None:
            headers.setdefault("Content-Type", "application/json")
        resp = await client.request(method, url, json=body, headers=headers)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text[:10000]}
        return RawDocument(
            url=url,
            type="json",
            json=data,
            http_status=resp.status_code,
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_graphql(self, url: str, query: str, client: Any, start: float) -> RawDocument:
        """GraphQL 端点 — POST {query, variables}"""
        variables_str = self.config.selectors.get("graphql_variables", "{}")
        try:
            variables = json.loads(variables_str)
        except Exception:
            variables = {}
        body = {"query": query, "variables": variables}
        resp = await client.post(
            url, json=body, headers={"Content-Type": "application/json", "User-Agent": "IMDF-Crawler/4.0"}
        )
        resp.raise_for_status()
        data = resp.json()
        # GraphQL 错误检测
        errors = data.get("errors") if isinstance(data, dict) else None
        if errors:
            logger.warning(f"GraphQL errors at {url}: {errors[:1]}")
        return RawDocument(
            url=url,
            type="json",
            json=data,
            http_status=resp.status_code,
            source_metadata={"protocol": "graphql", "errors": errors},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
