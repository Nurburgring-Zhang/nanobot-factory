"""Kaggle public-dataset crawler (P20-B1 batch 2)

Kaggle Datasets API:
    GET https://www.kaggle.com/api/v1/datasets/list?search=<query>&page=<n>

Response shape (real API):
    [
      {
        "id": 12345,
        "ref": "owner/slug",
        "title": "...",
        "subtitle": "...",
        "creatorName": "...",
        "downloadCount": 0,
        "totalBytes": 0,
        "tags": [{"name": "tag1", ...}],
        "licenseName": "CC BY 4.0",
        "lastUpdated": "2024-01-01T00:00:00Z",
        ...
      },
      ...
    ]

Auth: optional. With credentials, response includes private + more quota.
Without, search still works for public datasets — Kaggle's "list" endpoint
does not require an API key for read-only public dataset searches.

Fallback: if API call fails (network / rate-limit / 401), we return [] and
log a warning. Tests inject httpx.MockTransport.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from . import BaseDatasetCrawler
from .dataset import Dataset

logger = logging.getLogger(__name__)


class KaggleCrawler(BaseDatasetCrawler):
    """Search Kaggle public datasets via REST API.

    Usage:
        async with httpx.AsyncClient() as client:
            cw = KaggleCrawler(client=client)
            results = await cw.list_datasets("cats", max_results=10)

        # or test-friendly with mock transport:
        cw = KaggleCrawler(transport=mock_transport)
    """

    channel = "kaggle_datasets"
    api_endpoint = "https://www.kaggle.com/api/v1/datasets/list"

    def __init__(self, username: Optional[str] = None,
                 key: Optional[str] = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Credentials are optional for public dataset search
        self.username = username or os.environ.get("KAGGLE_USERNAME")
        self.key = key or os.environ.get("KAGGLE_KEY")

    async def _fetch_raw(self, query: str, max_results: int) -> List[Any]:
        params = {"search": query, "page": 1}
        # Kaggle returns ~20 results per page; ask for ceil(N/20) pages
        import math
        pages = max(1, math.ceil(max_results / 20))
        all_items: List[Any] = []
        client = self._build_client()
        try:
            for page in range(1, pages + 1):
                params["page"] = page
                url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
                headers = {"Accept": "application/json"}
                if self.username and self.key:
                    headers["Authorization"] = f"Basic {self._basic_auth()}"
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Kaggle API status %d for page %d",
                                   resp.status_code, page)
                    break
                data = resp.json()
                if not isinstance(data, list):
                    break
                all_items.extend(data)
                if len(data) < 20:
                    break
                if len(all_items) >= max_results:
                    break
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)
        return all_items

    def _basic_auth(self) -> str:
        import base64
        cred = f"{self.username}:{self.key or ''}".encode("utf-8")
        return base64.b64encode(cred).decode("ascii")

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        out: List[Dataset] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            ref = r.get("ref") or ""
            url = r.get("url") or (f"https://www.kaggle.com/datasets/{ref}" if ref else "")
            tags_raw = r.get("tags") or []
            tag_names = []
            if isinstance(tags_raw, list):
                for t in tags_raw:
                    if isinstance(t, dict):
                        name = t.get("name") or t.get("displayName")
                        if name:
                            tag_names.append(str(name))
                    elif isinstance(t, str):
                        tag_names.append(t)
            elif isinstance(tags_raw, str):
                tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]

            # file types — Kaggle exposes 'fileTypes' as list
            file_types_raw = r.get("fileTypes") or r.get("filetypes") or []
            formats: List[str] = []
            if isinstance(file_types_raw, list):
                formats = [str(x).lower() for x in file_types_raw if x]
            elif isinstance(file_types_raw, str):
                formats = [t.strip().lower() for t in file_types_raw.split(",") if t.strip()]

            total_bytes = r.get("totalBytes")
            size_str = _humanize_bytes(total_bytes) if isinstance(total_bytes, (int, float)) else None

            ds_id = str(r.get("id") or r.get("ref") or f"kaggle_{idx}")
            title = (
                r.get("title")
                or r.get("subtitle")
                or (ref.split("/")[-1] if "/" in ref else ref)
                or ds_id
            )

            try:
                ds = Dataset(
                    id=ds_id,
                    title=str(title),
                    url=str(url) if url else "",
                    size=size_str,
                    format=formats,
                    tags=tag_names,
                    channel=self.channel,
                    description=str(r.get("subtitle") or r.get("description") or ""),
                    license=r.get("licenseName"),
                    downloads=_coerce_int_or_none(r.get("downloadCount")),
                    stars=_coerce_int_or_none(r.get("voteCount")),
                    author=r.get("creatorName"),
                    last_updated=r.get("lastUpdated"),
                    extra={
                        "ref": ref,
                        "isPrivate": r.get("isPrivate", False),
                        "kernelCount": r.get("kernelCount"),
                        "category": r.get("category"),
                    },
                )
                if not ds.id:
                    ds = ds.model_copy(update={"id": f"kaggle_{idx}"})
                if not ds.url:
                    ds = ds.model_copy(update={"url": f"https://www.kaggle.com/datasets/{ref}"})
                out.append(ds)
            except Exception as e:
                logger.debug("Kaggle record %d skipped: %s", idx, e)
                continue
        return out


def _coerce_int_or_none(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        n = int(v)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _humanize_bytes(n: float) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


__all__ = ["KaggleCrawler"]