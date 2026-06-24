"""clean.text.deduplicate — SimHash + exact dedup hybrid."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List


def _simhash(s: str) -> int:
    """64-bit SimHash approximation."""
    grams = [s[i:i + 3] for i in range(len(s) - 2)]
    if not grams:
        return 0
    h = 0
    for g in grams:
        h = (h * 31 + hash(g)) & 0xFFFFFFFF
    return h


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Drop exact-duplicate strings + near-duplicates via SimHash.

    params:
        hamming_threshold: int = 3
        enable_exact: bool = True
    """
    threshold = int(params.get("hamming_threshold", 3))
    enable_exact = bool(params.get("enable_exact", True))
    seen_exact = set()
    seen_hashes = []
    out = []
    for x in items:
        s = x if isinstance(x, str) else repr(x)
        if enable_exact:
            h = hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()
            if h in seen_exact:
                continue
            seen_exact.add(h)
        sh = _simhash(s)
        is_dup = False
        for prev in seen_hashes:
            if _hamming(sh, prev) <= threshold:
                is_dup = True
                break
        if is_dup:
            continue
        seen_hashes.append(sh)
        out.append(x)
    return out