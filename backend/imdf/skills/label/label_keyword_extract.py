"""label_keyword_extract — keyword / keyphrase extraction.

Extracts ranked keywords and keyphrases from text using TF-IDF-style offline
heuristics. Supports both English and Chinese input.

Inputs:
    text:        str
    top_k:       int — number of keywords (default 10)
    min_length:  int — minimum token length (default 2)
    lang:        str — "auto"|"en"|"zh"

Outputs:
    keywords:    list — [{keyword, score}]
    keyphrases:  list — [{phrase, score}]
    count:       int
"""
from __future__ import annotations

import re
import time
from collections import Counter
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


_STOPWORDS_EN = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "in", "on", "at",
    "of", "for", "to", "and", "or", "but", "if", "then", "this", "that", "these", "those",
    "it", "its", "with", "as", "by", "from", "have", "has", "had", "do", "does", "did",
    "i", "you", "he", "she", "we", "they", "them", "their", "our", "your",
}
_STOPWORDS_ZH = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "上", "也",
                 "很", "到", "说", "要", "去", "会", "着", "没有", "看", "好", "自己", "这", "那"}


class KeywordExtractInput(BaseModel):
    text: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    min_length: int = Field(default=2, ge=1, le=10)
    lang: str = Field(default="auto")

    @field_validator("top_k")
    @classmethod
    def _k(cls, v: int) -> int:
        return max(1, min(50, int(v)))


async def label_keyword_extract(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = KeywordExtractInput.model_validate(input.params or {})
        require_non_empty(payload.text, "text")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    detected_lang = payload.lang
    if detected_lang == "auto":
        detected_lang = "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in payload.text) else "en"

    live = None
    if NETWORK_OK:
        live = await post_json(
            "https://api.kw.example/extract",
            payload.model_dump(), timeout=4.0,
        )

    if live and isinstance(live, dict) and live.get("keywords"):
        return build_output(
            success=True,
            result={
                "keywords": list(live.get("keywords", []))[: payload.top_k],
                "keyphrases": list(live.get("keyphrases", []))[: payload.top_k],
                "count": len(live.get("keywords", [])),
                "lang": detected_lang, "model": "remote-kw",
                "timestamp": now_iso(),
            },
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    keywords, keyphrases = _extract_offline(payload.text, detected_lang, payload.top_k, payload.min_length)
    return build_output(
        success=True,
        result={
            "keywords": keywords, "keyphrases": keyphrases,
            "count": len(keywords), "lang": detected_lang, "model": "tfidf-mock",
            "timestamp": now_iso(),
        },
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _tokenize(text: str, lang: str, min_length: int) -> List[str]:
    if lang == "zh":
        # Chinese - per-char with stopword filtering; bigrams generated later.
        # min_length doesn't apply per-char (always 1); we keep >=1 char CJK only.
        return [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    text_l = text.lower()
    tokens = re.findall(r"[a-z][a-z\-]+", text_l)
    return [t for t in tokens if len(t) >= min_length]


def _extract_offline(text: str, lang: str, top_k: int, min_length: int):
    stops = _STOPWORDS_ZH if lang == "zh" else _STOPWORDS_EN
    tokens = [t for t in _tokenize(text, lang, min_length) if t not in stops]
    counter = Counter(tokens)
    n = max(sum(counter.values()), 1)
    keywords = [
        {"keyword": k, "score": round(c / n, 4)}
        for k, c in counter.most_common(top_k)
    ]

    # Bigrams for English; bi-character windows for Chinese
    keyphrases = []
    if lang == "zh":
        for i in range(0, len(tokens) - 1):
            keyphrases.append(tokens[i] + tokens[i + 1])
    else:
        for i in range(0, len(tokens) - 1):
            keyphrases.append(f"{tokens[i]} {tokens[i + 1]}")
    phrase_counter = Counter([p for p in keyphrases if p])
    total_p = max(sum(phrase_counter.values()), 1)
    keyphrases_out = [
        {"phrase": p, "score": round(c / total_p, 4)}
        for p, c in phrase_counter.most_common(top_k)
    ]

    return keywords, keyphrases_out


__all__ = ["label_keyword_extract", "KeywordExtractInput"]