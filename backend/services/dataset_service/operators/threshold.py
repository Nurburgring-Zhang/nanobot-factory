"""threshold — 阈值筛选算子 (硬阈值).

op_id: filter.threshold
"""
from __future__ import annotations

from typing import Any, Dict

OP_ID = "filter.threshold"
NAME = "阈值筛选"
CATEGORY = "rank"
DESCRIPTION = "按硬阈值保留/丢弃样本 (score >= min and <= max)"
PARAMS: list = [
    {"name": "min", "type": "float", "default": 0.0, "required": False},
    {"name": "max", "type": "float", "default": 1.0, "required": False},
    {"name": "score_field", "type": "str", "default": "score", "required": False},
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
    lo = float(params.get("min", 0.0))
    hi = float(params.get("max", 1.0))
    field = str(params.get("score_field", "score"))
    items = list(data) if isinstance(data, list) else [data]
    kept = []
    dropped = []
    for x in items:
        s = _primary_score(x, field)
        if lo <= s <= hi:
            kept.append(x)
        else:
            dropped.append(x)
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "min": lo,
        "max": hi,
        "score_field": field,
    }
