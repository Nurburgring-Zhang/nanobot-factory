"""annot.3d.depth_map — depth map annotation operator.

Inputs:
    items: list of dicts {
        image_id?,
        depth: 2D array | path | data-url,
        intrinsics?: {fx, fy, cx, cy},
        valid_mask?: 2D array | path | data-url,
        scale?: float = 1.0
    }
    params:
        min_depth: float = 0.0
        max_depth: float = 1000.0
        unit: str = "m"               — m | cm | mm
        compute_stats: bool = True    — min/max/mean/median/std
        compute_histogram: bool = True
        histogram_bins: int = 64
        require_intrinsics: bool = False

Returns per-item: {item_index, ok, shape, stats: {...}, histogram: {...}, valid_ratio}.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _HAS_PIL, decode_data_url


def _coerce_depth(d: Any):
    """Coerce depth input to a 2D numpy float array, or None."""
    if _HAS_NUMPY and hasattr(d, "ndim"):
        a = d
        if a.ndim == 3:
            a = a.mean(axis=-1) if a.shape[-1] in (3, 4) else a.squeeze()
        return a.astype("float32") if a.ndim == 2 else None
    if isinstance(d, (bytes, bytearray)):
        if _HAS_PIL:
            try:
                from PIL import Image as _I
                import numpy as _np
                return _np.asarray(_I.open(io.BytesIO(d))).astype("float32")
            except Exception:  # noqa: BLE001
                pass
        if _HAS_CV2:
            try:
                import numpy as _np
                arr = _np.frombuffer(d, dtype=_np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if img.ndim == 3:
                        img = img[:, :, 0]
                    return img.astype("float32")
            except Exception:  # noqa: BLE001
                pass
    if isinstance(d, str):
        buf = decode_data_url(d)
        if buf:
            return _coerce_depth(buf)
    return None


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_d = float(params.get("min_depth", 0.0))
    max_d = float(params.get("max_depth", 1000.0))
    unit = str(params.get("unit", "m"))
    do_stats = bool(params.get("compute_stats", True))
    do_hist = bool(params.get("compute_histogram", True))
    bins = int(params.get("histogram_bins", 64))
    require_K = bool(params.get("require_intrinsics", False))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict):
            rec.update({"ok": False, "error": "input_must_be_dict"})
            out.append(rec)
            continue
        scale = float(item.get("scale", 1.0))
        K = item.get("intrinsics")
        if require_K and not isinstance(K, dict):
            rec.update({"ok": False, "error": "missing_intrinsics"})
            out.append(rec)
            continue
        depth = _coerce_depth(item.get("depth"))
        valid = _coerce_depth(item.get("valid_mask"))
        if depth is None or not _HAS_NUMPY:
            rec.update({
                "ok": False,
                "error": "depth_decode_failed_or_no_numpy",
                "shape": None,
            })
            out.append(rec)
            continue
        depth = depth * scale
        if unit == "cm":
            depth = depth / 100.0
        elif unit == "mm":
            depth = depth / 1000.0
        mask_arr = (depth >= min_d) & (depth <= max_d)
        if valid is not None and _HAS_NUMPY:
            mask_arr = mask_arr & (valid > 0)
        import numpy as _np
        valid_pixels = depth[mask_arr] if mask_arr.any() else _np.array([])
        valid_ratio = float(mask_arr.mean()) if mask_arr.size else 0.0
        stats: Dict[str, float] = {}
        if do_stats and valid_pixels.size:
            stats = {
                "min": round(float(valid_pixels.min()), 4),
                "max": round(float(valid_pixels.max()), 4),
                "mean": round(float(valid_pixels.mean()), 4),
                "median": round(float(__import__("numpy").median(valid_pixels)), 4),
                "std": round(float(valid_pixels.std()), 4),
            }
        hist_dict: Dict[str, int] = {}
        if do_hist and valid_pixels.size:
            counts, edges = __import__("numpy").histogram(valid_pixels, bins=bins)
            for j, c in enumerate(counts):
                hist_dict[f"{float(edges[j]):.3f}-{float(edges[j + 1]):.3f}"] = int(c)
        rec.update({
            "ok": True,
            "image_id": item.get("image_id"),
            "shape": list(depth.shape),
            "valid_ratio": round(valid_ratio, 6),
            "unit": "m",
            "stats": stats,
            "histogram": hist_dict,
            "intrinsics": K,
        })
        out.append(rec)
    return out