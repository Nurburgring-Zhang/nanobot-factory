"""collect.bilibili_dl — Bilibili video metadata + subtitle.

Recognizes BV IDs and av IDs. Sandbox returns deterministic mock.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import deterministic_id, mock_response

_BILI = re.compile(r"(?:bilibili\.com/video/)([Bb][Vv][0-9A-Za-z]+|av\d+)", re.I)


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    m = _BILI.search(query)
    if m:
        vid = m.group(1)
        items: List[Dict[str, Any]] = [{
            "id": vid,
            "title": f"Bilibili video {vid}",
            "url": f"https://www.bilibili.com/video/{vid}",
            "duration_sec": 0,
            "uploader": "",
            "play_count": 0,
        }]
    else:
        items = mock_response("bilibili", query, count=max_results, kind="video")
        for it in items:
            it["duration_sec"] = 0
            it["uploader"] = ""
    return {
        "source": "bilibili",
        "query": query,
        "count": len(items),
        "items": items,
    }


__all__ = ["run"]
