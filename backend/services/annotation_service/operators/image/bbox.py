"""annot.image.bbox — rectangle bbox annotation operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'boxes'?: [bbox,...]}
    params:
        min_area: int = 16           — drop boxes smaller than this area
        iou_threshold: float = 0.0  — NMS IoU threshold (0 disables NMS)
        min_confidence: float = 0.0 — drop boxes below this score
        max_boxes: int = 1000       — cap per image
        auto_estimate: bool = False — heuristic auto-boxing (edge-density regions)

Each input bbox must be a dict with at least x1,y1,x2,y2. Optional keys:
    label, score, class_id, mask (binary mask path), kpts.

Returns per-image: {image_id, image_shape, count, boxes: [validated bbox], notes}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, bbox_iou_xyxy, ensure_numpy_bgr, load_image_any


def _validate(box: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a bbox dict: ensure x1,y1,x2,y2, label, score, id."""
    out = {
        "id": box.get("id") or f"box_{uuid.uuid4().hex[:8]}",
        "x1": float(box.get("x1", 0)),
        "y1": float(box.get("y1", 0)),
        "x2": float(box.get("x2", 0)),
        "y2": float(box.get("y2", 0)),
        "label": str(box.get("label", "object")),
        "score": float(box.get("score", 1.0)),
        "class_id": box.get("class_id"),
    }
    if out["x2"] < out["x1"]:
        out["x1"], out["x2"] = out["x2"], out["x1"]
    if out["y2"] < out["y1"]:
        out["y1"], out["y2"] = out["y2"], out["y1"]
    return out


def _nms(boxes: List[Dict[str, Any]], iou_thr: float) -> List[Dict[str, Any]]:
    """Greedy NMS — keep highest score, drop overlaps above iou_thr."""
    if not boxes or iou_thr <= 0:
        return boxes
    sorted_boxes = sorted(boxes, key=lambda b: b.get("score", 1.0), reverse=True)
    keep: List[Dict[str, Any]] = []
    while sorted_boxes:
        best = sorted_boxes.pop(0)
        keep.append(best)
        sorted_boxes = [
            b for b in sorted_boxes
            if bbox_iou_xyxy(best, b) < iou_thr
        ]
    return keep


def _auto_estimate(img: Any, max_boxes: int) -> List[Dict[str, Any]]:
    """Edge-density heuristic: find dense-gradient rectangular regions."""
    if not _HAS_CV2 or not _HAS_NUMPY:
        return []
    arr = ensure_numpy_bgr(img)
    if arr is None:
        return []
    try:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if _HAS_CV2 else arr.mean(axis=-1)
    except Exception:  # noqa: BLE001
        return []
    edges = cv2.Canny(gray, 80, 200) if _HAS_CV2 else None
    if edges is None:
        return []
    # downsample to grid; pick cells with edge density > threshold
    h, w = edges.shape
    gh, gw = max(1, h // 8), max(1, w // 8)
    boxes: List[Dict[str, Any]] = []
    for gy in range(0, h, gh):
        for gx in range(0, w, gw):
            patch = edges[gy:gy + gh, gx:gx + gw]
            density = float(patch.mean()) / 255.0
            if density > 0.10:
                boxes.append({
                    "x1": float(gx), "y1": float(gy),
                    "x2": float(min(w, gx + gw)), "y2": float(min(h, gy + gh)),
                    "label": "auto_region",
                    "score": min(1.0, density * 4.0),
                })
                if len(boxes) >= max_boxes:
                    return boxes
    return boxes


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_area = int(params.get("min_area", 16))
    iou_thr = float(params.get("iou_threshold", 0.0))
    min_conf = float(params.get("min_confidence", 0.0))
    max_boxes = int(params.get("max_boxes", 1000))
    auto_est = bool(params.get("auto_estimate", False))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        if isinstance(item, dict) and "boxes" in item:
            img_input = {k: v for k, v in item.items() if k != "boxes"}
        else:
            img_input = item
        img, meta = load_image_any(img_input)
        rec: Dict[str, Any] = {"image_index": i, "image_meta": meta}
        if img is None:
            rec["ok"] = False
            rec["boxes"] = []
            rec["count"] = 0
            out.append(rec)
            continue
        raw_boxes: List[Dict[str, Any]] = []
        if isinstance(item, dict) and isinstance(item.get("boxes"), list):
            raw_boxes = [_validate(b) for b in item["boxes"]]
        if auto_est:
            raw_boxes.extend(_validate(b) for b in _auto_estimate(img, max_boxes))
        # filter
        kept = [b for b in raw_boxes if (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) >= min_area]
        kept = [b for b in kept if b.get("score", 1.0) >= min_conf]
        kept = _nms(kept, iou_thr)
        if len(kept) > max_boxes:
            kept = sorted(kept, key=lambda b: b.get("score", 1.0), reverse=True)[:max_boxes]
        rec.update({
            "ok": True,
            "count": len(kept),
            "boxes": kept,
        })
        out.append(rec)
    return out