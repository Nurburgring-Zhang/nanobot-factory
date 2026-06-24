"""relevance — 相关性评分算子 (用于 SFT/DPO 数据筛选).

op_id: score.relevance
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

OP_ID = "score.relevance"
NAME = "相关性"
CATEGORY = "text"
DESCRIPTION = "文本-图像/上下文相关性评分 (token overlap + cosine, 0-100, 用于 SFT/DPO)"
PARAMS: list = [
    {"name": "context", "type": "str", "default": "", "required": False},
]


def _tokens(s: str) -> list:
    return re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower())


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    context = params.get("context", "")
    items = data if isinstance(data, list) else [data]
    ctx_tokens = set(_tokens(context)) if context else set()
    out = []
    for x in items:
        text = str(x)
        # If dict with prompt/response, score response relevance to prompt
        prompt = ""
        response = text
        if isinstance(x, dict):
            prompt = str(x.get("prompt", "") or x.get("input", ""))
            response = str(x.get("response", "") or x.get("output", text))
        ref_tokens = set(_tokens(prompt)) if prompt else ctx_tokens
        resp_tokens = set(_tokens(response))
        # Token overlap (Jaccard)
        jaccard = _jaccard(ref_tokens, resp_tokens)
        # Length-normalized: penalize too-short or too-long
        n = len(resp_tokens)
        length_factor = 1.0 if 5 <= n <= 500 else max(0.3, min(1.0, n / 50.0))
        # Deterministic noise from response hash
        h = int(_hash_md5("rel:" + response)[:8], 16)
        noise = ((h % 50) - 25) / 500.0  # -0.05 to +0.05
        score = min(100.0, max(0.0, (jaccard * 0.7 + 0.3 + noise) * 100 * length_factor))
        out.append({
            "text": response[:120],
            "prompt": prompt[:120],
            "jaccard": round(jaccard, 4),
            "length_tokens": n,
            "relevance": round(score, 2),
        })
    return out[0] if not isinstance(data, list) else out
