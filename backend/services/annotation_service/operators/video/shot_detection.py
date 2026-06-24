"""annot.video.shot_detection — shot/scene boundary detection operator.

Inputs:
    items: list of dicts {
        video_id, fps?,
        frames: [{frame_id, features: {mean_brightness?, mean_color?, histogram?, ...}}]
    }
    params:
        threshold: float = 0.30          — diff threshold (0..1)
        min_shot_length: int = 1         — min frames between shots
        method: str = "brightness"       — brightness | histogram | combined
        hysteresis: float = 0.05         — keep prev decision if within hysteresis

Returns per-item: {item_index, ok, frame_count, shot_count, shots: [{start_frame,end_frame,length}]}.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _feature(fr: Dict[str, Any], method: str) -> float:
    """Reduce a frame to a scalar feature."""
    f = fr.get("features") or {}
    if method == "brightness":
        if "mean_brightness" in f:
            return float(f["mean_brightness"])
        if "mean_color" in f and isinstance(f["mean_color"], (list, tuple)):
            vals = [float(x) for x in f["mean_color"]]
            return sum(vals) / len(vals) if vals else 0.0
        return 0.0
    if method == "histogram":
        hist = f.get("histogram")
        if isinstance(hist, list) and hist:
            vals = [float(x) for x in hist]
            return sum(vals) / len(vals) if vals else 0.0
        return 0.0
    # combined
    parts = []
    if "mean_brightness" in f:
        parts.append(float(f["mean_brightness"]))
    if "mean_color" in f and isinstance(f["mean_color"], (list, tuple)):
        parts.extend(float(x) for x in f["mean_color"])
    if "histogram" in f and isinstance(f["histogram"], list):
        parts.extend(float(x) for x in f["histogram"][:8])
    return sum(parts) / len(parts) if parts else 0.0


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    threshold = float(params.get("threshold", 0.30))
    min_len = int(params.get("min_shot_length", 1))
    method = str(params.get("method", "brightness"))
    hysteresis = float(params.get("hysteresis", 0.05))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("frames"), list):
            rec.update({"ok": False, "shot_count": 0, "shots": [],
                        "error": "missing_frames"})
            out.append(rec)
            continue
        frames = sorted(item["frames"], key=lambda f: f.get("frame_id", 0))
        if len(frames) < 2:
            rec.update({"ok": True, "shot_count": 1,
                        "shots": [{"start_frame": 0,
                                   "end_frame": len(frames) - 1,
                                   "length": len(frames)}]})
            out.append(rec)
            continue
        feats = [_feature(fr, method) for fr in frames]
        # normalize feature range to [0,1]
        lo, hi = min(feats), max(feats)
        rng = max(1e-9, hi - lo)
        nfeats = [(f - lo) / rng for f in feats]
        # detect boundaries
        shots_raw: List[Dict[str, int]] = []
        cur_start = 0
        for j in range(1, len(frames)):
            diff = abs(nfeats[j] - nfeats[j - 1])
            if diff >= threshold + (hysteresis if diff > threshold - hysteresis else 0):
                shots_raw.append({
                    "start_frame": int(frames[cur_start].get("frame_id", cur_start)),
                    "end_frame": int(frames[j - 1].get("frame_id", j - 1)),
                    "length": j - cur_start,
                })
                cur_start = j
        shots_raw.append({
            "start_frame": int(frames[cur_start].get("frame_id", cur_start)),
            "end_frame": int(frames[-1].get("frame_id", len(frames) - 1)),
            "length": len(frames) - cur_start,
        })
        # enforce min length
        merged: List[Dict[str, int]] = []
        for s in shots_raw:
            if merged and s["length"] < min_len:
                merged[-1]["end_frame"] = s["end_frame"]
                merged[-1]["length"] = merged[-1]["end_frame"] - merged[-1]["start_frame"] + 1
            else:
                merged.append(dict(s))
        rec.update({
            "ok": True,
            "video_id": item.get("video_id"),
            "fps": item.get("fps"),
            "frame_count": len(frames),
            "shot_count": len(merged),
            "method": method,
            "threshold": threshold,
            "shots": merged,
        })
        out.append(rec)
    return out