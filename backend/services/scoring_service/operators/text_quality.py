"""text_quality — 文本质量评分算子 (长度 + 句法结构).

op_id: score.text_quality
"""
from __future__ import annotations

import re
from typing import Any, Dict

OP_ID = "score.text_quality"
NAME = "文本质量"
CATEGORY = "text"
DESCRIPTION = "文本流畅度/可读性评分 (0-100)"
PARAMS: list = []


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        text = str(x)
        if not text:
            out.append({"text": text, "text_quality": 0.0})
            continue
        words = re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", text)
        sentences = [s for s in re.split(r"[.!?。！？]+", text) if s.strip()]
        avg_sentence_len = len(words) / max(1, len(sentences))
        length_score = min(50, len(words) * 0.5)
        structure_score = min(30, len(sentences) * 5)
        length_penalty = max(0, (avg_sentence_len - 40) * 0.5)
        overall = round(length_score + structure_score - length_penalty, 2)
        out.append({
            "text": text[:120],
            "words": len(words),
            "sentences": len(sentences),
            "avg_sentence_len": round(avg_sentence_len, 2),
            "text_quality": max(0.0, overall),
        })
    return out[0] if not isinstance(data, list) else out
