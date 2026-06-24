"""balance_filter — 类别平衡筛选算子.

op_id: filter.balance
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict

OP_ID = "filter.balance"
NAME = "类别平衡"
CATEGORY = "balance"
DESCRIPTION = "按类别下采样/上采样到目标分布"
PARAMS: list = [
    {"name": "label_field", "type": "str", "default": "label", "required": False},
    {"name": "target_per_class", "type": "int", "default": 0, "required": False,
     "description": "0 → use majority class size"},
    {"name": "mode", "type": "str", "default": "undersample", "required": False,
     "description": "undersample | oversample"},
    {"name": "seed", "type": "int", "default": 42, "required": False},
]


def _label_of(item: Any, field: str) -> str:
    if isinstance(item, dict):
        return str(item.get(field, "unknown"))
    return "unknown"


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    label_field = str(params.get("label_field", "label"))
    target = int(params.get("target_per_class", 0))
    mode = str(params.get("mode", "undersample")).lower()
    seed = int(params.get("seed", 42))
    rng = random.Random(seed)
    items = list(data) if isinstance(data, list) else [data]
    by_label: Dict[str, list] = {}
    for x in items:
        lbl = _label_of(x, label_field)
        by_label.setdefault(lbl, []).append(x)

    if target <= 0:
        # Use majority size
        target = max(len(v) for v in by_label.values()) if by_label else 0

    kept: list = []
    per_class_counts: Dict[str, int] = {}
    for lbl, lst in by_label.items():
        if mode == "oversample":
            # Sample with replacement up to target
            if len(lst) >= target:
                chosen = lst[:target]
            else:
                chosen = list(lst) + [rng.choice(lst) for _ in range(target - len(lst))]
        else:
            # Undersample
            n = min(target, len(lst))
            chosen = rng.sample(lst, n)
        kept.extend(chosen)
        per_class_counts[lbl] = len(chosen)

    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(items) - len(kept),
        "per_class_counts": per_class_counts,
        "target_per_class": target,
        "mode": mode,
    }
