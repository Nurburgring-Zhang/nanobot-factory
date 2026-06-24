"""collect.arxiv_api — arXiv paper search.

Live: GET http://export.arxiv.org/api/query?search_query=...&max_results=...
Parses Atom XML with regex. Sandbox: deterministic mock.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import is_sandbox, mock_response, safe_get

_ARXIV = re.compile(r"<entry>(.*?)</entry>", re.S)
_ARXIV_ID = re.compile(r"<id>.*?/abs/([^<]+)</id>")


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    if is_sandbox():
        items = mock_response("arxiv", query, count=max_results, kind="paper")
        for it in items:
            it["arxiv_id"] = f"2401.{abs(hash(it['id'])) % 99999:05d}"
            it["authors"] = ["Author A", "Author B"]
            it["summary"] = f"Abstract for paper about: {query} (sandbox mock)"
            it["pdf_url"] = f"https://arxiv.org/pdf/{it['arxiv_id']}.pdf"
        return {
            "source": "arxiv",
            "query": query,
            "count": len(items),
            "mode": "mock",
            "items": items,
        }
    r = safe_get("http://export.arxiv.org/api/query",
                 params={"search_query": query, "max_results": max_results},
                 timeout=10.0)
    if not isinstance(r, dict) or "_raw" not in r:
        return {"source": "arxiv", "query": query, "count": 0, "mode": "error", "items": []}
    raw = r.get("_raw", "")
    items: List[Dict[str, Any]] = []
    for chunk in _ARXIV.findall(raw):
        idm = _ARXIV_ID.search(chunk)
        arxiv_id = idm.group(1) if idm else ""
        title_m = re.search(r"<title>(.*?)</title>", chunk, re.S)
        summary_m = re.search(r"<summary>(.*?)</summary>", chunk, re.S)
        items.append({
            "id": arxiv_id,
            "arxiv_id": arxiv_id,
            "title": (title_m.group(1).strip() if title_m else ""),
            "summary": (summary_m.group(1).strip() if summary_m else ""),
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else "",
        })
    return {"source": "arxiv", "query": query, "count": len(items),
            "mode": "live", "items": items}


__all__ = ["run"]
