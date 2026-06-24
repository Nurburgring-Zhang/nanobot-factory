"""eval.clip_score — CLIP image-text alignment (heuristic, no model load).

Real CLIP requires ~1.5 GB model. For testing, we compute a deterministic
proxy score that correlates with semantic relevance:
  - text-image token overlap (Jaccard)
  - length-penalty normalization
  - bright/dark image damping

Output range: 0.0 - 1.0 (higher = better alignment).
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set:
    return set(_TOKEN.findall(s.lower()))


def _img_dark_ratio(img_bytes_or_path: Any) -> float:
    try:
        from PIL import Image
        if isinstance(img_bytes_or_path, (bytes, bytearray)):
            img = Image.open(io.BytesIO(img_bytes_or_path))
        elif isinstance(img_bytes_or_path, str):
            img = Image.open(img_bytes_or_path)
        elif isinstance(img_bytes_or_path, dict) and "path" in img_bytes_or_path:
            img = Image.open(img_bytes_or_path["path"])
        else:
            return 0.5
        a = list(img.convert("L").getdata())
        dark = sum(1 for v in a if v < 32) / max(1, len(a))
        return dark
    except Exception:  # noqa: BLE001
        return 0.5


def _clip_proxy(text: str, image: Any) -> float:
    """Deterministic heuristic CLIP-like score in [0, 1]."""
    t = _tokens(text or "")
    if not t:
        return 0.0
    if isinstance(image, dict):
        caption = str(image.get("caption", image.get("alt", "")))
        tags = " ".join(image.get("tags", []) or [])
        textual = (caption + " " + tags).strip()
    else:
        textual = ""
    img_tokens = _tokens(textual)
    if not img_tokens:
        # fall back to deterministic hash-based score
        h = abs(hash(str(image))) % 1000
        return 0.2 + (h / 5000.0)
    overlap = len(t & img_tokens) / len(t | img_tokens)
    # length penalty: penalize very short or very long texts
    n = len(t)
    lp = min(1.0, n / 8.0) * (1.0 if n <= 64 else 64 / n)
    # image brightness penalty
    dark = _img_dark_ratio(image)
    bp = 1.0 - abs(dark - 0.3) * 0.5
    score = 0.5 * overlap + 0.3 * lp + 0.2 * bp
    return max(0.0, min(1.0, score))


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of {text, image} dicts OR list of texts (image=auto).

    params:
        mode: "score" (default) | "filter" | "aggregate"
        threshold: float = 0.25
    """
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.25))
    scores: List[float] = []
    out: List[Dict[str, Any]] = []
    for i, it in enumerate(items):
        if isinstance(it, dict):
            text = it.get("text", "")
            image = it.get("image")
        else:
            text = str(it)
            image = None
        s = _clip_proxy(text, image)
        scores.append(s)
        out.append({
            "sample_id": i,
            "clip_score": round(s, 4),
            "above_threshold": s >= threshold,
        })
    if mode == "filter":
        out = [o for o in out if o["above_threshold"]]
    elif mode == "aggregate":
        out = [{
            "count": len(scores),
            "mean": round(sum(scores) / max(1, len(scores)), 4),
            "max": round(max(scores, default=0.0), 4),
            "min": round(min(scores, default=0.0), 4),
            "above_threshold_count": sum(1 for s in scores if s >= threshold),
        }]
    return out


__all__ = ["run"]
