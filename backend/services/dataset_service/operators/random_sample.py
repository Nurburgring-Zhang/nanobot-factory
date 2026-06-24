"""random_sample — 随机采样筛选算子.

op_id: filter.random_sample
"""
from __future__ import annotations

import random
from typing import Any, Dict

OP_ID = "filter.random_sample"
NAME = "随机采样"
CATEGORY = "sample"
DESCRIPTION = "按指定比例或数量随机采样"
PARAMS: list = [
    {"name": "n", "type": "int", "default": 0, "required": False,
     "description": "0 → use ratio"},
    {"name": "ratio", "type": "float", "default": 0.1, "required": False,
     "description": "0-1, used when n=0"},
    {"name": "seed", "type": "int", "default": 42, "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    n = int(params.get("n", 0))
    ratio = float(params.get("ratio", 0.1))
    seed = int(params.get("seed", 42))
    rng = random.Random(seed)
    items = list(data) if isinstance(data, list) else [data]
    if n <= 0:
        n = max(1, int(round(len(items) * ratio)))
    n = min(n, len(items))
    chosen = rng.sample(items, n) if n < len(items) else list(items)
    return {
        "kept": chosen,
        "kept_count": len(chosen),
        "dropped_count": len(items) - len(chosen),
        "n": n,
        "ratio": ratio,
        "seed": seed,
    }
