"""annot.image.classification — image classification operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'predictions'?: [{label, score}, ...]}
    params:
        top_k: int = 5                — keep top-K predictions
        min_confidence: float = 0.0   — drop predictions below
        label_set: list = []          — whitelist; empty=allow-all
        multi_label: bool = False     — keep all above threshold vs top-1

Returns per-image: {image_index, ok, top_label, top_score, predictions: [...]}.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import load_image_any


def _normalize(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "label": str(p.get("label", "unknown")),
        "class_id": p.get("class_id"),
        "score": float(p.get("score", 0.0)),
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    top_k = int(params.get("top_k", 5))
    min_conf = float(params.get("min_confidence", 0.0))
    label_set = set(str(x) for x in params.get("label_set") or [])
    multi = bool(params.get("multi_label", False))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"image_index": i}
        img_input = item.get("image") if isinstance(item, dict) and "image" in item else (
            {k: v for k, v in item.items() if k != "predictions"}
            if isinstance(item, dict) else item
        )
        img, meta = load_image_any(img_input)
        rec["image_meta"] = meta
        if img is None:
            rec.update({"ok": False, "predictions": [], "top_label": None})
            out.append(rec)
            continue
        raw_preds: List[Dict[str, Any]] = []
        if isinstance(item, dict) and isinstance(item.get("predictions"), list):
            raw_preds = [_normalize(p) for p in item["predictions"]]
        else:
            # fallback: heuristic pseudo-classification based on average color
            if isinstance(img, type(__import__("numpy").ndarray)):
                import numpy as _np
                bgr = img
                mean_bgr = bgr.reshape(-1, 3).mean(axis=0)
                avg = float(mean_bgr.mean())
                label = "bright" if avg > 160 else ("dark" if avg < 80 else "neutral")
                raw_preds = [{"label": label, "score": min(1.0, avg / 255.0)}]
        if label_set:
            raw_preds = [p for p in raw_preds if p["label"] in label_set]
        raw_preds = [p for p in raw_preds if p["score"] >= min_conf]
        raw_preds.sort(key=lambda p: p["score"], reverse=True)
        if not multi:
            preds = raw_preds[:1]
        else:
            preds = raw_preds[:top_k]
        top = preds[0] if preds else None
        rec.update({
            "ok": True,
            "predictions": preds,
            "top_label": top["label"] if top else None,
            "top_score": top["score"] if top else None,
            "count": len(preds),
        })
        out.append(rec)
    return out