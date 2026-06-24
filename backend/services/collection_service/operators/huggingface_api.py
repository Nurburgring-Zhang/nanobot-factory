"""collect.huggingface_api — HuggingFace Hub dataset / model search.

Live: GET https://huggingface.co/api/datasets?search=...&limit=...
Sandbox: deterministic mock.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    resource = params.get("resource", "datasets")  # datasets|models|spaces
    if is_sandbox():
        items = mock_response("huggingface", query, count=max_results, kind=resource.rstrip("s"))
        for it in items:
            it["id"] = f"org/{it['id']}"
            it["downloads"] = abs(hash(it["id"])) % 1_000_000
            it["tags"] = ["text", "image", "multimodal"][: (abs(hash(it["id"])) % 3) + 1]
        return {
            "source": "huggingface",
            "query": query,
            "resource": resource,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    url = f"https://huggingface.co/api/{resource}"
    r = safe_get(url, params={"search": query, "limit": max_results}, timeout=10.0)
    if not isinstance(r, list):
        return {"source": "huggingface", "query": query, "count": 0, "mode": "error", "items": []}
    items: List[Dict[str, Any]] = []
    for it in r:
        items.append({
            "id": it.get("id") or it.get("name", ""),
            "downloads": it.get("downloads", 0),
            "tags": it.get("tags", []),
            "url": f"https://huggingface.co/{resource}/{it.get('id', '')}",
        })
    return {"source": "huggingface", "query": query, "resource": resource,
            "count": len(items), "mode": "live", "items": items}


__all__ = ["run"]
