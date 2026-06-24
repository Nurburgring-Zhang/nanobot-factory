"""Shared video utility helpers."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    import cv2  # noqa: F401
    _HAS_CV2 = True
except Exception:  # noqa: BLE001
    _HAS_CV2 = False

try:
    import numpy as np  # noqa: F401
    _HAS_NUMPY = True
except Exception:  # noqa: BLE001
    _HAS_NUMPY = False


def capabilities() -> Dict[str, bool]:
    return {"cv2": _HAS_CV2, "numpy": _HAS_NUMPY}


def probe(path: str) -> Dict[str, Any]:
    """Open a video file and return its metadata; {} on failure."""
    if not _HAS_CV2 or not isinstance(path, str) or not os.path.exists(path):
        return {}
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return {}
        meta = {
            "path": path,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS)) or 0.0,
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "duration": float(cap.get(cv2.CAP_PROP_FRAME_COUNT)) /
                        (float(cap.get(cv2.CAP_PROP_FPS)) or 25.0),
        }
        cap.release()
        return meta
    except Exception as e:  # noqa: BLE001
        return {"path": path, "error": str(e)}


def iter_frames(path: str, max_frames: int = 16, stride: int = 1) -> Iterator[Any]:
    """Yield up to `max_frames` from a video at every `stride`-th frame."""
    if not _HAS_CV2:
        return
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return
    try:
        idx = 0
        yielded = 0
        while yielded < max_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if idx % stride == 0:
                yield frame
                yielded += 1
            idx += 1
    finally:
        cap.release()


def get_metadata(item: Any) -> Dict[str, Any]:
    """Extract metadata from either a path-string or a dict."""
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, str):
        return probe(item)
    return {}


def black_border_ratio_frame(frame: "np.ndarray", edge: int = 8) -> float:
    """Ratio of border pixels that are near-black (BGR uint8)."""
    import numpy as np
    g = cv2_to_gray(frame) if _HAS_CV2 else frame.mean(axis=2)
    h, w = g.shape
    if h < 2 * edge or w < 2 * edge:
        return 0.0
    border = np.concatenate([
        g[:edge, :].flatten(),
        g[-edge:, :].flatten(),
        g[:, :edge].flatten(),
        g[:, -edge:].flatten(),
    ])
    return float((border < 16).mean())


def cv2_to_gray(frame: "np.ndarray") -> "np.ndarray":
    import cv2
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def static_frame_score(frames: List["np.ndarray"]) -> float:
    """Mean frame-to-frame pixel difference (0..1). <0.02 = static."""
    import numpy as np
    if len(frames) < 2:
        return 1.0
    diffs = []
    for i in range(1, len(frames)):
        a = cv2_to_gray(frames[i - 1]).astype(np.float32)
        b = cv2_to_gray(frames[i]).astype(np.float32)
        diffs.append(float(np.abs(a - b).mean()) / 255.0)
    return float(np.mean(diffs))


def phash_64_from_array(gray: "np.ndarray") -> int:
    from PIL import Image
    pil = Image.fromarray(gray).resize((8, 8), Image.BILINEAR)
    import numpy as np
    arr = np.asarray(pil, dtype=np.float32)
    avg = arr.mean()
    bits = (arr > avg).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")