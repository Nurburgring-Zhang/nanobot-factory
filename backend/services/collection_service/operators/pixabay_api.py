"""collect.pixabay_api — Pixabay image / video / audio search.

Live: GET https://pixabay.com/api/?key=...&q=...&per_page=...
Sandbox: deterministic mock.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    media_type = params.get("media_type", "image")  # image|video|audio
    api_key = params.get("api_key") or os.environ.get("PIXABAY_API_KEY", "")
    if is_sandbox() or not api_key:
        items = mock_response("pixabay", query, count=max_results, kind=media_type)
        for it in items:
            it["thumb"] = f"https://cdn.pixabay.com/photo/{it['id']}/200x200.jpg"
        return {
            "source": "pixabay",
            "query": query,
            "count": len(items),
            "media_type": media_type,
            "mode": "mock",
            "items": items,
        }
    r = safe_get("https://pixabay.com/api/",
                 params={"key": api_key, "q": query, "per_page": max_results}, timeout=8.0)
    if not isinstance(r, dict) or "hits" not in r:
        return {"source": "pixabay", "query": query, "count": 0, "mode": "error", "items": []}
    items: List[Dict[str, Any]] = []
    for h in r.get("hits", []):
        items.append({
            "id": str(h.get("id")),
            "title": h.get("tags", ""),
            "url": h.get("pageURL", ""),
            "thumb": h.get("previewURL", ""),
            "width": h.get("imageWidth"),
            "height": h.get("imageHeight"),
        })
    return {"source": "pixabay", "query": query, "count": len(items),
            "media_type": media_type, "mode": "live", "items": items}


__all__ = ["run"]
