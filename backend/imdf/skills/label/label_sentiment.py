"""label_sentiment — sentiment analysis.

Performs sentiment analysis on text and returns per-sentence and overall
polarity in [−1, 1] plus a label (``positive`` / ``neutral`` / ``negative``).

Inputs:
    text:       str  — input text
    granularity:"sentence"|"paragraph"|"document"
    lang:       str  — "auto"|"en"|"zh"

Outputs:
    label:      str
    score:      float
    sentences:  list — [{text, label, score}]
    lang:       str
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


_VALID_GRAINS = {"sentence", "paragraph", "document"}

_POS_WORDS_EN = {"good", "great", "excellent", "love", "best", "wonderful", "amazing", "happy", "perfect", "nice"}
_NEG_WORDS_EN = {"bad", "terrible", "awful", "hate", "worst", "horrible", "sad", "poor", "disappointing", "wrong"}
_POS_WORDS_ZH = {"好", "棒", "喜欢", "完美", "满意", "优秀", "开心", "高兴", "推荐"}
_NEG_WORDS_ZH = {"差", "糟糕", "讨厌", "失望", "不好", "后悔", "烂", "难用"}


def _classify(score: float) -> str:
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


class SentimentInput(BaseModel):
    text: str = Field(..., min_length=1)
    granularity: str = Field(default="sentence")
    lang: str = Field(default="auto")

    @field_validator("granularity")
    @classmethod
    def _g(cls, v: str) -> str:
        v = (v or "sentence").lower().strip()
        if v not in _VALID_GRAINS:
            raise ValueError(f"granularity must be one of {sorted(_VALID_GRAINS)}")
        return v


async def label_sentiment(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = SentimentInput.model_validate(input.params or {})
        require_non_empty(payload.text, "text")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    detected_lang = payload.lang
    if detected_lang == "auto":
        detected_lang = "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in payload.text) else "en"

    live = None
    if NETWORK_OK:
        live = await post_json(
            "https://api.sentiment.example/analyze",
            payload.model_dump(), timeout=4.0,
        )

    if live and isinstance(live, dict) and live.get("label"):
        return build_output(
            success=True,
            result={
                "label": str(live["label"]),
                "score": clamp(float(live.get("score", 0.0)), -1.0, 1.0),
                "sentences": list(live.get("sentences", [])),
                "lang": detected_lang,
                "granularity": payload.granularity,
                "model": "remote-sentiment",
                "timestamp": now_iso(),
            },
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — lexicon + sentence split.
    sentences = _split_units(payload.text, payload.granularity, detected_lang)
    scored: List[Dict[str, Any]] = []
    total = 0.0
    for s in sentences:
        sc = _score_sentence(s, detected_lang)
        scored.append({"text": s, "label": _classify(sc), "score": round(sc, 4)})
        total += sc
    overall = total / max(len(scored), 1)
    return build_output(
        success=True,
        result={
            "label": _classify(overall),
            "score": round(overall, 4),
            "sentences": scored,
            "lang": detected_lang,
            "granularity": payload.granularity,
            "model": "lexicon-mock",
            "timestamp": now_iso(),
        },
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _split_units(text: str, granularity: str, lang: str) -> List[str]:
    if granularity == "document":
        return [text.strip()] if text.strip() else []
    if granularity == "paragraph":
        return [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    # sentence
    if lang == "zh":
        parts = re.split(r"(?<=[。！？!?\.])", text)
    else:
        parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _score_sentence(sentence: str, lang: str) -> float:
    pos = _POS_WORDS_ZH if lang == "zh" else _POS_WORDS_EN
    neg = _NEG_WORDS_ZH if lang == "zh" else _NEG_WORDS_EN
    tokens = list(sentence) if lang == "zh" else sentence.lower().split()
    p = sum(1 for t in tokens if t in pos)
    n = sum(1 for t in tokens if t in neg)
    total = p + n
    if total == 0:
        return 0.0
    return clamp((p - n) / max(total, 1), -1.0, 1.0)


__all__ = ["label_sentiment", "SentimentInput"]