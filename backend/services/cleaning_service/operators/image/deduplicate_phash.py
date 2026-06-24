"""clean.image.deduplicate.phash — 64-bit perceptual hash near-duplicate detection."""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, _load_image, hamming, phash_64, to_grayscale_array


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Drop near-duplicates based on perceptual hash (hamming distance ≤ threshold).

    params:
        hamming_threshold: int = 10   (0..64; smaller = stricter)
    """
    threshold = int(params.get("hamming_threshold", 10))
    if not _HAS_NUMPY:
        # Degraded mode: fall back to MD5 exact dedup
        import hashlib
        seen = set()
        out: List[Any] = []
        for x in items:
            h = hashlib.md5(repr(x).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            out.append(x)
        return out

    hashes: List[int] = []
    out: List[Any] = []
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception:  # noqa: BLE001
            continue
        if img is None:
            continue
        try:
            gray = to_grayscale_array(img)
            h = phash_64(gray)
        except Exception:  # noqa: BLE001
            continue
        is_dup = False
        for prev in hashes:
            if hamming(h, prev) <= threshold:
                is_dup = True
                break
        if not is_dup:
            hashes.append(h)
            out.append(x)
    return out