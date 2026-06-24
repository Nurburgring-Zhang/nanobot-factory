"""clean.text.length — filter items by character length."""
from __future__ import annotations

from typing import Any, Dict, List


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep items where len(str(item)) is in [min, max].

    params:
        min_chars: int = 1
        max_chars: int = 100000
    """
    lo = int(params.get("min_chars", 1))
    hi = int(params.get("max_chars", 100000))
    out = []
    for x in items:
        n = len(x) if isinstance(x, str) else (len(x) if hasattr(x, "__len__") else 1)
        if lo <= n <= hi:
            out.append(x)
    return out