"""percentile — 百分位筛选算子.

op_id: filter.percentile
"""
from __future__ import annotations

import statistics
from typing import Any, Dict

OP_ID = "filter.percentile"
NAME = "百分位筛选"
CATEGORY = "rank"
DESCRIPTION = "保留 score 在指定百分位以上的项 (默认 P50)"
PARAMS: list = [
    {"name": "percentile", "type": "float", "default": 50.0, "required": False},
    {"name": "score_field", "type": "str", "default": "score", "required": False},
    {"name": "mode", "type": "str", "default": "above", "required": False,
     "description": "above | below"},
]


def _primary_score(item: Any, field: str) -> float:
    if isinstance(item, dict):
        v = item.get(field)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            for k in ("overall", "score", "value", "mean"):
                if isinstance(v.get(k), (int, float)):
                    return float(v[k])
    if isinstance(item, (int, float)):
        return float(item)
    return 0.0


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    pct = float(params.get("percentile", 50.0))
    field = str(params.get("score_field", "score"))
    mode = str(params.get("mode", "above")).lower()
    items = list(data) if isinstance(data, list) else [data]
    scores = [_primary_score(x, field) for x in items]
    if not scores:
        return {"kept": [], "kept_count": 0, "threshold": 0.0, "percentile": pct}
    # Sort and pick threshold by rank
    sorted_scores = sorted(scores)
    rank = max(0, min(len(sorted_scores) - 1,
                      int(round(pct / 100.0 * (len(sorted_scores) - 1)))))
    threshold = sorted_scores[rank]
    if mode == "below":
        kept = [x for x, s in zip(items, scores) if s <= threshold]
    else:
        kept = [x for x, s in zip(items, scores) if s >= threshold]
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(items) - len(kept),
        "threshold": round(threshold, 4),
        "percentile": pct,
        "mode": mode,
        "score_stats": {
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
            "mean": round(statistics.mean(scores), 4),
            "median": round(statistics.median(scores), 4),
        },
    }
