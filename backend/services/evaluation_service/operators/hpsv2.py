"""eval.hpsv2 — Human Preference Score v2 (heuristic, no model load).

HPSv2 (Wu et al. 2023) uses CLIP-based reward model. We provide a
deterministic proxy combining:
  - CLIP-style alignment (token overlap with caption)
  - aesthetic signal
  - image quality signal (low noise / blur)
  - text-image length harmony

Output: 0.0 - 1.0 (higher = preferred by humans).
"""
from __future__ import annotations

import io
import math
import re
from typing import Any, Dict, List

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set:
    return set(_TOKEN.findall(s.lower()))


def _pil(img: Any):
    try:
        from PIL import Image
        if isinstance(img, (bytes, bytearray)):
            return Image.open(io.BytesIO(img))
        if isinstance(img, str):
            return Image.open(img)
        if isinstance(img, dict) and "path" in img:
            return Image.open(img["path"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _quality_signals(img) -> Dict[str, float]:
    import numpy as np
    if img is None:
        return {"laplacian_var": 0.0, "noise": 1.0, "dark_ratio": 0.5}
    g = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = g.shape
    if h < 3 or w < 3:
        return {"laplacian_var": 0.0, "noise": 1.0, "dark_ratio": 0.5}
    # 4-neighbor laplacian
    g2 = g[1:-1, 1:-1]
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g2)
    lap_var = float(lap.var())
    # robust noise (median abs deviation of high-pass)
    hp = np.abs(lap - np.median(lap))
    noise = float(hp.mean() / 255.0)
    dark = float((g < 32).mean())
    return {"laplacian_var": lap_var, "noise": noise, "dark_ratio": dark}


def _hps_score(text: str, image: Any) -> Dict[str, float]:
    t = _tokens(text or "")
    if isinstance(image, dict):
        cap = str(image.get("caption", ""))
        tags = " ".join(image.get("tags", []) or [])
        textual = (cap + " " + tags).strip()
    else:
        textual = ""
    img_tokens = _tokens(textual)
    if t and img_tokens:
        align = len(t & img_tokens) / max(1, len(t))
    else:
        align = 0.0
    sig = _quality_signals(_pil(image))
    # Quality: high laplacian var, low noise, balanced dark ratio
    sharpness = min(1.0, sig["laplacian_var"] / 400.0)
    cleanness = max(0.0, 1.0 - 4.0 * sig["noise"])
    balanced = 1.0 - abs(sig["dark_ratio"] - 0.3) * 1.5
    balanced = max(0.0, min(1.0, balanced))
    n = len(t)
    length_fit = 1.0 if 3 <= n <= 60 else max(0.0, 1.0 - abs(n - 30) / 50.0)
    score = (
        0.35 * align
        + 0.25 * sharpness
        + 0.20 * cleanness
        + 0.10 * balanced
        + 0.10 * length_fit
    )
    return {
        "hps": round(max(0.0, min(1.0, score)), 4),
        "alignment": round(align, 4),
        "sharpness": round(sharpness, 4),
        "cleanness": round(cleanness, 4),
        "balanced": round(balanced, 4),
        "length_fit": round(length_fit, 4),
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of {text, image} or {prompt, image} dicts."""
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.4))
    out: List[Dict[str, Any]] = []
    scores: List[float] = []
    for i, it in enumerate(items):
        if isinstance(it, dict):
            text = it.get("text") or it.get("prompt") or ""
            image = it.get("image")
        else:
            text, image = str(it), None
        s = _hps_score(text, image)
        scores.append(s["hps"])
        out.append({"sample_id": i, **s, "above_threshold": s["hps"] >= threshold})
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(scores),
            "hps_mean": round(sum(scores) / max(1, len(scores)), 4),
        }]
    return out


__all__ = ["run"]
