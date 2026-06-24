"""rule_based — 规则筛选算子 (DSL: 简单表达式 evaluator).

op_id: filter.rule_based
"""
from __future__ import annotations

from typing import Any, Dict, List

OP_ID = "filter.rule_based"
NAME = "规则筛选"
CATEGORY = "rule"
DESCRIPTION = "按规则表达式筛选 (DSL: field op value, 多条 AND 组合)"
PARAMS: list = [
    {"name": "rules", "type": "list", "default": [], "required": True,
     "description": "List of {field, op, value}. ops: eq/ne/gt/gte/lt/lte/contains/in"},
]


_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "contains": lambda a, b: b in (a if isinstance(a, (str, list, dict)) else str(a)),
    "in": lambda a, b: a in b,
}


def _value_of(item: Any, field: str) -> Any:
    """Read field via dot-path: e.g. scores.aesthetic."""
    if not isinstance(item, dict):
        return None
    cur: Any = item
    for part in field.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _matches(item: Any, rule: Dict[str, Any]) -> bool:
    field = str(rule.get("field", ""))
    op = str(rule.get("op", "eq"))
    value = rule.get("value")
    if op not in _OPS:
        return False
    v = _value_of(item, field)
    try:
        return bool(_OPS[op](v, value))
    except Exception:
        return False


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    rules = params.get("rules") or []
    if not isinstance(rules, list) or not rules:
        return {
            "kept": list(data) if isinstance(data, list) else [data],
            "kept_count": 0, "dropped_count": 0,
            "rules_applied": [], "error": "no_rules",
        }
    # Validate op names
    for r in rules:
        if not isinstance(r, dict):
            continue
        op = str(r.get("op", "eq"))
        if op not in _OPS:
            return {
                "kept": [], "kept_count": 0, "dropped_count": 0,
                "rules_applied": [], "error": f"unknown_op: {op}",
            }
    items = list(data) if isinstance(data, list) else [data]
    kept = []
    dropped = []
    for x in items:
        if all(_matches(x, r) for r in rules if isinstance(r, dict)):
            kept.append(x)
        else:
            dropped.append(x)
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "rules_applied": [
            {"field": str(r.get("field")), "op": str(r.get("op")), "value": r.get("value")}
            for r in rules if isinstance(r, dict)
        ],
    }
