"""clean.video.deduplicate — near-duplicate via perceptual hash on sampled frames."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, _HAS_NUMPY, cv2_to_gray, hamming, iter_frames, phash_64_from_array


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Sample 4 frames per video; perceptual-hash them; compare sets.

    params:
        hamming_threshold: int = 12
        frames_per_video: int = 4
    """
    threshold = int(params.get("hamming_threshold", 12))
    nframes = int(params.get("frames_per_video", 4))
    if not _HAS_CV2 or not _HAS_NUMPY:
        # Fallback: MD5 dedup on path
        import hashlib
        seen = set(); out = []
        for x in items:
            h = hashlib.md5(repr(x).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h); out.append(x)
        return out

    signatures: List[List[int]] = []
    out: List[Any] = []
    for x in items:
        if not isinstance(x, str):
            continue
        frames = list(iter_frames(x, max_frames=nframes))
        if not frames:
            continue
        sig = []
        try:
            for f in frames:
                g = cv2_to_gray(f)
                sig.append(phash_64_from_array(g))
        except Exception:  # noqa: BLE001
            continue
        # Compare to previous signatures: if ≥60% frames are near-duplicates → drop
        is_dup = False
        for prev in signatures:
            near = sum(1 for h in sig if any(hamming(h, p) <= threshold for p in prev))
            if near >= max(1, int(0.6 * len(sig))):
                is_dup = True
                break
        if not is_dup:
            signatures.append(sig)
            out.append(x)
    return out