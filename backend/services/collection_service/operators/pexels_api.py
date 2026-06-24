"""collect.pexels_api — Pexels video + image search.

Live: GET https://api.pexels.com/{videos|photos}/search?query=...&per_page=...
Sandbox: deterministic mock.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    media_type = params.get("media_type", "videos")
    api_key = params.get("api_key") or os.environ.get("PEXELS_API_KEY", "")
    if is_sandbox() or not api_key:
        items = mock_response("pexels", query, count=max_results, kind=media_type.rstrip("s"))
        for it in items:
            it["thumb"] = f"https://images.pexels.com/photos/{it['id']}/pexels-photo.jpeg"
        return {
            "source": "pexels",
            "query": query,
            "count": len(items),
            "media_type": media_type,
            "mode": "mock",
            "items": items,
        }
    url = f"https://api.pexels.com/{media_type}/search"
    r = safe_get(url, params={"query": query, "per_page": max_results}, timeout=8.0)
    if not isinstance(r, dict) or (media_type not in r):
        return {"source": "pexels", "query": query, "count": 0, "mode": "error", "items": []}
    items = []
    for m in r.get(media_type, []):
        items.append({
            "id": str(m.get("id")),
            "title": query,
            "url": m.get("url") or m.get("link", ""),
            "thumb": (m.get("image") or ""),
            "duration_sec": m.get("duration", 0),
        })
    return {"source": "pexels", "query": query, "count": len(items),
            "media_type": media_type, "mode": "live", "items": items}


__all__ = ["run"]
