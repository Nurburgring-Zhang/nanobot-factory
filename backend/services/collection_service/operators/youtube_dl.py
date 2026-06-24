"""collect.youtube_dl — YouTube video metadata + thumbnail download.

Real impl uses yt-dlp (optional). In sandbox mode returns deterministic
metadata from a query. Recognizes both video URL and search query.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import deterministic_id, is_sandbox, mock_response

_YT_URL = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/))([\w\-]{6,15})", re.I)


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    include_meta = bool(params.get("include_meta", True))
    m = _YT_URL.search(query)
    if m:
        vid = m.group(1)
        items: List[Dict[str, Any]] = [{
            "id": vid,
            "title": f"YouTube Video {vid}",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "duration_sec": 0,
            "channel": "",
        }]
    else:
        if is_sandbox():
            items = mock_response("youtube", query, count=max_results, kind="video")
        else:
            items = [{
                "id": deterministic_id(f"yt:{query}:{i}", "yt"),
                "title": f"YouTube result {i + 1}: {query}",
                "url": f"https://www.youtube.com/watch?v={deterministic_id(query + str(i), 'yt')}",
                "thumbnail": "",
                "duration_sec": 0,
                "channel": "",
            } for i in range(max_results)]
    return {
        "source": "youtube",
        "query": query,
        "count": len(items),
        "include_meta": include_meta,
        "items": items,
    }


__all__ = ["run"]
