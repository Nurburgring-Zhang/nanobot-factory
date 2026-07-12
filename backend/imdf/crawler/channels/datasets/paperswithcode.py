"""PapersWithCode crawler (P20-B1 batch 2)

PapersWithCode exposes a REST API at:
    GET https://paperswithcode.com/api/v1/datasets/?q=<query>&page=<n>
    GET https://paperswithcode.com/api/v1/datasets/<id>/
    GET https://paperswithcode.com/api/v1/datasets/?q=<query>&items_per_page=<n>

PWC API list response shape:
    {
      "count": 123,
      "next": "https://paperswithcode.com/api/v1/datasets/?page=2",
      "previous": null,
      "results": [
        {
          "id": "mnist",
          "name": "MNIST",
          "description": "…",
          "url": "https://paperswithcode.com/dataset/mnist",
          "paper": {"id": "…", "title": "…", "url": "…"},
          "tags": ["image", "classification"],
          "variants": ["mnist", "fashion-mnist"],
          "modalities": ["Images"],
          "languages": ["English"],
          "tasks": [{"id": "image-classification", "name": "Image Classification"}],
          "num_papers": 1234,
          "num_tasks": 5
        },
        ...
      ]
    }

PWC has no public rate-limit for read-only listing, but is sensitive to
abusive scraping — we default to a small page size and let max_results cap.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from . import BaseDatasetCrawler
from .dataset import Dataset

logger = logging.getLogger(__name__)


class PapersWithCodeCrawler(BaseDatasetCrawler):
    """Search PapersWithCode public datasets via REST API."""

    channel = "paperswithcode"
    api_endpoint = "https://paperswithcode.com/api/v1/datasets/"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.timeout < 30:
            self.timeout = 30.0

    async def _fetch_raw(self, query: str, max_results: int) -> List[Any]:
        # PWC supports `q=` for free-text search
        url = f"{self.api_endpoint}?{urllib.parse.urlencode({'q': query, 'items_per_page': max_results})}"
        client = self._build_client()
        try:
            resp = await client.get(
                url,
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("PapersWithCode status %d body=%s",
                               resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            if not isinstance(data, dict):
                return []
            results = data.get("results") or []
            if not isinstance(results, list):
                return []
            return results[:max_results]
        finally:
            if self._client is None and self._transport is None:
                await self._close_client(client)

    def parse_records(self, records: List[Any], query: str = "") -> List[Dataset]:
        out: List[Dataset] = []
        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            try:
                ds_id = str(r.get("id") or r.get("slug") or f"pwc_{idx}")
                name = str(r.get("name") or ds_id)
                url = (
                    r.get("url")
                    or f"https://paperswithcode.com/dataset/{ds_id}"
                )
                tags_raw = r.get("tags") or []
                if isinstance(tags_raw, str):
                    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
                else:
                    tags_list = [str(t) for t in tags_raw if t]
                # modalities + tasks also act as tags
                modalities = r.get("modalities") or []
                languages = r.get("languages") or []
                tasks = r.get("tasks") or []
                for m in modalities:
                    if m and m not in tags_list:
                        tags_list.append(f"modality:{m}")
                for lang in languages:
                    if lang and f"lang:{lang}" not in tags_list:
                        tags_list.append(f"lang:{lang}")
                if isinstance(tasks, list):
                    for t in tasks[:5]:
                        if isinstance(t, dict):
                            nm = t.get("name") or t.get("id")
                            if nm and nm not in tags_list:
                                tags_list.append(str(nm))

                # PWC doesn't expose formats/sizes — derive format from name if obvious
                formats: List[str] = []
                desc = (r.get("description") or "").lower()
                for fmt in ("parquet", "csv", "json", "jsonl", "tfrecord",
                            "arrow", "hdf5", "txt", "zip", "tar"):
                    if fmt in desc and fmt not in formats:
                        formats.append(fmt)

                # size — count of papers/usage is the closest proxy
                num_papers = r.get("num_papers")
                size_str = (
                    f"{int(num_papers)} papers" if isinstance(num_papers, (int, float)) else None
                )

                ds = Dataset(
                    id=ds_id,
                    title=name,
                    url=url,
                    size=size_str,
                    format=formats,
                    tags=tags_list,
                    channel=self.channel,
                    description=str(r.get("description") or "")[:500],
                    license=None,
                    downloads=None,
                    stars=_coerce_int_or_none(r.get("num_papers")),
                    author=None,
                    last_updated=str(r.get("last_updated")) if r.get("last_updated") else None,
                    extra={
                        "variants": r.get("variants") or [],
                        "modalities": modalities,
                        "languages": languages,
                        "tasks": tasks,
                        "num_papers": r.get("num_papers"),
                        "num_tasks": r.get("num_tasks"),
                        "paper": r.get("paper"),
                    },
                )
                if not ds.title:
                    ds = ds.model_copy(update={"title": ds.id})
                if not ds.url:
                    ds = ds.model_copy(update={
                        "url": f"https://paperswithcode.com/dataset/{ds.id}",
                    })
                out.append(ds)
            except Exception as e:
                logger.debug("PapersWithCode record %d skipped: %s", idx, e)
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


__all__ = ["PapersWithCodeCrawler"]