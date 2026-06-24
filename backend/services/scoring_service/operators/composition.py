"""composition — 构图评分算子 (三分法 + 主体居中度启发式).

op_id: score.composition
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import HAS_PILLOW
except Exception:  # noqa: BLE001
    HAS_PILLOW = False

OP_ID = "score.composition"
NAME = "构图评分"
CATEGORY = "image"
DESCRIPTION = "图像构图评分 (三分法 + 中心偏移, 0-100)"
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
                from PIL import Image
                img = Image.open(path).convert("L")
                w, h = img.size
                if w == 0 or h == 0:
                    raise ValueError("zero size")
                # Find dominant subject via darkest 10% mean position
                pixels = list(img.getdata())
                step = max(1, len(pixels) // 5000)
                sampled = pixels[::step]
                # Threshold at 10th percentile
                sorted_p = sorted(sampled)
                threshold = sorted_p[len(sorted_p) // 10] if sorted_p else 0
                ys, xs = [], []
                idx = 0
                for y in range(0, h, max(1, h // 100)):
                    for xx in range(0, w, max(1, w // 100)):
                        pi = y * w + xx
                        if pi < len(pixels) and pixels[pi] <= threshold:
                            xs.append(xx)
                            ys.append(y)
                if xs and ys:
                    cx = sum(xs) / len(xs)
                    cy = sum(ys) / len(ys)
                else:
                    cx, cy = w / 2, h / 2
                # Distance from rule-of-thirds intersection points (0-1 range)
                thirds = [(w / 3, h / 3), (2 * w / 3, h / 3), (w / 3, 2 * h / 3), (2 * w / 3, 2 * h / 3)]
                d = min(((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5 for tx, ty in thirds)
                diag = (w * w + h * h) ** 0.5
                norm = d / diag if diag else 1
                # Closer to thirds intersection (norm ~ 0.2-0.4) → higher score
                thirds_score = max(0.0, 100 - abs(norm - 0.3) * 250)
                # Center-offset bonus
                center_d = ((cx - w / 2) ** 2 + (cy - h / 2) ** 2) ** 0.5 / diag
                offset_score = 60 + min(40, center_d * 100)
                overall = round(thirds_score * 0.6 + offset_score * 0.4, 2)
                out.append({
                    "file_path": path,
                    "size": [w, h],
                    "subject_center": [round(cx, 1), round(cy, 1)],
                    "thirds_score": round(thirds_score, 2),
                    "offset_score": round(offset_score, 2),
                    "composition": overall,
                })
                continue
            except Exception as e:  # noqa: BLE001
                out.append({"file_path": path, "error": str(e)})
                continue
        h_ = int(_hash_md5(path)[:8], 16)
        out.append({"file_path": path, "composition": 50 + (h_ % 50), "mode": "mock"})
    return out[0] if not isinstance(data, list) else out
