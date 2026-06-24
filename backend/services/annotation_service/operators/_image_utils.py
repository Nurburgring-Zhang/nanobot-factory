"""annotation_service.operators._image_utils — shared helpers for image ops.

Loaded lazily via importlib so missing cv2/numpy/PIL degrade gracefully.
"""
from __future__ import annotations

import base64
import io
import os
from typing import Any, Dict, Optional, Tuple

try:
    import numpy as _np  # type: ignore
    _HAS_NUMPY = True
except Exception:  # noqa: BLE001
    _np = None
    _HAS_NUMPY = False

try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:  # noqa: BLE001
    cv2 = None
    _HAS_CV2 = False

try:
    from PIL import Image as _PILImage  # type: ignore
    _HAS_PIL = True
except Exception:  # noqa: BLE001
    _PILImage = None
    _HAS_PIL = False


def decode_data_url(data_url: str) -> Optional[bytes]:
    """Decode a `data:image/...;base64,...` URL or a plain base64 string."""
    if not data_url:
        return None
    s = str(data_url)
    if "," in s and s.startswith("data:"):
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s)
    except Exception:  # noqa: BLE001
        return None


def load_image_any(item: Any) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Load an image from various input shapes.

    Accepted input types:
      * PIL/numpy array          — pass through
      * str filesystem path      — cv2.imread
      * str `data:image/...` URL — PIL Image.open
      * str base64               — PIL Image.open
      * dict {'path'|'url'|'data'|'image'|'numpy'|'b64': ...}

    Returns (image, meta). image is None on failure with meta['error'] set.
    """
    meta: Dict[str, Any] = {}
    if item is None:
        return None, {"error": "empty_input"}
    # numpy/PIL already
    if _HAS_NUMPY and isinstance(item, _np.ndarray):
        return item, {"shape": list(item.shape), "source": "ndarray"}
    if _HAS_PIL and isinstance(item, _PILImage.Image):
        return item, {"size": item.size, "mode": item.mode, "source": "pil"}
    if isinstance(item, dict):
        # try common keys
        for key in ("path", "file", "url"):
            v = item.get(key)
            if isinstance(v, str) and os.path.exists(v):
                return _read_path(v)
        for key in ("data", "b64", "image", "base64"):
            v = item.get(key)
            if isinstance(v, str):
                if key in ("data", "image", "url") and v.startswith("data:") or key == "url":
                    buf = decode_data_url(v)
                else:
                    buf = decode_data_url(v)
                if buf:
                    return _read_buffer(buf, hint=key)
        if "numpy" in item and _HAS_NUMPY:
            arr = item["numpy"]
            try:
                return _np.asarray(arr), {"shape": list(_np.asarray(arr).shape), "source": "numpy_field"}
            except Exception as e:  # noqa: BLE001
                return None, {"error": f"numpy_decode_failed: {e}"}
        meta["error"] = "no_known_dict_key"
        return None, meta
    if isinstance(item, str):
        if os.path.exists(item):
            return _read_path(item)
        # treat as data-url or base64
        buf = decode_data_url(item)
        if buf:
            return _read_buffer(buf, hint="string")
        meta["error"] = "string_not_path_or_data_url"
        return None, meta
    meta["error"] = f"unsupported_type: {type(item).__name__}"
    return None, meta


def _read_path(path: str) -> Tuple[Optional[Any], Dict[str, Any]]:
    if not _HAS_CV2 and not _HAS_PIL:
        return None, {"error": "no_image_lib", "path": path}
    if _HAS_CV2:
        try:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is not None:
                return img, {"shape": list(img.shape), "source": "cv2_path", "path": path}
        except Exception as e:  # noqa: BLE001
            return None, {"error": f"cv2_failed: {e}", "path": path}
    if _HAS_PIL:
        try:
            im = _PILImage.open(path).convert("RGB")
            return im, {"size": im.size, "source": "pil_path", "path": path}
        except Exception as e:  # noqa: BLE001
            return None, {"error": f"pil_failed: {e}", "path": path}
    return None, {"error": "all_readers_failed", "path": path}


def _read_buffer(buf: bytes, hint: str = "") -> Tuple[Optional[Any], Dict[str, Any]]:
    if _HAS_PIL:
        try:
            im = _PILImage.open(io.BytesIO(buf)).convert("RGB")
            return im, {"size": im.size, "source": "pil_buffer", "hint": hint}
        except Exception:  # noqa: BLE001
            pass
    if _HAS_CV2:
        try:
            arr = _np.frombuffer(buf, dtype=_np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                return img, {"shape": list(img.shape), "source": "cv2_buffer", "hint": hint}
        except Exception:  # noqa: BLE001
            pass
    return None, {"error": "buffer_decode_failed", "hint": hint}


def ensure_numpy_bgr(img: Any) -> Optional[Any]:
    """Return image as numpy BGR (H,W,3) uint8. None if conversion fails."""
    if not _HAS_NUMPY:
        return None
    if isinstance(img, _np.ndarray):
        if img.ndim == 2:
            img = _np.stack([img] * 3, axis=-1)
        if img.shape[-1] == 4:
            # assume RGBA → BGR
            try:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) if _HAS_CV2 else img[:, :, :3]
            except Exception:  # noqa: BLE001
                img = img[:, :, :3]
        return img
    if _HAS_PIL and isinstance(img, _PILImage.Image):
        a = _np.asarray(img)
        # RGB → BGR
        if a.ndim == 3 and a.shape[-1] == 3:
            a = a[:, :, ::-1].copy()
        return a
    return None


def bbox_iou_xyxy(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Compute IoU between two XYXY bboxes (each {x1,y1,x2,y2})."""
    x1 = max(a["x1"], b["x1"])
    y1 = max(a["y1"], b["y1"])
    x2 = min(a["x2"], b["x2"])
    y2 = min(a["y2"], b["y2"])
    iw = max(0.0, x2 - x1)
    ih = max(0.0, y2 - y1)
    inter = iw * ih
    area_a = max(0.0, a["x2"] - a["x1"]) * max(0.0, a["y2"] - a["y1"])
    area_b = max(0.0, b["x2"] - b["x1"]) * max(0.0, b["y2"] - b["y1"])
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


def polygon_area(points: list) -> float:
    """Shoelace formula. points: [(x,y), ...]."""
    if not points or len(points) < 3:
        return 0.0
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    return abs(area) / 2.0


__all__ = [
    "_HAS_NUMPY",
    "_HAS_CV2",
    "_HAS_PIL",
    "decode_data_url",
    "load_image_any",
    "ensure_numpy_bgr",
    "bbox_iou_xyxy",
    "polygon_area",
]