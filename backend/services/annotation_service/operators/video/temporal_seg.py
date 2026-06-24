"""annot.video.temporal_seg — temporal segmentation operator.

Inputs:
    items: list of dicts {
        video_id, fps?,
        segments: [{segment_id?, start_time, end_time, label, score?, metadata?}]
    }
    params:
        min_duration: float = 0.1          — drop shorter segments
        max_duration: float = 600.0
        merge_same_label: bool = False     — merge adjacent segments with same label
        min_gap: float = 0.0              — gap threshold when merging
        allow_overlap: bool = False        — if False, enforce non-overlap
        label_set: list = []              — empty=allow-all

Each segment: {start_time (sec), end_time (sec), label, score?}.

Returns per-item: {item_index, ok, segment_count, duration_total, segments: [...]}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


def _validate(seg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": seg.get("id") or f"seg_{uuid.uuid4().hex[:8]}",
        "start_time": float(seg.get("start_time", 0.0)),
        "end_time": float(seg.get("end_time", 0.0)),
        "label": str(seg.get("label", "segment")),
        "score": float(seg.get("score", 1.0)),
        "metadata": seg.get("metadata") or {},
    }


def _merge(segments: List[Dict[str, Any]], min_gap: float) -> List[Dict[str, Any]]:
    if not segments:
        return segments
    segs = sorted(segments, key=lambda s: (s["start_time"], s["end_time"]))
    out: List[Dict[str, Any]] = [segs[0]]
    for s in segs[1:]:
        last = out[-1]
        if (s["label"] == last["label"]
                and s["start_time"] - last["end_time"] <= min_gap):
            last["end_time"] = max(last["end_time"], s["end_time"])
            last["score"] = max(last["score"], s["score"])
        else:
            out.append(s)
    return out


def _drop_overlaps(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep highest-score segment when segments overlap."""
    if not segments:
        return segments
    segs = sorted(segments, key=lambda s: s["start_time"])
    out: List[Dict[str, Any]] = []
    for s in segs:
        if out and s["start_time"] < out[-1]["end_time"]:
            if s["score"] > out[-1]["score"]:
                out[-1] = s
        else:
            out.append(s)
    return out


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_dur = float(params.get("min_duration", 0.1))
    max_dur = float(params.get("max_duration", 600.0))
    do_merge = bool(params.get("merge_same_label", False))
    min_gap = float(params.get("min_gap", 0.0))
    no_overlap = not bool(params.get("allow_overlap", False))
    label_set = set(str(x) for x in params.get("label_set") or [])

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("segments"), list):
            rec.update({"ok": False, "segment_count": 0, "segments": [],
                        "error": "missing_segments"})
            out.append(rec)
            continue
        segs = [_validate(s) for s in item["segments"]]
        segs = [s for s in segs if (s["end_time"] - s["start_time"]) >= min_dur]
        segs = [s for s in segs if (s["end_time"] - s["start_time"]) <= max_dur]
        if label_set:
            segs = [s for s in segs if s["label"] in label_set]
        if no_overlap:
            segs = _drop_overlaps(segs)
        if do_merge:
            segs = _merge(segs, min_gap)
        total = sum(max(0.0, s["end_time"] - s["start_time"]) for s in segs)
        rec.update({
            "ok": True,
            "video_id": item.get("video_id"),
            "fps": item.get("fps"),
            "segment_count": len(segs),
            "duration_total": round(total, 4),
            "segments": segs,
        })
        out.append(rec)
    return out