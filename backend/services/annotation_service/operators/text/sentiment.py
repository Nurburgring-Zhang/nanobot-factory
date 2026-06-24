"""annot.text.sentiment — sentiment analysis operator.

Inputs:
    items: list of dicts {text: str, predictions?: [{label, score}]}
    params:
        label_set: list = ["positive", "negative", "neutral"]
        top_k: int = 1
        min_score: float = 0.0
        intensity_threshold: float = 0.0  — drop weak signals
        method: str = "lexicon"            — lexicon | heuristic | score

Each prediction: {label:str, score:float}.

Heuristic lexicon (zh + en):
  positive: 好,棒,喜欢,优秀,爱,完美,推荐,赞 / good, great, love, excellent, awesome
  negative: 差,坏,糟,讨厌,失望,烂,坑 / bad, terrible, hate, awful, worst

Returns per-item: {item_index, ok, label, score, intensity, scores: {label:score}}.
"""
from __future__ import annotations

from typing import Any, Dict, List

_POSITIVE = {
    "好": 1, "棒": 1, "喜欢": 1, "优秀": 1, "爱": 0.8, "完美": 1, "推荐": 1, "赞": 1,
    "good": 1, "great": 1, "love": 1, "excellent": 1, "awesome": 1, "best": 1, "amazing": 1,
}
_NEGATIVE = {
    "差": -1, "坏": -1, "糟": -1, "讨厌": -1, "失望": -1, "烂": -1, "坑": -1,
    "bad": -1, "terrible": -1, "hate": -1, "awful": -1, "worst": -1, "horrible": -1,
}


def _lexicon_score(text: str) -> float:
    if not text:
        return 0.0
    s = text.lower()
    pos = sum(w.count(k) * v for k, v in _POSITIVE.items() for w in [s] if k in w)
    neg = sum(w.count(k) * v for k, v in _NEGATIVE.items() for w in [s] if k in w)
    return pos + neg


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    label_set = [str(x) for x in (params.get("label_set") or
                                    ["positive", "negative", "neutral"])]
    top_k = int(params.get("top_k", 1))
    min_score = float(params.get("min_score", 0.0))
    intensity = float(params.get("intensity_threshold", 0.0))
    method = str(params.get("method", "lexicon"))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            rec.update({"ok": False, "label": None, "score": None,
                        "error": "missing_text"})
            out.append(rec)
            continue
        text = item["text"]
        scores: Dict[str, float] = {label: 0.0 for label in label_set}
        if isinstance(item.get("predictions"), list) and item["predictions"]:
            for p in item["predictions"]:
                lbl = str(p.get("label", ""))
                if lbl in scores:
                    scores[lbl] = float(p.get("score", 0.0))
        else:
            raw = _lexicon_score(text) if method == "lexicon" else 0.0
            if "positive" in scores and "negative" in scores:
                if raw > 0:
                    scores["positive"] = min(1.0, abs(raw))
                    scores["negative"] = 0.0
                elif raw < 0:
                    scores["negative"] = min(1.0, abs(raw))
                    scores["positive"] = 0.0
                else:
                    scores["neutral"] = scores.get("neutral", 1.0)
        # sort by score
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        ranked = [(lbl, s) for lbl, s in ranked if s >= min_score]
        if not ranked:
            ranked = [("neutral", 1.0)]
        top = ranked[0]
        rec.update({
            "ok": True,
            "text_length": len(text),
            "label": top[0],
            "score": top[1],
            "intensity": abs(top[1]) if top[0] != "neutral" else 0.0,
            "scores": scores,
            "top_k": [{"label": lbl, "score": s} for lbl, s in ranked[:top_k]],
        })
        if rec["intensity"] < intensity:
            rec["label"] = "neutral"
            rec["intensity"] = 0.0
        out.append(rec)
    return out