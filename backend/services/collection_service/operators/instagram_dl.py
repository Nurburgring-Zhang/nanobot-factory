"""collect.instagram_dl — Instagram post / reel collection.

Recognizes /p/, /reel/, /tv/ shortcodes. Sandbox returns deterministic mock.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import deterministic_id, mock_response

_IG = re.compile(r"instagram\.com/(?:p|reel|tv)/([\w\-]+)", re.I)


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    m = _IG.search(query)
    if m:
        shortcode = m.group(1)
        items: List[Dict[str, Any]] = [{
            "id": shortcode,
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "type": "post",
            "caption": f"Instagram post {shortcode}",
            "media_urls": [],
        }]
    else:
        items = mock_response("instagram", query, count=max_results, kind="post")
        for it in items:
            it["type"] = "post"
            it["caption"] = it.get("title", "")
            it["media_urls"] = []
    return {
        "source": "instagram",
        "query": query,
        "count": len(items),
        "items": items,
    }


__all__ = ["run"]
