"""safety — 安全性评分算子 (NSFW + 敏感词 + PII 风险).

op_id: score.safety
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

OP_ID = "score.safety"
NAME = "安全性"
CATEGORY = "safety"
DESCRIPTION = "内容安全评分 (NSFW + 敏感词 + PII, 0-100, 越高越安全)"
PARAMS: list = [
    {"name": "nsfw_threshold", "type": "float", "default": 0.7, "required": False},
    {"name": "pii_threshold", "type": "float", "default": 0.5, "required": False},
]


# Minimal PII regex (email, phone, ID-like)
_PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"\b1[3-9]\d{9}\b"),            # CN mobile
    re.compile(r"\b\d{17}[\dXx]\b"),           # CN ID
    re.compile(r"\b\d{16,19}\b"),              # credit card-like
]

# Lightweight sensitive-word list (placeholder; production should use a lexicon)
_SENSITIVE = {"badword", "hate", "暴力", "色情", "毒品", "weapon", "kill"}


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    nsfw_threshold = float(params.get("nsfw_threshold", 0.7))
    pii_threshold = float(params.get("pii_threshold", 0.5))
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        text = str(x)
        # PII risk: count matches / length
        pii_hits = sum(len(p.findall(text)) for p in _PII_PATTERNS)
        pii_risk = min(1.0, pii_hits / 5.0) if text else 0.0
        # Sensitive-word risk
        lo = text.lower()
        sens_hits = sum(1 for w in _SENSITIVE if w in lo or w in text)
        sens_risk = min(1.0, sens_hits / 5.0)
        # NSFW: deterministic pseudo from text hash (mock classifier)
        h = int(_hash_md5("nsfw:" + text)[:8], 16)
        nsfw = (h % 100) / 1000.0  # 0-0.1
        # Composite safety: start at 100, subtract weighted risks
        score = 100.0
        score -= nsfw * 200 if nsfw > nsfw_threshold else 0
        score -= pii_risk * (50 if pii_risk > pii_threshold else 15)
        score -= sens_risk * (60 if sens_hits > 2 else 20)
        score = max(0.0, min(100.0, score))
        out.append({
            "text": text[:120],
            "nsfw_probability": round(nsfw, 4),
            "pii_risk": round(pii_risk, 4),
            "pii_hits": pii_hits,
            "sensitive_hits": sens_hits,
            "safety": round(score, 2),
        })
    return out[0] if not isinstance(data, list) else out
