"""eval.aesthetic_predict — Aesthetic quality predictor (heuristic).

Real LAION aesthetic predictor uses a CLIP+MLP head. We provide a
deterministic proxy based on:
  - brightness, contrast (std of luminance)
  - saturation (HSV)
  - colorfulness (Hasler-Süsstrunk)
  - rule-of-thirds alignment proxy (gradient energy near thirds lines)
  - face-count proxy via symmetry score (low-cost)

Output: 1.0 - 10.0 float (LAION scale).
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List


def _load_pil(image: Any):
    try:
        from PIL import Image
        if isinstance(image, (bytes, bytearray)):
            return Image.open(io.BytesIO(image)).convert("RGB")
        if isinstance(image, str):
            return Image.open(image).convert("RGB")
        if isinstance(image, dict) and "path" in image:
            return Image.open(image["path"]).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    return None


def _brightness_contrast_saturation(img) -> Dict[str, float]:
    import numpy as np
    a = np.asarray(img, dtype=np.float32) / 255.0  # H,W,3
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    bright = float(lum.mean())
    contrast = float(lum.std())
    mx = a.max(axis=-1)
    mn = a.min(axis=-1)
    sat = float((mx - mn).mean())
    return {"brightness": bright, "contrast": contrast, "saturation": sat}


def _colorfulness(img) -> float:
    import numpy as np
    a = np.asarray(img, dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    rg = np.abs(r - g)
    yb = np.abs(0.5 * (r + g) - b)
    mean_rg, std_rg = float(rg.mean()), float(rg.std())
    mean_yb, std_yb = float(yb.mean()), float(yb.std())
    return float(math.sqrt(std_rg ** 2 + std_yb ** 2 + 0.3 * (mean_rg ** 2 + mean_yb ** 2)))


def _symmetry_proxy(img) -> float:
    import numpy as np
    a = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    h, w = a.shape
    if h < 4 or w < 4:
        return 0.0
    left = a[:, :w // 2]
    right = np.fliplr(a[:, w - w // 2:])
    if left.shape != right.shape:
        return 0.0
    diff = float(np.abs(left - right).mean())
    return max(0.0, 1.0 - 4 * diff)


def _aesthetic_score(img) -> Dict[str, Any]:
    if img is None:
        return {"score": None, "features": {}}
    try:
        bc = _brightness_contrast_saturation(img)
        cf = _colorfulness(img)
        sym = _symmetry_proxy(img)
    except Exception as e:  # noqa: BLE001
        return {"score": None, "features": {"error": str(e)}}
    # bell-curve scoring: ideal bright ~ 0.45, contrast ~ 0.25, sat ~ 0.2
    bright = 1.0 - abs(bc["brightness"] - 0.45) * 2.0
    contr = min(1.0, bc["contrast"] / 0.30)
    sat = min(1.0, bc["saturation"] / 0.30)
    col = min(1.0, cf / 50.0)
    sym_n = min(1.0, sym)
    raw = 0.25 * bright + 0.20 * contr + 0.20 * sat + 0.20 * col + 0.15 * sym_n
    score = 1.0 + 9.0 * max(0.0, min(1.0, raw))
    return {
        "score": round(float(score), 3),
        "features": {
            "brightness": round(bc["brightness"], 3),
            "contrast": round(bc["contrast"], 3),
            "saturation": round(bc["saturation"], 3),
            "colorfulness": round(cf, 3),
            "symmetry": round(sym, 3),
        },
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of image paths/bytes/dicts.

    params:
        mode: "score" | "filter" | "aggregate"
        threshold: float = 5.0
    """
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 5.0))
    out: List[Dict[str, Any]] = []
    scores: List[float] = []
    for i, it in enumerate(items):
        img = _load_pil(it)
        s = _aesthetic_score(img)
        score = s.get("score")
        scores.append(score if score is not None else 0.0)
        out.append({
            "sample_id": i,
            "aesthetic": s.get("score"),
            "features": s.get("features", {}),
            "above_threshold": (score is not None and score >= threshold),
        })
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        valid = [s for s in scores if s is not None and s > 0]
        out = [{
            "count": len(scores),
            "mean": round(sum(valid) / max(1, len(valid)), 3),
            "max": round(max(valid, default=0.0), 3),
            "min": round(min(valid, default=0.0), 3),
        }]
    return out


__all__ = ["run"]
