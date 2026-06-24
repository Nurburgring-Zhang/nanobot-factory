"""difficulty — 难度评分算子 (用于 RLHF 训练数据筛选).

op_id: score.difficulty
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

OP_ID = "score.difficulty"
NAME = "难度"
CATEGORY = "text"
DESCRIPTION = "任务难度评分 (token 复杂度 + 不确定度, 0-100, 用于 RLHF)"
PARAMS: list = []


def _tokens(s: str) -> list:
    return re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower())


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        text = str(x)
        prompt = text
        if isinstance(x, dict):
            prompt = str(x.get("prompt", "") or x.get("input", text))
        tokens = _tokens(prompt)
        n = len(tokens)
        # Lexical diversity
        unique_ratio = len(set(tokens)) / n if n else 0.0
        # Avg word length
        avg_len = sum(len(t) for t in tokens) / n if n else 0.0
        # Numeric / symbol density (harder problems)
        numeric_count = len(re.findall(r"\d+", prompt))
        sym_count = len(re.findall(r"[<>=+\-*/^%]", prompt))
        special = numeric_count + sym_count
        # Composite difficulty 0-1
        length_score = min(1.0, n / 200.0)
        diversity_score = min(1.0, unique_ratio)
        complexity_score = min(1.0, avg_len / 8.0)
        structure_score = min(1.0, special / 20.0)
        composite = (length_score * 0.4 + diversity_score * 0.2
                     + complexity_score * 0.2 + structure_score * 0.2)
        h = int(_hash_md5("diff:" + prompt)[:8], 16)
        noise = ((h % 30) - 15) / 200.0  # -0.075 to +0.075
        score = min(100.0, max(0.0, (composite + noise) * 100))
        out.append({
            "text": prompt[:120],
            "tokens": n,
            "unique_ratio": round(unique_ratio, 3),
            "avg_token_len": round(avg_len, 2),
            "numeric_count": numeric_count,
            "symbol_count": sym_count,
            "difficulty": round(score, 2),
        })
    return out[0] if not isinstance(data, list) else out
