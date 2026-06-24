"""clarity — 清晰度评分算子 (基于 Laplacian variance, no-PIL fallback).

op_id: score.clarity
"""
from __future__ import annotations

import hashlib
import statistics
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.clarity"
NAME = "清晰度"
CATEGORY = "image"
DESCRIPTION = "图像清晰度评分 (Laplacian variance, 0-100)"
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
                img = Image.open(path).convert("L")
                # Approximate Laplacian via second-derivative convolution
                kernel = ImageFilter.Kernel(
                    size=(3, 3),
                    kernel=[0, 1, 0, 1, -4, 1, 0, 1, 0],
                    scale=1,
                    offset=128,
                )
                lap = img.filter(kernel)
                pixels = list(lap.getdata())
                var = statistics.pvariance(pixels) if len(pixels) > 1 else 0.0
                # var 0..~10000 — clamp to 0-100 via log scale
                import math
                score = min(100.0, max(0.0, math.log1p(var) * 8))
                out.append({
                    "file_path": path,
                    "laplacian_var": round(var, 2),
                    "clarity": round(score, 2),
                })
                continue
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        h = int(_hash_md5(path)[:8], 16)
        out.append({"file_path": path, "clarity": 50 + (h % 50), "mode": "mock"})
    return out[0] if not isinstance(data, list) else out
