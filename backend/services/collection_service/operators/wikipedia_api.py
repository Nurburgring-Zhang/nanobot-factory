"""collect.wikipedia_api — Wikipedia REST summary + page collection.

Live: uses en.wikipedia.org/api/rest_v1/page/summary/{title}.
Sandbox: returns deterministic mock.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    title = query.strip().replace(" ", "_")
    if is_sandbox():
        items = mock_response("wikipedia", title, count=max_results, kind="article")
        for it in items:
            it["title"] = title.replace("_", " ")
            it["extract"] = f"Summary for {title} (sandbox mock)"
            it["pageid"] = it["id"]
        return {
            "source": "wikipedia",
            "query": query,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    r = safe_get(url, timeout=5.0)
    if r is None or "_status" in r:
        return {
            "source": "wikipedia",
            "query": query,
            "count": 0,
            "mode": "error",
            "items": [],
            "note": r.get("_status") if isinstance(r, dict) else "network_unavailable",
        }
    return {
        "source": "wikipedia",
        "query": query,
        "count": 1,
        "mode": "live",
        "items": [{
            "id": r.get("titles", {}).get("canonical", title),
            "title": r.get("title", title),
            "extract": r.get("extract", ""),
            "url": r.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "thumbnail": r.get("thumbnail", {}).get("source", ""),
            "pageid": r.get("pageid", 0),
        }],
    }


__all__ = ["run"]
