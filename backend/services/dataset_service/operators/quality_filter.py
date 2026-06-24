"""quality_filter — 质量筛选算子 (基于 composite 评分).

op_id: filter.quality
"""
from __future__ import annotations

from typing import Any, Dict

OP_ID = "filter.quality"
NAME = "质量筛选"
CATEGORY = "quality"
DESCRIPTION = "按 composite quality 评分 (aesthetic + technical + safety 综合) 筛选"
PARAMS: list = [
    {"name": "min_score", "type": "float", "default": 60.0, "required": False},
    {"name": "weights", "type": "dict", "default": {}, "required": False,
     "description": "weights for sub-scores (aesthetic/technical/safety/etc.)"},
]


_DEFAULT_WEIGHTS = {
    "aesthetic": 0.4,
    "technical": 0.3,
    "safety": 0.2,
    "text_quality": 0.1,
}


def _extract_subscores(item: Any) -> Dict[str, float]:
    """Read sub-scores from item.scores dict (or item itself)."""
    scores: Dict[str, float] = {}
    if isinstance(item, dict):
        s = item.get("scores")
        if isinstance(s, dict):
            for k, v in s.items():
                if isinstance(v, (int, float)):
                    scores[k] = float(v)
        # Also support flat keys
        for k, v in item.items():
            if isinstance(v, (int, float)) and k in _DEFAULT_WEIGHTS:
                scores.setdefault(k, float(v))
    return scores


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    min_score = float(params.get("min_score", 60.0))
    weights = dict(_DEFAULT_WEIGHTS)
    user_w = params.get("weights") or {}
    if isinstance(user_w, dict):
        for k, v in user_w.items():
            if isinstance(v, (int, float)):
                weights[k] = float(v)
    items = list(data) if isinstance(data, list) else [data]
    kept = []
    dropped = []
    composite_list = []
    for x in items:
        sub = _extract_subscores(x)
        if not sub:
            # No scores → drop with reason
            dropped.append(x)
            composite_list.append(0.0)
            continue
        total = 0.0
        wsum = 0.0
        for k, w in weights.items():
            if k in sub:
                total += sub[k] * w
                wsum += w
        composite = (total / wsum) if wsum else 0.0
        composite_list.append(composite)
        if composite >= min_score:
            kept.append(x)
        else:
            dropped.append(x)
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "min_score": min_score,
        "weights": weights,
        "composite_scores": [round(c, 2) for c in composite_list],
    }
