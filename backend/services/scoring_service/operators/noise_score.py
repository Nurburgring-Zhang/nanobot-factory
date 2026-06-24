"""noise_score — 噪声评分算子 (基于像素差分方差, 越高越噪声).

op_id: score.noise
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.noise"
NAME = "噪声评分"
CATEGORY = "image"
DESCRIPTION = "图像噪声评分 (高频方差, 0-100, 越低越干净)"
PARAMS: list = []


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        path = x if isinstance(x, str) else (x.get("path", "") if isinstance(x, dict) else str(x))
        if HAS_PILLOW:
            try:
                from PIL import Image, ImageFilter
                img = Image.open(path).convert("L").resize((128, 128))
                blurred = img.filter(ImageFilter.GaussianBlur(radius=1))
                # High-freq = original − blurred
                import statistics
                d1 = list(img.getdata())
                d2 = list(blurred.getdata())
                residuals = [abs(a - b) for a, b in zip(d1, d2)]
                noise = statistics.mean(residuals) if residuals else 0
                # Score: noise 0 → 100 (clean), noise 30 → 0 (very noisy)
                score = max(0.0, min(100.0, 100 - noise * 3.3))
                out.append({
                    "file_path": path,
                    "noise_level": round(noise, 2),
                    "noise_score": round(score, 2),  # higher = cleaner
                })
                continue
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        h_ = int(_hash_md5(path)[:8], 16)
        out.append({"file_path": path, "noise_score": 50 + (h_ % 50), "mode": "mock"})
    return out[0] if not isinstance(data, list) else out
