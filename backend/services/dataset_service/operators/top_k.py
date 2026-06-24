"""top_k — top-K 筛选算子 (按 score 字段保留前 K 个).

op_id: filter.top_k
"""
from __future__ import annotations

from typing import Any, Dict, List

OP_ID = "filter.top_k"
NAME = "Top-K 筛选"
CATEGORY = "rank"
DESCRIPTION = "按指定 score 字段保留分数最高的 K 项"
PARAMS: list = [
    {"name": "k", "type": "int", "default": 100, "required": True},
    {"name": "score_field", "type": "str", "default": "score", "required": False},
    {"name": "descending", "type": "bool", "default": True, "required": False},
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
    """Filter top-K from a list of items.

    data: list of dicts (each must have score_field) or list of numbers
    params: { k, score_field, descending }
    """
    k = int(params.get("k", 100))
    field = str(params.get("score_field", "score"))
    descending = bool(params.get("descending", True))
    items = list(data) if isinstance(data, list) else [data]
    items.sort(key=lambda x: _primary_score(x, field), reverse=descending)
    kept = items[: max(0, k)]
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": max(0, len(items) - len(kept)),
        "params": {"k": k, "score_field": field, "descending": descending},
    }
