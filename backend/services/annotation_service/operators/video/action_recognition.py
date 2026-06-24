"""annot.video.action_recognition — temporal action recognition operator.

Inputs:
    items: list of dicts {
        video_id,
        clips: [{clip_id, start_frame, end_frame, predictions: [{label, score}]}]
    }
    params:
        top_k: int = 5
        min_confidence: float = 0.0
        label_set: list = []              — empty=allow-all
        min_clip_length: int = 1
        max_clip_length: int = 100000
        action_categories: list = []      — optional list of allowed action names

Returns per-item: {item_index, ok, clip_count, clips: [...]}.
"""
from __future__ import annotations

from typing import Any, Dict, List


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    top_k = int(params.get("top_k", 5))
    min_conf = float(params.get("min_confidence", 0.0))
    label_set = set(str(x) for x in params.get("label_set") or [])
    categories = set(str(x) for x in params.get("action_categories") or [])
    min_len = int(params.get("min_clip_length", 1))
    max_len = int(params.get("max_clip_length", 100000))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("clips"), list):
            rec.update({"ok": False, "clip_count": 0, "clips": [],
                        "error": "missing_clips"})
            out.append(rec)
            continue
        clips_out: List[Dict[str, Any]] = []
        for c in item["clips"]:
            length = int(c.get("end_frame", 0)) - int(c.get("start_frame", 0))
            if length < min_len or length > max_len:
                continue
            preds = c.get("predictions", []) or []
            preds = [
                {"label": str(p.get("label", "unknown")),
                 "class_id": p.get("class_id"),
                 "score": float(p.get("score", 0.0))}
                for p in preds
            ]
            if label_set:
                preds = [p for p in preds if p["label"] in label_set]
            if categories:
                preds = [p for p in preds if p["label"] in categories]
            preds = [p for p in preds if p["score"] >= min_conf]
            preds.sort(key=lambda p: p["score"], reverse=True)
            preds = preds[:top_k]
            clips_out.append({
                "clip_id": c.get("clip_id"),
                "start_frame": c.get("start_frame"),
                "end_frame": c.get("end_frame"),
                "length_frames": length,
                "top_label": preds[0]["label"] if preds else None,
                "top_score": preds[0]["score"] if preds else None,
                "predictions": preds,
            })
        rec.update({
            "ok": True,
            "video_id": item.get("video_id"),
            "clip_count": len(clips_out),
            "clips": clips_out,
        })
        out.append(rec)
    return out