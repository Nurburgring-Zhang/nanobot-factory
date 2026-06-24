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
On decode failure the record carries ``error`` and ``error_source`` so callers
can distinguish bad PIL bytes from cv2 failures or unsupported input types.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any, Dict, List, Optional, Tuple

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _HAS_PIL, decode_data_url

_log = logging.getLogger(__name__)


def _coerce_depth(d: Any) -> Tuple[Optional[Any], Optional[str]]:
    """Coerce depth input to a 2D numpy float array.

    Returns ``(array_or_None, error_or_None)``. ``error`` is a short string
    like ``"pil_decode_failed: <msg>"`` so callers can surface specific
    reasons without losing them silently.
    """
    if _HAS_NUMPY and hasattr(d, "ndim"):
        a = d
        if a.ndim == 3:
            a = a.mean(axis=-1) if a.shape[-1] in (3, 4) else a.squeeze()
        if a.ndim != 2:
            return None, f"ndarray_not_2d: shape={getattr(a, 'shape', None)}"
        return a.astype("float32"), None
    if isinstance(d, (bytes, bytearray)):
        if _HAS_PIL:
            try:
                from PIL import Image as _I
                import numpy as _np
                arr = _np.asarray(_I.open(io.BytesIO(d))).astype("float32")
                if arr.ndim == 3:
                    arr = arr[:, :, 0]
                if arr.ndim != 2:
                    return None, f"pil_decoded_not_2d: ndim={arr.ndim}"
                return arr, None
            except Exception as exc:  # noqa: BLE001
                _log.debug("depth_map.pil_decode_failed: %s", exc)
                pil_err = f"pil_decode_failed: {exc.__class__.__name__}: {exc}"
        else:
            pil_err = "pil_unavailable"
        if _HAS_CV2:
            try:
                import numpy as _np
                arr = _np.frombuffer(d, dtype=_np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                if img is None:
                    return None, f"{pil_err}; cv2_decode_returned_none"
                if img.ndim == 3:
                    img = img[:, :, 0]
                if img.ndim != 2:
                    return None, f"cv2_decoded_not_2d: ndim={img.ndim}"
                return img.astype("float32"), None
            except Exception as exc:  # noqa: BLE001
                _log.debug("depth_map.cv2_decode_failed: %s", exc)
                return None, f"{pil_err}; cv2_decode_failed: {exc.__class__.__name__}: {exc}"
        return None, f"{pil_err}; cv2_unavailable"
    if isinstance(d, str):
        buf = decode_data_url(d)
        if buf:
            arr, sub_err = _coerce_depth(buf)
            if arr is not None:
                return arr, None
            return None, f"data_url_decode_failed: {sub_err}"
        return None, "string_not_data_url_or_empty"
    if d is None:
        return None, "input_is_none"
    return None, f"unsupported_input_type: {type(d).__name__}"


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
        depth, depth_err = _coerce_depth(item.get("depth"))
        valid, valid_err = _coerce_depth(item.get("valid_mask"))
        if depth is None or not _HAS_NUMPY:
            err_msg = depth_err or "depth_decode_failed"
            if not _HAS_NUMPY:
                err_msg = f"numpy_unavailable; {err_msg}"
            rec.update({
                "ok": False,
                "error": err_msg,
                "error_source": "depth",
                "shape": None,
                "valid_mask_error": valid_err,
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