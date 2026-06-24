"""collect.twitter_dl — Twitter / X post / thread collection.

In sandbox: returns deterministic mock items keyed on query.
Live mode: placeholder; real impl requires bearer-token auth.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ._utils import deterministic_id, is_sandbox, mock_response

_TWITTER_URL = re.compile(r"(?:twitter\.com|x\.com)/(\w+)/status/(\d+)", re.I)


def run(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    max_results = int(params.get("max_results", 5))
    m = _TWITTER_URL.search(query)
    if m:
        user, status_id = m.group(1), m.group(2)
        items: List[Dict[str, Any]] = [{
            "id": status_id,
            "author": user,
            "url": f"https://x.com/{user}/status/{status_id}",
            "text": f"[Twitter/X] post {status_id} by {user}",
            "lang": "en",
            "metrics": {"likes": 0, "retweets": 0, "replies": 0},
        }]
    else:
        seed = query if not is_sandbox() else f"twitter:{query}"
        items = [{
            "id": deterministic_id(f"{seed}:{i}", "tweet"),
            "author": f"user_{deterministic_id(seed, 'u')[:6]}",
            "url": f"https://x.com/user/status/{deterministic_id(seed + str(i), 't')}",
            "text": f"Tweet {i + 1} about: {query}",
            "lang": "en",
            "metrics": {"likes": 100 - i * 5, "retweets": 30 - i, "replies": 5},
        } for i in range(max_results)]
    return {
        "source": "twitter",
        "query": query,
        "count": len(items),
        "items": items,
    }


__all__ = ["run"]
