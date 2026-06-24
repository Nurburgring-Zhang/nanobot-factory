"""preference — 偏好评分算子 (用于 DPO 训练数据).

op_id: score.preference
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

OP_ID = "score.preference"
NAME = "偏好"
CATEGORY = "text"
DESCRIPTION = "偏好评分 (chosen vs rejected, 0-100, 用于 DPO)"
PARAMS: list = [
    {"name": "chosen", "type": "str", "default": "", "required": False},
    {"name": "rejected", "type": "str", "default": "", "required": False},
]


def _tokens(s: str) -> set:
    return set(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower()))


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


_POS = {"好", "棒", "优秀", "准确", "清晰", "good", "great", "excellent", "clear", "correct"}
_NEG = {"差", "糟", "错误", "模糊", "bad", "wrong", "unclear", "vague"}


def _quality_signal(text: str) -> float:
    """Heuristic quality 0-1 from pos/neg keyword density + length sweet-spot."""
    lo = text.lower()
    p = sum(1 for w in _POS if w in lo or w in text)
    n = sum(1 for w in _NEG if w in lo or w in text)
    sent = max(1, len(re.split(r"[.!?。！？]+", text)))
    words = len(_tokens(text))
    avg = words / sent
    sweet = 1.0 if 8 <= avg <= 25 else max(0.5, 1 - abs(avg - 16) / 30)
    polarity = (p - n) / max(1, p + n)
    return 0.5 + 0.3 * polarity + 0.2 * (sweet - 0.5)


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    chosen = params.get("chosen", "")
    rejected = params.get("rejected", "")
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        if isinstance(x, dict):
            chosen = chosen or str(x.get("chosen", ""))
            rejected = rejected or str(x.get("rejected", ""))
        if not chosen or not rejected:
            out.append({"chosen": chosen[:80], "rejected": rejected[:80], "preference": 0.0, "error": "missing chosen/rejected"})
            continue
        q_chosen = _quality_signal(chosen)
        q_rejected = _quality_signal(rejected)
        margin = q_chosen - q_rejected  # -1 to 1
        # Deterministic noise from hash of pair
        h = int(_hash_md5(chosen + "||" + rejected)[:8], 16)
        noise = ((h % 50) - 25) / 250.0  # -0.1 to +0.1
        score = min(100.0, max(0.0, 50 + margin * 50 + noise * 10))
        out.append({
            "chosen": chosen[:80],
            "rejected": rejected[:80],
            "q_chosen": round(q_chosen, 3),
            "q_rejected": round(q_rejected, 3),
            "margin": round(margin, 3),
            "preference": round(score, 2),  # >50 = chosen preferred
        })
    return out[0] if not isinstance(data, list) else out
