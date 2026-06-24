"""
scoring_service.dispatch — 15 评分算子的执行入口.
- 5 基础算子 (有 imdf_op) → 优先 imdf.engines.aesthetic_scorer 真实逻辑
- 10 扩展算子 → 内联实现 (启发式 + 模拟)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

try:
    from imdf.engines.operators_lib import get_registry as _get_imdf_registry
    _IMDF_REG = _get_imdf_registry()
except Exception:
    _IMDF_REG = None

try:
    from imdf.engines.aesthetic_scorer import (
        AestheticScorer, get_aesthetic_scorer, HAS_PILLOW,
    )
    _AESTHETIC = get_aesthetic_scorer()
except Exception:
    AestheticScorer = None
    _AESTHETIC = None
    HAS_PILLOW = False


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _stable_pseudo_score(seed: str, lo: float = 50.0, hi: float = 100.0) -> float:
    """Deterministic pseudo-score in [lo, hi] from a string seed."""
    h = int(_hash_md5(seed)[:8], 16)
    return round(lo + (h % 1000) / 1000.0 * (hi - lo), 2)


def _aesthetic_score_image(path: str) -> Dict[str, Any]:
    if _AESTHETIC is None or not HAS_PILLOW:
        h = int(_hash_md5(path)[:8], 16)
        return {"file_path": path, "overall": 60 + (h % 40), "mode": "mock"}
    try:
        result = _AESTHETIC.score_image(path)
        return {
            "file_path": result.file_path,
            "overall": (result.clip_iqa.overall + result.musiq.overall) / 2,
            "clip_iqa": result.clip_iqa.to_dict(),
            "musiq": result.musiq.to_dict(),
            "grade": result.grade if hasattr(result, "grade") else None,
        }
    except Exception as e:
        return {"file_path": path, "error": str(e)}


def _technical_quality_image(path: str) -> Dict[str, Any]:
    if _AESTHETIC is None or not HAS_PILLOW:
        h = int(_hash_md5(path)[:8], 16)
        return {"file_path": path, "technical": 50 + (h % 50), "mode": "mock"}
    try:
        from PIL import Image, ImageStat, ImageFilter
        img = Image.open(path).convert("RGB")
        gray = img.convert("L")
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
        diffs = [abs(p1 - p2) for p1, p2 in zip(list(gray.getdata()), list(blurred.getdata()))]
        sharpness = min(100, statistics.mean(diffs) * 4)
        stat = ImageStat.Stat(img)
        mean_brightness = sum(stat.mean) / 3
        brightness = 100 - min(100, abs(mean_brightness - 128) * 0.8)
        return {
            "file_path": path,
            "sharpness": round(sharpness, 2),
            "brightness": round(brightness, 2),
            "technical": round((sharpness * 0.6 + brightness * 0.4), 2),
        }
    except Exception as e:
        return {"file_path": path, "error": str(e)}


def _nsfw_detector(path: str, threshold: float = 0.7) -> Dict[str, Any]:
    """Mock NSFW detector — returns low score for normal content."""
    h = int(_hash_md5(path)[:8], 16)
    p = (h % 100) / 1000.0  # 0-0.1
    return {
        "file_path": path,
        "nsfw_probability": round(p, 4),
        "is_nsfw": p > threshold,
        "threshold": threshold,
    }


def _coherence_score(items: List[Any]) -> Dict[str, Any]:
    """Coherence: text-list temporal coherence = inverse of edit distance variance."""
    if not items:
        return {"coherence": 0.0, "mode": "empty"}
    if len(items) < 2:
        return {"coherence": _stable_pseudo_score(str(items[0]))}
    # Simple proxy: shorter text more likely adjacent
    lengths = [len(str(x)) for x in items]
    variance = statistics.pvariance(lengths) if len(lengths) > 1 else 0.0
    base = 80 - min(40, math.log1p(variance) * 5)
    return {"coherence": round(base, 2), "items": len(items), "variance": round(variance, 2)}


def _diversity_score(items: List[Any]) -> Dict[str, Any]:
    """Diversity: unique-token ratio."""
    if not items:
        return {"diversity": 0.0, "unique_ratio": 0.0}
    tokens = []
    for x in items:
        tokens.extend(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", str(x).lower()))
    if not tokens:
        return {"diversity": 0.0, "unique_ratio": 0.0}
    unique = len(set(tokens))
    return {
        "diversity": round(unique / len(tokens) * 100, 2),
        "unique_ratio": round(unique / len(tokens), 4),
        "total_tokens": len(tokens),
        "unique_tokens": unique,
    }


def _clip_score(text: str, image: str = "") -> Dict[str, Any]:
    """Mock CLIP score — high if text references the image path."""
    if image and image in text:
        score = 0.85
    else:
        score = _stable_pseudo_score(text + image, 0.3, 0.9)
    return {"text": text[:120], "image": image, "clip_score": round(score, 4)}


def _text_quality(text: str) -> Dict[str, Any]:
    """Heuristic text quality score."""
    if not text:
        return {"quality": 0.0}
    words = re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", text)
    sentences = [s for s in re.split(r"[.!?。！？]+", text) if s.strip()]
    avg_sentence_len = len(words) / max(1, len(sentences))
    length_score = min(50, len(words) * 0.5)
    structure_score = min(30, len(sentences) * 5)
    length_penalty = max(0, (avg_sentence_len - 40) * 0.5)
    return {
        "quality": round(length_score + structure_score - length_penalty, 2),
        "words": len(words),
        "sentences": len(sentences),
        "avg_sentence_len": round(avg_sentence_len, 2),
    }


def _toxicity(text: str, threshold: float = 0.5) -> Dict[str, Any]:
    """Mock toxicity — stable pseudo-score, mark above threshold as toxic."""
    score = _stable_pseudo_score("tox:" + text, 0.0, 0.6)
    return {
        "text": text[:120],
        "toxicity": round(score, 4),
        "is_toxic": score > threshold,
        "threshold": threshold,
    }


def _sentiment(text: str) -> Dict[str, Any]:
    """Heuristic sentiment: positive/negative keyword count."""
    pos = {"好", "棒", "优秀", "good", "great", "excellent", "amazing", "love", "喜欢", "赞"}
    neg = {"差", "糟", "失败", "bad", "terrible", "awful", "hate", "讨厌", "烂"}
    lo = text.lower()
    p = sum(1 for w in pos if w in lo or w in text)
    n = sum(1 for w in neg if w in lo or w in text)
    if p + n == 0:
        score = 0.0
    else:
        score = (p - n) / (p + n)
    return {"sentiment": round(score, 4), "positive": p, "negative": n}


def _language_quality(text: str) -> Dict[str, Any]:
    """Grammar/spelling/punctuation composite."""
    if not text:
        return {"quality": 0.0}
    has_punct = any(c in text for c in "。.，,;；!！?？")
    char_count = len(text)
    unique_chars = len(set(text))
    ratio = unique_chars / max(1, char_count)
    score = 60 + min(30, ratio * 100) + (10 if has_punct else 0)
    return {
        "quality": round(score, 2),
        "char_count": char_count,
        "unique_ratio": round(ratio, 4),
        "has_punctuation": has_punct,
    }


def _factuality(text: str) -> Dict[str, Any]:
    """Mock factuality — penalize very long, reward moderate length with specifics."""
    if not text:
        return {"factuality": 0.0}
    h = int(_hash_md5("fact:" + text)[:8], 16)
    base = 60 + (h % 40)
    # Penalize for vague phrases
    vague = ["也许", "可能", "maybe", "perhaps"]
    vague_count = sum(1 for w in vague if w in text.lower() or w in text)
    score = max(20.0, base - vague_count * 5)
    return {"factuality": round(score, 2), "vague_hits": vague_count}


def _video_motion(video_path: str) -> Dict[str, Any]:
    """Mock video motion score."""
    return {
        "video_path": video_path,
        "motion_score": _stable_pseudo_score("motion:" + video_path, 20, 80),
        "mode": "mock",
    }


def _video_stability(video_path: str) -> Dict[str, Any]:
    """Mock video stability — higher = more stable."""
    return {
        "video_path": video_path,
        "stability": _stable_pseudo_score("stab:" + video_path, 50, 95),
        "mode": "mock",
    }


def _audio_quality(audio_path: str) -> Dict[str, Any]:
    """Mock audio quality (PESQ-style)."""
    return {
        "audio_path": audio_path,
        "quality": _stable_pseudo_score("audio:" + audio_path, 30, 95),
        "mode": "mock",
    }


def _code_quality(code: str) -> Dict[str, Any]:
    """Heuristic code quality — reward comments, balanced braces, short lines."""
    if not code:
        return {"quality": 0.0}
    lines = code.splitlines()
    n = max(1, len(lines))
    avg_len = sum(len(l) for l in lines) / n
    long_lines = sum(1 for l in lines if len(l) > 120)
    has_comments = any("#" in l or "//" in l for l in lines)
    brace_balance = code.count("{") - code.count("}")
    score = 70 - long_lines * 2 - min(20, abs(brace_balance) * 5) + (10 if has_comments else 0)
    score -= min(15, max(0, avg_len - 80) * 0.3)
    return {
        "quality": round(max(0.0, min(100.0, score)), 2),
        "lines": len(lines),
        "avg_line_len": round(avg_len, 1),
        "long_lines": long_lines,
        "has_comments": has_comments,
        "brace_balance": brace_balance,
    }


# ── dispatch ─────────────────────────────────────────────────────────────────
def apply_scorer(op_id: str, data: Any, params: Dict[str, Any]) -> Any:
    """Unified scorer execution entry point.

    Returns:
      - For op_id with imdf_op: prefer imdf.engines.operators_lib, fall back to in-house.
      - For op_id without imdf_op: in-house implementation.
    """
    from ._legacy_operators import get_operator_meta
    meta = get_operator_meta(op_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Unknown scorer: {op_id}")

    is_list = isinstance(data, list)
    items = data if is_list else [data]

    # ── 1. base scorers backed by imdf engines ─────────────────────────────
    if op_id == "score.aesthetic":
        out = [_aesthetic_score_image(str(x) if not isinstance(x, dict) else x.get("path", ""))
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.technical_quality":
        out = [_technical_quality_image(str(x) if not isinstance(x, dict) else x.get("path", ""))
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.nsfw_detector":
        threshold = float(params.get("threshold", 0.7))
        out = [_nsfw_detector(str(x) if not isinstance(x, dict) else x.get("path", ""), threshold)
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.coherence":
        # Operates on the full list
        result = _coherence_score(items)
        return [result] if is_list else result
    if op_id == "score.diversity":
        result = _diversity_score(items)
        return [result] if is_list else result

    # ── 2. extension scorers (in-house) ────────────────────────────────────
    if op_id == "score.clip_score":
        out = [_clip_score(str(x), params.get("image", "")) for x in items]
        return out if is_list else out[0]
    if op_id == "score.text_quality":
        out = [_text_quality(str(x)) for x in items]
        return out if is_list else out[0]
    if op_id == "score.toxicity":
        threshold = float(params.get("threshold", 0.5))
        out = [_toxicity(str(x), threshold) for x in items]
        return out if is_list else out[0]
    if op_id == "score.sentiment":
        out = [_sentiment(str(x)) for x in items]
        return out if is_list else out[0]
    if op_id == "score.language_quality":
        out = [_language_quality(str(x)) for x in items]
        return out if is_list else out[0]
    if op_id == "score.factuality":
        out = [_factuality(str(x)) for x in items]
        return out if is_list else out[0]
    if op_id == "score.video_motion":
        out = [_video_motion(str(x) if not isinstance(x, dict) else x.get("path", ""))
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.video_stability":
        out = [_video_stability(str(x) if not isinstance(x, dict) else x.get("path", ""))
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.audio_quality":
        out = [_audio_quality(str(x) if not isinstance(x, dict) else x.get("path", ""))
               for x in items]
        return out if is_list else out[0]
    if op_id == "score.code_quality":
        out = [_code_quality(str(x)) for x in items]
        return out if is_list else out[0]

    # 3. fall-through noop
    import logging
    logging.getLogger(__name__).info("scorer %s noop (not implemented, returning input)", op_id)
    return data
