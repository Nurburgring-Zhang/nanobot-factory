"""aesthetic — 美学评分算子 (复用 imdf.engines.aesthetic_scorer).

op_id: score.aesthetic
输入: image_path (str) 或 list[image_path]
输出: { overall, clip_iqa, musiq, grade }
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from imdf.engines.aesthetic_scorer import get_aesthetic_scorer, HAS_PILLOW
    _SCORER = get_aesthetic_scorer()
except Exception:  # noqa: BLE001
    _SCORER = None
    HAS_PILLOW = False

OP_ID = "score.aesthetic"
NAME = "美学评分"
CATEGORY = "image"
DESCRIPTION = "图像美学评分 (CLIP-IQA + MUSIQ, 0-100)"
PARAMS: list = []


def _hash_md5(s: str) -> str:
    import hashlib
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Run aesthetic scoring on image path(s).

    Accepts:
      data: str | list[str]
      params: ignored (no params)
    """
    items = data if isinstance(data, list) else [data]
    results = []
    for x in items:
        path = x if isinstance(x, str) else (x.get("path", "") if isinstance(x, dict) else str(x))
        if _SCORER is not None and HAS_PILLOW:
            try:
                r = _SCORER.score_image(path)
                results.append({
                    "file_path": r.file_path,
                    "overall": (r.clip_iqa.overall + r.musiq.overall) / 2,
                    "clip_iqa": r.clip_iqa.to_dict(),
                    "musiq": r.musiq.to_dict(),
                    "grade": getattr(r, "grade", None),
                })
                continue
            except Exception as e:  # noqa: BLE001
                results.append({"file_path": path, "error": str(e)})
                continue
        # Mock fallback
        h = int(_hash_md5(path)[:8], 16)
        results.append({"file_path": path, "overall": 60 + (h % 40), "mode": "mock"})
    return results[0] if not isinstance(data, list) else results
