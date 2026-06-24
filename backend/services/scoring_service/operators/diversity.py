"""diversity — 多样性评分算子 (unique token ratio + entropy).

op_id: score.diversity
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict

OP_ID = "score.diversity"
NAME = "多样性"
CATEGORY = "dataset"
DESCRIPTION = "数据集多样性评分 (unique token ratio + Shannon entropy, 0-100)"
PARAMS: list = []


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    # Operates on a list of items
    if not isinstance(data, list):
        data = [data]
    if not data:
        return {"diversity": 0.0, "unique_ratio": 0.0, "total_tokens": 0, "unique_tokens": 0}
    tokens = []
    for x in data:
        tokens.extend(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", str(x).lower()))
    if not tokens:
        return {"diversity": 0.0, "unique_ratio": 0.0}
    unique = set(tokens)
    counts = Counter(tokens)
    total = len(tokens)
    # Shannon entropy over token distribution
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    unique_ratio = len(unique) / total
    # Diversity score: weighted unique_ratio (60%) + normalized entropy (40%)
    norm_entropy = min(1.0, entropy / math.log2(len(unique))) if len(unique) > 1 else 0
    diversity = round((unique_ratio * 0.6 + norm_entropy * 0.4) * 100, 2)
    return {
        "diversity": diversity,
        "unique_ratio": round(unique_ratio, 4),
        "entropy": round(entropy, 3),
        "total_tokens": total,
        "unique_tokens": len(unique),
    }
