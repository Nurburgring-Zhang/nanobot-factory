"""annot.image.semantic_seg — semantic segmentation mask annotation operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'mask'?: path_or_data_url, 'classes'?: [str]}
    params:
        num_classes: int = 21            — expected class count (Pascal VOC=21, Cityscapes=19)
        include_background: bool = True  — class 0 reserved for background
        compute_histogram: bool = True   — per-class pixel histogram
        min_class_ratio: float = 0.0     — flag classes below this pixel ratio
        method: str = "pascal_voc"       — label scheme hint

Each mask input: 2D array (H,W) of int class indices, or path/data-url of PNG mask.

Returns per-image: {image_index, ok, shape, classes: [str], histogram: {c:count}, ratios}.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _HAS_PIL, decode_data_url, load_image_any

DEFAULT_PASCAL = [
    "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
    "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
    "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor",
]


def _normalize_mask(mask: Any) -> Any:
    """Try to coerce mask input into a 2D integer numpy array."""
    if _HAS_NUMPY and hasattr(mask, "ndim") and getattr(mask, "ndim", 0) >= 2:
        return mask
    if isinstance(mask, (bytes, bytearray)):
        if _HAS_PIL:
            try:
                from PIL import Image as _I
                return _np.asarray(_I.open(io.BytesIO(mask)))
            except Exception:  # noqa: BLE001
                return None
        if _HAS_CV2:
            try:
                import numpy as _np2
                arr = _np2.frombuffer(mask, dtype=_np2.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            except Exception:  # noqa: BLE001
                return None
    if isinstance(mask, str):
        buf = decode_data_url(mask)
        if buf:
            return _normalize_mask(buf)
    return None


def _compute_hist(mask: Any, num_classes: int) -> Dict[int, int]:
    if not _HAS_NUMPY:
        return {}
    try:
        import numpy as _np2
        flat = _np2.asarray(mask).astype("int64").ravel()
        hist = _np2.bincount(flat, minlength=num_classes)
        return {int(c): int(hist[c]) for c in range(num_classes)}
    except Exception:  # noqa: BLE001
        return {}


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    num_classes = int(params.get("num_classes", 21))
    include_bg = bool(params.get("include_background", True))
    do_hist = bool(params.get("compute_histogram", True))
    min_ratio = float(params.get("min_class_ratio", 0.0))
    method = str(params.get("method", "pascal_voc"))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"image_index": i, "method": method}
        if not isinstance(item, dict):
            rec.update({"ok": False, "error": "input_must_be_dict_with_mask"})
            out.append(rec)
            continue
        classes = item.get("classes") or DEFAULT_PASCAL[:num_classes]
        if include_bg and "background" not in classes:
            classes = ["background"] + classes
        mask = _normalize_mask(item.get("mask"))
        if mask is None or not _HAS_NUMPY:
            rec.update({
                "ok": False,
                "error": "mask_decode_failed_or_no_numpy",
                "shape": None,
                "classes": classes,
                "histogram": {},
            })
            out.append(rec)
            continue
        try:
            import numpy as _np2
            shape = list(_np2.asarray(mask).shape)
        except Exception:  # noqa: BLE001
            shape = None
        hist = _compute_hist(mask, num_classes) if do_hist else {}
        total = sum(hist.values()) or 1
        ratios = {c: round(hist.get(c, 0) / total, 6) for c in hist}
        rare = sorted([c for c, r in ratios.items() if 0 < r < min_ratio])
        rec.update({
            "ok": True,
            "shape": shape,
            "classes": classes,
            "histogram": hist,
            "ratios": ratios,
            "rare_classes": rare,
        })
        out.append(rec)
    return out