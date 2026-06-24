"""clean.text.empty — drop empty/None/whitespace-only strings."""
from __future__ import annotations

from typing import Any, Dict, List


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Remove None / empty / whitespace-only items.

    params:
        keep_none: bool = False
    """
    keep_none = bool(params.get("keep_none", False))
    out = []
    for x in items:
        if x is None:
            if keep_none:
                out.append(x)
            continue
        if isinstance(x, str) and not x.strip():
            continue
        out.append(x)
    return out