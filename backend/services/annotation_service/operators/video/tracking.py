"""annot.video.tracking — multi-object tracking operator.

Inputs:
    items: list of dicts {frame_id, detections: [{bbox:{x1,y1,x2,y2}, score, label, class_id}, ...]}
    params:
        max_age: int = 30               — drop tracks after this many frames without match
        min_hits: int = 3               — minimum detections before confirming a track
        iou_threshold: float = 0.3     — IoU gate for detection-track association
        method: str = "iou"             — iou | centroid

Each track output: {track_id, label, class_id, frames: [{frame_id, bbox, score}], length, score_avg}.

Returns per-item: {item_index, ok, track_count, tracks: [...]}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .._image_utils import bbox_iou_xyxy


class _Track:
    __slots__ = ("track_id", "label", "class_id", "frames", "last_seen", "score_sum")

    def __init__(self, det: Dict[str, Any], frame_id: Any, tid: str):
        self.track_id = tid
        self.label = str(det.get("label", "object"))
        self.class_id = det.get("class_id")
        self.frames: List[Dict[str, Any]] = []
        self.last_seen: Any = frame_id
        self.score_sum: float = 0.0
        self._add(det, frame_id)

    def _add(self, det: Dict[str, Any], frame_id: Any) -> None:
        b = det["bbox"]
        self.frames.append({
            "frame_id": frame_id,
            "bbox": b,
            "score": float(det.get("score", 1.0)),
        })
        self.score_sum += float(det.get("score", 1.0))
        self.last_seen = frame_id


def _match(tracks: List[_Track], dets: List[Dict[str, Any]], iou_thr: float) -> List[int]:
    """Greedy IoU matching. Return list of detection indices matched to tracks (same order)."""
    if not tracks or not dets:
        return [-1] * len(dets)
    pairs: List[tuple] = []
    for ti, t in enumerate(tracks):
        if not t.frames:
            continue
        last_bbox = t.frames[-1]["bbox"]
        for di, d in enumerate(dets):
            iou = bbox_iou_xyxy(last_bbox, d["bbox"])
            if iou >= iou_thr:
                pairs.append((iou, ti, di))
    pairs.sort(reverse=True)
    matched_t = set()
    matched_d = set()
    assignment = [-1] * len(dets)
    for _, ti, di in pairs:
        if ti in matched_t or di in matched_d:
            continue
        matched_t.add(ti)
        matched_d.add(di)
        assignment[di] = ti
    return assignment


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_age = int(params.get("max_age", 30))
    min_hits = int(params.get("min_hits", 3))
    iou_thr = float(params.get("iou_threshold", 0.3))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("detections"), list):
            rec.update({"ok": False, "track_count": 0, "tracks": [],
                        "error": "missing_detections"})
            out.append(rec)
            continue
        frame_id = item.get("frame_id", 0)
        dets = item.get("detections", [])
        # accept per-item track state for sequential multi-frame inputs
        tracks: List[_Track] = item.get("_state_tracks", [])  # type: ignore[arg-type]
        next_id_counter = item.get("_state_next_id", 1)  # type: ignore[arg-type]
        if not tracks:
            tracks = []
            next_id_counter = 1
        # match
        assignment = _match(tracks, dets, iou_thr)
        for di, (det, ti) in enumerate(zip(dets, assignment)):
            if ti >= 0:
                tracks[ti]._add(det, frame_id)
            else:
                tracks.append(_Track(det, frame_id, f"trk_{next_id_counter:04d}"))
                next_id_counter += 1
        # prune old tracks
        try:
            cutoff = int(frame_id) - max_age
            tracks = [t for t in tracks if int(t.last_seen) >= cutoff]
        except Exception:  # noqa: BLE001
            pass
        # serialize
        out_tracks: List[Dict[str, Any]] = []
        for t in tracks:
            if len(t.frames) < min_hits:
                continue
            avg = t.score_sum / len(t.frames) if t.frames else 0.0
            out_tracks.append({
                "track_id": t.track_id,
                "label": t.label,
                "class_id": t.class_id,
                "length": len(t.frames),
                "score_avg": round(avg, 4),
                "frames": t.frames,
                "first_frame": t.frames[0]["frame_id"],
                "last_frame": t.frames[-1]["frame_id"],
            })
        rec.update({
            "ok": True,
            "frame_id": frame_id,
            "track_count": len(out_tracks),
            "tracks": out_tracks,
        })
        out.append(rec)
    return out