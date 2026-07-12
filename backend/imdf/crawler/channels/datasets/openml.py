"""OpenML crawler (P20-B1 batch 2)

OpenML REST API:
    GET https://www.openml.org/api/v1/json/data/list/tag/<tag>/limit/<n>/offset/<o>
    GET https://www.openml.org/api/v1/json/data/list/data_name/<q>/limit/<n>/offset/<o>
    GET https://www.openml.org/api/v1/json/data/<id>                  (full metadata)
    GET https://www.openml.org/api/v1/json/data/qualities/<id>       (feature info)

Public, no auth required.

List response shape:
    {
      "data": {
        "dataset": [
          {"did": "1", "name": "anneal", "version": "1", "status": "active",
           "format": "ARFF", "tag": ["study_1", "uci"], "visibility": "public",
           "uploader": "1", "name": "anneal", "url": "https://…",
           "md5_checksum": "…", "file_id": "1", "did": "1"}
        ]
      }
    }

Single-dataset response (`/data/<id>`):
    {
      "data_set_description": {
        "id": "1", "name": "anneal", "version": "1",
        "description": "…", "format": "ARFF",
        "upload_date": "2014-08-21 16:16:14",
        "licence": "Public", "url": "https://…",
        "default_target_attribute": "class",
        "tag": ["study_1"], "visibility": "public",
        "version_label": "1", "status": "active"
      },
      "qualities": {
        "Attribute_1": {"name": "…", "datatype": "numeric", …},
        …
      },
      "tags": ["study_1", "uci"]
    }
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from . import BaseDatasetCrawler
from .dataset import Dataset

logger = logging.getLogger(__name__)


class OpenMLCrawler(BaseDatasetCrawler):
    """Search OpenML public datasets via REST API.

    Usage:
        cw = OpenMLCrawler()
        results = await cw.list_datasets("iris", max_results=10)
    """

    channel = "openml"
    api_endpoint = "https://www.openml.org/api/v1/json"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # tune timeout — OpenML can be slow on cold cache
        if self.timeout < 30:
            self.timeout = 30.0

    async def _fetch_raw(self, query: str, max_results: int) -> List[Any]:
        # OpenML list endpoint expects a *tag*, not a free-text search.
        # We use the `data_name` filter instead which performs substring match.
        encoded = urllib.parse.quote(query, safe="")
        url = f"{self.api_endpoint}/data/list/data_name/{encoded}/limit/{max_results}/offset/0"
        client = self._build_client()
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                logger.warning("OpenML list status %d body=%s",
                               resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            items = data.get("data", {}).get("dataset", [])
            if not isinstance(items, list):
                return []
            # Trim to max_results
            return items[:max_results]
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        out: List[Dataset] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            try:
                did = str(r.get("did") or r.get("id") or f"openml_{idx}")
                name = str(r.get("name") or did)
                url = str(r.get("url") or f"https://www.openml.org/d/{did}")
                fmt_str = r.get("format") or ""
                formats = [fmt_str.lower()] if fmt_str else []
                tags_raw = r.get("tag") or []
                if isinstance(tags_raw, str):
                    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
                else:
                    tags_list = [str(t) for t in tags_raw if t]
                version = str(r.get("version") or "1")
                ds = Dataset(
                    id=did,
                    title=name,
                    url=url,
                    size=None,
                    format=formats,
                    tags=tags_list,
                    channel=self.channel,
                    description=f"OpenML dataset {name} (version {version})",
                    license=str(r.get("licence") or "Public"),
                    downloads=_coerce_int_or_none(r.get("download_url")),
                    author=None,
                    last_updated=str(r.get("upload_date")) if r.get("upload_date") else None,
                    extra={
                        "version": version,
                        "status": r.get("status"),
                        "visibility": r.get("visibility"),
                        "file_id": r.get("file_id"),
                        "md5_checksum": r.get("md5_checksum"),
                    },
                )
                if not ds.title:
                    ds = ds.model_copy(update={"title": ds.id})
                if not ds.url:
                    ds = ds.model_copy(update={"url": f"https://www.openml.org/d/{ds.id}"})
                out.append(ds)
            except Exception as e:
                logger.debug("OpenML record %d skipped: %s", idx, e)
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


__all__ = ["OpenMLCrawler"]