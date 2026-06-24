"""color_harmony — 色彩和谐评分算子 (色相分布熵 + 主色比例).

op_id: score.color_harmony
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.color_harmony"
NAME = "色彩和谐"
CATEGORY = "image"
DESCRIPTION = "色彩和谐评分 (色相分布 + 主色平衡, 0-100)"
PARAMS: list = []


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _rgb_to_hue(r: int, g: int, b: int) -> float:
    import colorsys
    h_, s_, v_ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h_ * 360.0


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        path = x if isinstance(x, str) else (x.get("path", "") if isinstance(x, dict) else str(x))
        if HAS_PILLOW:
            try:
                from PIL import Image
                img = Image.open(path).convert("RGB").resize((64, 64))
                hues = []
                for r, g, b in img.getdata():
                    hues.append(_rgb_to_hue(r, g, b))
                # Bucket hues into 12 bins (30 deg each)
                bins = [0] * 12
                for h_ in hues:
                    bins[int(h_ / 30) % 12] += 1
                total = sum(bins)
                import math
                # Entropy — higher = more colorful
                entropy = -sum((b / total) * math.log2(b / total) for b in bins if b > 0)
                # Normalize: max possible = log2(12) ~ 3.585
                harmony = min(100, (entropy / 3.585) * 100)
                # Bonus for complementary pairs (180 deg apart) presence
                comp_bonus = 0
                for i in range(6):
                    if bins[i] > 0 and bins[i + 6] > 0:
                        comp_bonus += 5
                harmony = min(100, harmony + comp_bonus)
                out.append({
                    "file_path": path,
                    "entropy": round(entropy, 3),
                    "hue_distribution": bins,
                    "color_harmony": round(harmony, 2),
                })
                continue
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        h_ = int(_hash_md5(path)[:8], 16)
        out.append({"file_path": path, "color_harmony": 50 + (h_ % 50), "mode": "mock"})
    return out[0] if not isinstance(data, list) else out
