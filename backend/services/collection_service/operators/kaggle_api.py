"""collect.kaggle_api — Kaggle dataset / competition search.

Live: GET https://www.kaggle.com/api/v1/datasets/list?search=...&page_size=...
Sandbox: deterministic mock. Note: real kaggle requires API token.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    resource = params.get("resource", "datasets")  # datasets|competitions
    kaggle_user = os.environ.get("KAGGLE_USERNAME", "")
    kaggle_key = os.environ.get("KAGGLE_KEY", "")
    if is_sandbox() or not (kaggle_user and kaggle_key):
        items = mock_response("kaggle", query, count=max_results, kind=resource.rstrip("s"))
        for it in items:
            it["ref"] = f"user/{it['id']}"
            it["title"] = f"Kaggle {resource}: {query} #{it['id'][-4:]}"
            it["size_bytes"] = abs(hash(it["id"])) % (500 * 1024 * 1024)
            it["vote_count"] = abs(hash(it["id"])) % 1000
        return {
            "source": "kaggle",
            "query": query,
            "resource": resource,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    url = f"https://www.kaggle.com/api/v1/{resource}/list"
    r = safe_get(url, params={"search": query, "page_size": max_results}, timeout=10.0)
    if not isinstance(r, list):
        return {"source": "kaggle", "query": query, "count": 0, "mode": "error", "items": []}
    items: List[Dict[str, Any]] = []
    for it in r:
        items.append({
            "id": str(it.get("id", it.get("ref", ""))),
            "ref": it.get("ref", ""),
            "title": it.get("title", ""),
            "size_bytes": it.get("totalBytes", 0),
            "vote_count": it.get("voteCount", 0),
        })
    return {"source": "kaggle", "query": query, "resource": resource,
            "count": len(items), "mode": "live", "items": items}


__all__ = ["run"]
