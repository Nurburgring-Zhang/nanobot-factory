"""collect.unsplash_api — Unsplash image search (requires access key).

Live: GET https://api.unsplash.com/search/photos?query=...&client_id=...
Sandbox: returns deterministic mock with image URLs.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    api_key = params.get("api_key") or os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if is_sandbox() or not api_key:
        items = mock_response("unsplash", query, count=max_results, kind="image")
        for it in items:
            it["thumb_url"] = f"https://source.unsplash.com/200x200/?{query}&sig={it['id'][-6:]}"
            it["width"] = 200
            it["height"] = 200
        return {
            "source": "unsplash",
            "query": query,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    r = safe_get("https://api.unsplash.com/search/photos",
                 params={"query": query, "per_page": max_results},
                 timeout=8.0)
    if not isinstance(r, dict) or "results" not in r:
        return {"source": "unsplash", "query": query, "count": 0, "mode": "error", "items": []}
    items: List[Dict[str, Any]] = []
    for ph in r.get("results", []):
        u = ph.get("urls", {})
        items.append({
            "id": ph.get("id"),
            "title": ph.get("alt_description") or query,
            "thumb_url": u.get("thumb"),
            "url": u.get("regular"),
            "width": ph.get("width"),
            "height": ph.get("height"),
            "author": ph.get("user", {}).get("name", ""),
        })
    return {"source": "unsplash", "query": query, "count": len(items),
            "mode": "live", "items": items}


__all__ = ["run"]
