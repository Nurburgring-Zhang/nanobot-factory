"""clean.image.deduplicate.md5 — exact MD5 deduplication for images."""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List


def _md5(x: Any) -> str:
    if isinstance(x, (bytes, bytearray)):
        return hashlib.md5(bytes(x)).hexdigest()
    if isinstance(x, str) and os.path.exists(x):
        h = hashlib.md5()
        with open(x, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    if isinstance(x, str):
        return hashlib.md5(x.encode("utf-8", errors="ignore")).hexdigest()
    return hashlib.md5(repr(x).encode()).hexdigest()


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Drop items with duplicate MD5 hashes (keep first occurrence)."""
    seen = set()
    out: List[Any] = []
    for x in items:
        h = _md5(x)
        if h in seen:
            continue
        seen.add(h)
        out.append(x)
    return out