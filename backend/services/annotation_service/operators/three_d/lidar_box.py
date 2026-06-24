"""annot.3d.lidar_box — LiDAR 3D bounding box annotation operator.

Inputs:
    items: list of dicts {
        frame_id?,
        boxes: [{
            center:{x,y,z}, size:{w,h,l} | {l,w,h},
            yaw?, label?, score?, class_id?, track_id?
        }, ...]
    }
    params:
        min_volume: float = 0.01        — drop boxes smaller than this m³
        max_volume: float = 200.0
        min_score: float = 0.0
        iou_3d_threshold: float = 0.0   — NMS IoU 3D (0 disables)
        yaw_range: list = [-3.1416, 3.1416]
        allowed_labels: list = []       — empty=allow-all

Each box output: {id, center, size, yaw, label, score, volume, iou_3d_self}.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List


def _validate(b: Dict[str, Any]) -> Dict[str, Any]:
    c = b.get("center") or {"x": 0, "y": 0, "z": 0}
    s = b.get("size") or {"w": 1, "h": 1, "l": 1}
    if "l" in s and "w" in s and "h" in s:
        size = {"w": float(s["w"]), "h": float(s["h"]), "l": float(s["l"])}
    else:
        size = {
            "w": float(s.get("w", s.get("width", 1))),
            "h": float(s.get("h", s.get("height", 1))),
            "l": float(s.get("l", s.get("length", 1))),
        }
    return {
        "id": b.get("id") or f"box3d_{uuid.uuid4().hex[:8]}",
        "center": {"x": float(c.get("x", 0)), "y": float(c.get("y", 0)), "z": float(c.get("z", 0))},
        "size": size,
        "yaw": float(b.get("yaw", 0.0)),
        "label": str(b.get("label", "object")),
        "score": float(b.get("score", 1.0)),
        "class_id": b.get("class_id"),
        "track_id": b.get("track_id"),
    }


def _volume(b: Dict[str, Any]) -> float:
    s = b["size"]
    return abs(s["w"] * s["h"] * s["l"])


def _iou_3d(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Approximate axis-aligned 3D IoU ignoring yaw (good enough for NMS pre-filter)."""
    va = _volume(a)
    vb = _volume(b)
    if va <= 0 or vb <= 0:
        return 0.0
    inter_w = max(0.0, min(a["center"]["x"] + a["size"]["w"] / 2,
                           b["center"]["x"] + b["size"]["w"] / 2)
                  - max(a["center"]["x"] - a["size"]["w"] / 2,
                        b["center"]["x"] - b["size"]["w"] / 2))
    inter_h = max(0.0, min(a["center"]["y"] + a["size"]["h"] / 2,
                           b["center"]["y"] + b["size"]["h"] / 2)
                  - max(a["center"]["y"] - a["size"]["h"] / 2,
                        b["center"]["y"] - b["size"]["h"] / 2))
    inter_l = max(0.0, min(a["center"]["z"] + a["size"]["l"] / 2,
                           b["center"]["z"] + b["size"]["l"] / 2)
                  - max(a["center"]["z"] - a["size"]["l"] / 2,
                        b["center"]["z"] - b["size"]["l"] / 2))
    inter = inter_w * inter_h * inter_l
    union = va + vb - inter
    return inter / union if union > 0 else 0.0


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_vol = float(params.get("min_volume", 0.01))
    max_vol = float(params.get("max_volume", 200.0))
    min_score = float(params.get("min_score", 0.0))
    iou_thr = float(params.get("iou_3d_threshold", 0.0))
    yaw_range = params.get("yaw_range") or [-math.pi, math.pi]
    try:
        ylo, yhi = float(yaw_range[0]), float(yaw_range[1])
    except Exception:  # noqa: BLE001
        ylo, yhi = -math.pi, math.pi
    labels = set(str(x) for x in params.get("allowed_labels") or [])

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("boxes"), list):
            rec.update({"ok": False, "box_count": 0, "boxes": [],
                        "error": "missing_boxes"})
            out.append(rec)
            continue
        boxes = [_validate(b) for b in item["boxes"]]
        boxes = [b for b in boxes if min_vol <= _volume(b) <= max_vol]
        boxes = [b for b in boxes if b["score"] >= min_score]
        if labels:
            boxes = [b for b in boxes if b["label"] in labels]
        boxes = [b for b in boxes if ylo <= b["yaw"] <= yhi]
        # NMS
        if iou_thr > 0:
            sorted_boxes = sorted(boxes, key=lambda x: x["score"], reverse=True)
            kept: List[Dict[str, Any]] = []
            while sorted_boxes:
                best = sorted_boxes.pop(0)
                kept.append(best)
                sorted_boxes = [
                    x for x in sorted_boxes if _iou_3d(best, x) < iou_thr
                ]
            boxes = kept
        for b in boxes:
            b["volume"] = round(_volume(b), 4)
        rec.update({
            "ok": True,
            "frame_id": item.get("frame_id"),
            "box_count": len(boxes),
            "boxes": boxes,
        })
        out.append(rec)
    return out