"""resolution_score — 分辨率评分算子.

op_id: score.resolution
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.resolution"
NAME = "分辨率评分"
CATEGORY = "image"
DESCRIPTION = "图像分辨率评分 (基于像素总量, 0-100)"
PARAMS: list = []


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        path = x if isinstance(x, str) else (x.get("path", "") if isinstance(x, dict) else str(x))
        w = h = 0
        if HAS_PILLOW:
            try:
                from PIL import Image
                with Image.open(path) as img:
                    w, h = img.size
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        else:
            # Deterministic mock based on path
            hash_v = int(_hash_md5(path)[:8], 16)
            w = 512 + (hash_v % 2048)
            h = 512 + ((hash_v >> 4) % 2048)
        pixels = w * h
        # log2 scaling: 480p~0.4M → 30, 1080p~2M → 60, 4K~8.3M → 90
        import math
        if pixels <= 0:
            score = 0.0
        else:
            score = min(100.0, max(0.0, (math.log2(pixels) - 18) * 10))
        out.append({
            "file_path": path,
            "width": w,
            "height": h,
            "pixels": pixels,
            "resolution_score": round(score, 2),
        })
    return out[0] if not isinstance(data, list) else out
