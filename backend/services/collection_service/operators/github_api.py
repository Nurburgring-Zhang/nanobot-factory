"""collect.github_api — GitHub repository / code / issues search.

Live: GET https://api.github.com/search/repositories?q=...
Sandbox: deterministic mock.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    resource = params.get("resource", "repositories")  # repositories|code|issues
    if is_sandbox():
        items = mock_response("github", query, count=max_results, kind=resource.rstrip("s"))
        for it in items:
            it["full_name"] = f"user/{it['id']}"
            it["description"] = f"GitHub {resource} matching: {query}"
            it["stars"] = abs(hash(it["id"])) % 10000
            it["html_url"] = f"https://github.com/user/{it['id']}"
        return {
            "source": "github",
            "query": query,
            "resource": resource,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    r = safe_get(f"https://api.github.com/search/{resource}",
                 params={"q": query, "per_page": max_results}, timeout=8.0)
    if not isinstance(r, dict) or "items" not in r:
        return {"source": "github", "query": query, "count": 0, "mode": "error", "items": []}
    items: List[Dict[str, Any]] = []
    for it in r.get("items", []):
        items.append({
            "id": str(it.get("id")),
            "title": it.get("full_name") or it.get("title", ""),
            "description": it.get("description", ""),
            "url": it.get("html_url", ""),
            "stars": it.get("stargazers_count", 0),
        })
    return {"source": "github", "query": query, "resource": resource,
            "count": len(items), "mode": "live", "items": items}


__all__ = ["run"]
