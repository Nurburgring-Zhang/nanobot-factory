"""annot.text.text_classification — general text classification operator.

Inputs:
    items: list of dicts {text: str, predictions?: [{label, score, class_id?}]}
    params:
        top_k: int = 1
        min_score: float = 0.0
        label_set: list = []            — empty=allow-all
        multi_label: bool = False       — return top-k vs single
        strip_html: bool = True
        min_text_length: int = 1
        max_text_length: int = 100000

Returns per-item: {item_index, ok, top_label, top_score, predictions}.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s).strip()


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    top_k = int(params.get("top_k", 1))
    min_score = float(params.get("min_score", 0.0))
    label_set = set(str(x) for x in params.get("label_set") or [])
    multi = bool(params.get("multi_label", False))
    strip = bool(params.get("strip_html", True))
    min_len = int(params.get("min_text_length", 1))
    max_len = int(params.get("max_text_length", 100000))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            rec.update({"ok": False, "top_label": None,
                        "error": "missing_text"})
            out.append(rec)
            continue
        text = item["text"]
        if strip:
            text = _strip_html(text)
        if not (min_len <= len(text) <= max_len):
            rec.update({"ok": False, "top_label": None,
                        "error": "text_length_out_of_range",
                        "text_length": len(text)})
            out.append(rec)
            continue
        preds: List[Dict[str, Any]] = []
        raw = item.get("predictions", []) or []
        for p in raw:
            lbl = str(p.get("label", "unknown"))
            score = float(p.get("score", 0.0))
            if label_set and lbl not in label_set:
                continue
            if score < min_score:
                continue
            preds.append({"label": lbl, "class_id": p.get("class_id"), "score": score})
        preds.sort(key=lambda p: p["score"], reverse=True)
        if multi:
            preds = preds[:top_k] if top_k > 0 else preds
        else:
            preds = preds[:1]
        top = preds[0] if preds else None
        rec.update({
            "ok": True,
            "text_length": len(text),
            "top_label": top["label"] if top else None,
            "top_score": top["score"] if top else None,
            "predictions": preds,
        })
        out.append(rec)
    return out