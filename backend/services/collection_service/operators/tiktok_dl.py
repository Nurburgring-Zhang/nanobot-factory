"""collect.tiktok_dl — TikTok video collection.

Recognizes tiktok short URL / @user/video/{id} pattern.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import deterministic_id, mock_response

_TT = re.compile(r"tiktok\.com/(?:@[\w\.\-]+/video/|v/)(\d+)", re.I)
_TT_SHORT = re.compile(r"vm\.tiktok\.com/([\w]+)", re.I)


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    m = _TT.search(query) or _TT_SHORT.search(query)
    if m:
        vid = m.group(1)
        items: List[Dict[str, Any]] = [{
            "id": vid,
            "url": f"https://www.tiktok.com/video/{vid}",
            "title": f"TikTok {vid}",
            "duration_sec": 0,
            "play_count": 0,
        }]
    else:
        items = mock_response("tiktok", query, count=max_results, kind="video")
        for it in items:
            it["duration_sec"] = 0
            it["play_count"] = 0
    return {
        "source": "tiktok",
        "query": query,
        "count": len(items),
        "items": items,
    }


__all__ = ["run"]
