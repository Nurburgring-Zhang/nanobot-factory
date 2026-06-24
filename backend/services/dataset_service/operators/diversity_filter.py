"""diversity_filter — 多样性筛选算子 (基于聚类贪心).

op_id: filter.diversity
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

OP_ID = "filter.diversity"
NAME = "多样性筛选"
CATEGORY = "diversity"
DESCRIPTION = "基于 n-gram 多样性贪心筛选 (避免重复/近重复)"
PARAMS: list = [
    {"name": "k", "type": "int", "default": 100, "required": True},
    {"name": "ngram", "type": "int", "default": 3, "required": False},
    {"name": "text_field", "type": "str", "default": "text", "required": False},
]


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _tokens(s: str) -> List[str]:
    return re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower())


def _ngrams(tokens: List[str], n: int) -> set:
    if len(tokens) < n:
        return set(tokens)
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    k = int(params.get("k", 100))
    n = int(params.get("ngram", 3))
    text_field = str(params.get("text_field", "text"))
    items = list(data) if isinstance(data, list) else [data]

    # Pre-compute n-gram sets
    grams_list = []
    for x in items:
        if isinstance(x, dict):
            text = str(x.get(text_field, ""))
        else:
            text = str(x)
        grams_list.append(_ngrams(_tokens(text), n))

    # Greedy: pick item with highest novelty vs already-selected set
    selected: List[int] = []
    selected_union: set = set()
    novelty_history: List[float] = []
    for i, g in enumerate(grams_list):
        if len(selected) >= k:
            break
        if not selected_union:
            sim = 0.0
        else:
            sim = _jaccard(g, selected_union)
        novelty = 1.0 - sim
        novelty_history.append(round(novelty, 4))
        # Always include first; thereafter only if reasonably novel
        if not selected or novelty > 0.05:
            selected.append(i)
            selected_union |= g

    kept = [items[i] for i in selected]
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(items) - len(kept),
        "ngram": n,
        "novelty_history": novelty_history[:50],
    }
