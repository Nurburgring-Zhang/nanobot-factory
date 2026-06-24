"""collect.common_crawl — Common Crawl index query.

Common Crawl exposes the CDX index for WARC/WAT/WET files. Live mode
constructs the CDX API URL but does not download full payloads (large).
Sandbox returns deterministic mock.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response


_CDX_INDEX = "http://index.commoncrawl.org/CC-MAIN-2024-22-index"


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    match_type = params.get("match_type", "domain")
    url_filter = params.get("url", query)
    if is_sandbox():
        items = mock_response("commoncrawl", url_filter, count=max_results, kind="warc")
        for it in items:
            it["warc_filename"] = f"CC-MAIN-2024-22/segments/.../{it['id']}.warc.gz"
            it["offset"] = 0
            it["length"] = 4096
        return {
            "source": "commoncrawl",
            "query": query,
            "match_type": match_type,
            "url": url_filter,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    # Real CDX API is form-post; in production code we'd POST here.
    return {
        "source": "commoncrawl",
        "query": query,
        "url": url_filter,
        "count": 0,
        "mode": "live_unavailable",
        "items": [],
        "note": "CDX API requires POST; full impl pending bearer",
    }


__all__ = ["run"]
