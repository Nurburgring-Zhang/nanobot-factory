"""collect.web_crawler — Generic webpage HTML/text extraction.

items: query is a URL; params may include max_chars, follow_redirects.
Uses httpx + regex HTML strip; falls back to mock if network unavailable.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from ._utils import is_sandbox, mock_response, parse_url_host, safe_get

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_chars = int(params.get("max_chars", 4096))
    timeout = float(params.get("timeout", 5.0))
    host = parse_url_host(query) or query
    if is_sandbox() or not query.startswith("http"):
        return {
            "mode": "mock",
            "source": "web_crawler",
            "host": host,
            "query": query,
            "items": mock_response("web_crawler", host, count=3, kind="page"),
        }
    r = safe_get(query, timeout=timeout)
    if r is None:
        return {
            "mode": "mock",
            "source": "web_crawler",
            "host": host,
            "query": query,
            "items": mock_response("web_crawler", host, count=1, kind="page"),
            "note": "network_unavailable",
        }
    raw = r.get("_raw", "")
    if raw:
        text = _WS.sub(" ", _HTML_TAG.sub(" ", raw)).strip()[:max_chars]
    else:
        text = ""
    return {
        "mode": "live",
        "source": "web_crawler",
        "host": host,
        "query": query,
        "items": [{
            "id": f"page_{hash(query) & 0xffffff:06x}",
            "title": host,
            "url": query,
            "text": text,
            "char_count": len(text),
        }],
    }


__all__ = ["run"]
