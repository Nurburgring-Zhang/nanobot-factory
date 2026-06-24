"""Shared image utility helpers for cleaning operators.

Loaded once on first import; degrades gracefully if Pillow/cv2/numpy are
unavailable so the service can still return useful metadata in degraded mode.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

try:
    import numpy as np  # noqa: F401
    _HAS_NUMPY = True
except Exception:  # noqa: BLE001
    _HAS_NUMPY = False

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:  # noqa: BLE001
    _HAS_PIL = False

try:
    import cv2  # noqa: F401
    _HAS_CV2 = True
except Exception:  # noqa: BLE001
    _HAS_CV2 = False


def capabilities() -> Dict[str, bool]:
    return {
        "numpy": _HAS_NUMPY,
        "PIL": _HAS_PIL,
        "cv2": _HAS_CV2,
    }


def _load_image(item: Union[str, bytes, bytearray, Dict[str, Any]]):
    """Load a PIL Image from path / bytes / or dict with 'path'/'bytes'.

    Returns (image, source_meta) or raises.
    """
    if not _HAS_PIL:
        raise RuntimeError("Pillow not available")
    if isinstance(item, (bytes, bytearray)):
        return Image.open(io.BytesIO(item)), {"source": "bytes", "size": len(item)}
    if isinstance(item, str):
        if not os.path.exists(item):
            # Return None with missing flag; caller decides whether to skip
            return None, {"source": "path", "path": item, "missing": True}
        img = Image.open(item)
        try:
            img.load()
        except Exception as e:  # noqa: BLE001
            return None, {"source": "path", "path": item, "error": f"load_failed: {e}"}
        return img, {"source": "path", "path": item, "size": os.path.getsize(item)}
    if isinstance(item, dict):
        if "bytes" in item:
            return _load_image(item["bytes"])
        if "path" in item:
            return _load_image(item["path"])
    raise ValueError(f"unsupported image input type: {type(item).__name__}")


def to_grayscale_array(pil_image) -> "np.ndarray":
    """Convert PIL image to uint8 grayscale numpy array."""
    import numpy as np
    g = pil_image.convert("L")
    return np.asarray(g, dtype=np.uint8)


def laplacian_variance(gray: "np.ndarray") -> float:
    """Laplacian variance — sharp image if high (>100), blurred if low (<100)."""
    import numpy as np
    if not _HAS_CV2:
        # Pure-numpy Laplacian approximation (4-neighbour)
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        from scipy.ndimage import convolve
        lap = convolve(gray.astype(np.float32), kernel)
        return float(lap.var())
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def phash_64(gray: "np.ndarray") -> int:
    """64-bit perceptual hash (8x8 average hash).

    Robust to small resize + color shift. Distance ≤ 10 ≈ near-duplicate.
    """
    from PIL import Image as PILImage
    import numpy as np
    pil = PILImage.fromarray(gray).resize((8, 8), PILImage.BILINEAR)
    arr = np.asarray(pil, dtype=np.float32)
    avg = arr.mean()
    bits = (arr > avg).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def color_histogram_features(pil_image) -> "np.ndarray":
    """4x4x4 RGB histogram (64-dim) as a compact semantic-style descriptor."""
    import numpy as np
    img = pil_image.convert("RGB").resize((128, 128))
    arr = np.asarray(img, dtype=np.uint8)
    feat = np.zeros((4, 4, 4), dtype=np.float32)
    for r, g, b in arr.reshape(-1, 3):
        feat[r >> 6, g >> 6, b >> 6] += 1.0
    feat /= max(1.0, feat.sum())
    return feat.flatten()


def cosine_distance(a: "np.ndarray", b: "np.ndarray") -> float:
    import numpy as np
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def skin_tone_ratio(pil_image) -> float:
    """Approximate skin-tone pixel ratio using YCbCr heuristics.

    Returns ratio in [0, 1]. >0.35 suggests NSFW (loose heuristic).
    """
    import numpy as np
    arr = np.asarray(pil_image.convert("YCbCr").resize((128, 128)))
    Y, Cb, Cr = arr[..., 0].astype(np.float32), arr[..., 1].astype(np.float32), arr[..., 2].astype(np.float32)
    mask = (
        (Y > 80) & (Cb > 77) & (Cb < 135) &
        (Cr > 133) & (Cr < 180) &
        (Cr > Cb)
    )
    return float(mask.mean())


def black_border_ratio(pil_image, edge_thresh: int = 8) -> float:
    """Estimate ratio of pixels in the border region that are 'black'.

    Used for both image-vignette detection and video frame border check.
    """
    import numpy as np
    g = np.asarray(pil_image.convert("L"))
    h, w = g.shape
    top = g[:edge_thresh, :]
    bot = g[-edge_thresh:, :]
    left = g[:, :edge_thresh]
    right = g[:, -edge_thresh:]
    border = np.concatenate([top.flatten(), bot.flatten(), left.flatten(), right.flatten()])
    return float((border < 16).mean())