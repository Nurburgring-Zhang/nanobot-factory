"""technical — 技术质量评分算子 (sharpness + brightness 综合).

op_id: score.technical
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.technical"
NAME = "技术质量"
CATEGORY = "image"
DESCRIPTION = "图像技术质量 (sharpness + brightness, 0-100)"
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
                from PIL import Image, ImageStat, ImageFilter
                img = Image.open(path).convert("RGB")
                gray = img.convert("L")
                blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
                # Variance of Laplacian as sharpness proxy
                import statistics
                diffs = [abs(p1 - p2) for p1, p2 in zip(list(gray.getdata()), list(blurred.getdata()))]
                sharpness = min(100, statistics.mean(diffs) * 4)
                stat = ImageStat.Stat(img)
                mean_brightness = sum(stat.mean) / 3
                brightness = 100 - min(100, abs(mean_brightness - 128) * 0.8)
                overall = round(sharpness * 0.6 + brightness * 0.4, 2)
                out.append({
                    "file_path": path,
                    "sharpness": round(sharpness, 2),
                    "brightness": round(brightness, 2),
                    "overall": overall,
                })
                continue
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        h = int(_hash_md5(path)[:8], 16)
        out.append({"file_path": path, "overall": 50 + (h % 50), "mode": "mock"})
    return out[0] if not isinstance(data, list) else out
