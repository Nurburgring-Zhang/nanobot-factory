"""HuggingFace Datasets crawler (P20-B1 batch 2)

HF Datasets Server API:
    GET https://huggingface.co/api/datasets?search=<query>&limit=<n>

Optional full-text search:
    GET https://huggingface.co/api/datasets?full=<query>&limit=<n>&config=<fmt>

Response shape (real API):
    [
      {
        "id": "owner/name",
        "downloads": 12345,
        "downloadsAllTime": 67890,
        "tags": ["task_categories:text-generation", ...],
        "lastModified": "2024-01-01T00:00:00Z",
        "cardData": {"license": "...", "size_categories": "..."},
        "siblings": [{"rfilename": "data/train.parquet"}, ...],
        "private": false,
        "gated": false,
        "author": "..."
      },
      ...
    ]

We don't require auth — public datasets are browseable anonymously.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from . import BaseDatasetCrawler
from .dataset import Dataset

logger = logging.getLogger(__name__)


# common file extensions we look for in the `siblings` rfilename list
_KNOWN_FORMATS = (
    "parquet", "csv", "jsonl", "json", "arrow", "tsv", "txt",
    "tar", "tar.gz", "zip", "h5", "hdf5", "tfrecord", "xml",
)


class HuggingFaceDatasetsCrawler(BaseDatasetCrawler):
    """Search HuggingFace public datasets via Datasets Server API.

    Usage:
        cw = HuggingFaceDatasetsCrawler(token="hf_…")  # optional
        results = await cw.list_datasets("vision", max_results=10)

    Note: HF token increases rate limit but is not required for read-only
    dataset listing.
    """

    channel = "huggingface_datasets"
    api_endpoint = "https://huggingface.co/api/datasets"

    def __init__(self, token: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.token = token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

    async def _fetch_raw(self, query: str, max_results: int) -> List[Any]:
        params = {"search": query, "limit": max_results}
        url = f"{self.api_endpoint}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        client = self._build_client()
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("HF Datasets API status %d body=%s",
                               resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            if not isinstance(data, list):
                return []
            return data
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        out: List[Dataset] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            ds_id = str(r.get("id") or f"hf_{idx}")
            url = f"https://huggingface.co/datasets/{ds_id}"
            tags_raw = r.get("tags") or []
            if isinstance(tags_raw, str):
                tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
            else:
                tags_list = [str(t) for t in tags_raw if t]

            # split "task_categories:text-generation" into "text-generation"
            tags_clean: List[str] = []
            for t in tags_list:
                if ":" in t:
                    tags_clean.append(t.split(":", 1)[1])
                else:
                    tags_clean.append(t)

            # Infer formats from siblings rfilename list
            formats: List[str] = []
            siblings = r.get("siblings") or []
            if isinstance(siblings, list):
                for sib in siblings:
                    rfn = ""
                    if isinstance(sib, dict):
                        rfn = sib.get("rfilename", "") or ""
                    elif isinstance(sib, str):
                        rfn = sib
                    rfn_low = rfn.lower()
                    for fmt in _KNOWN_FORMATS:
                        if rfn_low.endswith(f".{fmt}") and fmt not in formats:
                            formats.append(fmt)

            # card data may include size_categories & license
            card = r.get("cardData") or {}
            if isinstance(card, str):
                card = {}
            size_str = None
            size_cat = card.get("size_categories")
            if isinstance(size_cat, str):
                size_str = size_cat
            elif isinstance(card.get("dataset_info"), dict):
                # sometimes size is nested under dataset_info
                ds_info = card.get("dataset_info") or {}
                if isinstance(ds_info.get("features"), dict):
                    pass
                # try to extract a rows count
                rows = ds_info.get("num_rows") or ds_info.get("num_examples")
                if isinstance(rows, (int, float)):
                    size_str = f"{int(rows):,} rows"

            downloads = r.get("downloadsAllTime") or r.get("downloads")
            license_str = card.get("license") if isinstance(card, dict) else None
            if isinstance(license_str, dict):
                license_str = license_str.get("id") or license_str.get("name")

            try:
                ds = Dataset(
                    id=ds_id,
                    title=ds_id.split("/")[-1] if "/" in ds_id else ds_id,
                    url=url,
                    size=size_str,
                    format=formats,
                    tags=tags_clean,
                    channel=self.channel,
                    description=str(card.get("description") or card.get("summary") or "")[:500],
                    license=str(license_str) if license_str else None,
                    downloads=_coerce_int_or_none(downloads),
                    stars=_coerce_int_or_none(r.get("likes")),
                    author=str(r.get("author") or (ds_id.split("/")[0] if "/" in ds_id else "")),
                    last_updated=str(r.get("lastModified")) if r.get("lastModified") else None,
                    extra={
                        "private": bool(r.get("private", False)),
                        "gated": str(r.get("gated", "false")),
                        "downloads30d": r.get("downloads"),
                        "card_data_keys": list(card.keys()) if isinstance(card, dict) else [],
                    },
                )
                if not ds.title:
                    ds = ds.model_copy(update={"title": ds.id})
                if not ds.url:
                    ds = ds.model_copy(update={"url": f"https://huggingface.co/datasets/{ds.id}"})
                out.append(ds)
            except Exception as e:
                logger.debug("HF record %d skipped: %s", idx, e)
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


__all__ = ["HuggingFaceDatasetsCrawler"]