"""creativity — 创造性评分算子 (n-gram 新颖度 + 修辞密度).

op_id: score.creativity
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Dict

OP_ID = "score.creativity"
NAME = "创造性"
CATEGORY = "text"
DESCRIPTION = "创造性评分 (n-gram novelty + metaphor/rhetoric density, 0-100)"
PARAMS: list = [
    {"name": "background", "type": "list", "default": [], "required": False,
     "description": "Optional list of historical texts to compute novelty against"},
]


_RHETORIC = {"比喻", "好像", "仿佛", "如同", "像", "宛如", "metaphor", "like", "as if", "seems"}

# Stopwords (very small set — placeholder)
_STOP = {"的", "了", "是", "在", "和", "the", "a", "an", "is", "are", "was", "were", "of", "to", "in"}


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _tokens(s: str) -> list:
    return re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower())


def _bigrams(tokens: list) -> Counter:
    return Counter(zip(tokens, tokens[1:]))


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    background = params.get("background", []) or []
    items = data if isinstance(data, list) else [data]
    # Build background bigram set for novelty
    bg_bigrams: Counter = Counter()
    for bg in background:
        bg_bigrams.update(_bigrams(_tokens(str(bg))))
    out = []
    for x in items:
        text = str(x)
        tokens = _tokens(text)
        if len(tokens) < 2:
            out.append({"text": text[:80], "creativity": 0.0, "reason": "too_short"})
            continue
        bgs = _bigrams(tokens)
        # Novelty: ratio of bigrams not seen in background
        if bg_bigrams:
            novel = sum(1 for bg, c in bgs.items() if bg not in bg_bigrams)
            novelty_ratio = novel / len(bgs)
        else:
            # Self-novelty: rare-bigram density
            rare = sum(1 for bg, c in bgs.items() if c == 1)
            novelty_ratio = rare / len(bgs)
        # Rhetoric density
        lo = text.lower()
        rhet_hits = sum(1 for w in _RHETORIC if w in lo or w in text)
        rhet_density = rhet_hits / max(1, len(tokens))
        # Lexical richness (unique / total, excluding stopwords)
        non_stop = [t for t in tokens if t not in _STOP]
        richness = len(set(non_stop)) / len(non_stop) if non_stop else 0
        h = int(_hash_md5("cre:" + text)[:8], 16)
        noise = ((h % 30) - 15) / 300.0
        score = min(100.0, max(0.0,
            (novelty_ratio * 0.5 + min(1, rhet_density * 20) * 0.2 + richness * 0.3 + noise) * 100))
        out.append({
            "text": text[:120],
            "novelty_ratio": round(novelty_ratio, 3),
            "rhetoric_density": round(rhet_density, 4),
            "richness": round(richness, 3),
            "creativity": round(score, 2),
        })
    return out[0] if not isinstance(data, list) else out
