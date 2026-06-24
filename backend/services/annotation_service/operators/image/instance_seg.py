"""annot.image.instance_seg — instance segmentation operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'instances'?: [{mask, bbox, ...}]}
    params:
        max_instances: int = 100
        iou_threshold: float = 0.5   — NMS IoU threshold for dedup
        min_area: int = 16           — drop tiny masks
        mask_format: str = "polygon" — expected mask format in 'instances' input

Each instance dict: {mask, bbox:{x1,y1,x2,y2,label,score}, label, score, class_id}.

Returns per-image: {image_index, ok, count, instances: [...], area_stats}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, bbox_iou_xyxy, polygon_area

VALID_MASK_FORMATS = {"polygon", "rle", "binary", "bbox_only"}


def _validate(inst: Dict[str, Any]) -> Dict[str, Any]:
    bbox = inst.get("bbox") or {}
    return {
        "id": inst.get("id") or f"inst_{uuid.uuid4().hex[:8]}",
        "class_id": inst.get("class_id"),
        "label": str(inst.get("label", "instance")),
        "score": float(inst.get("score", 1.0)),
        "bbox": {
            "x1": float(bbox.get("x1", 0)),
            "y1": float(bbox.get("y1", 0)),
            "x2": float(bbox.get("x2", 0)),
            "y2": float(bbox.get("y2", 0)),
            "label": str(bbox.get("label", inst.get("label", "instance"))),
            "score": float(bbox.get("score", inst.get("score", 1.0))),
        },
        "mask": inst.get("mask"),  # raw mask payload; format determined by mask_format
        "mask_format": inst.get("mask_format", "polygon"),
    }


def _compute_area(inst: Dict[str, Any]) -> float:
    fmt = inst.get("mask_format", "polygon")
    m = inst.get("mask")
    if m is None:
        return 0.0
    if fmt == "polygon":
        return polygon_area(m) if isinstance(m, list) else 0.0
    if fmt == "binary" and _HAS_NUMPY:
        try:
            return float(__import__("numpy").asarray(m).sum())
        except Exception:  # noqa: BLE001
            return 0.0
    if fmt == "bbox_only":
        b = inst["bbox"]
        return max(0.0, b["x2"] - b["x1"]) * max(0.0, b["y2"] - b["y1"])
    return 0.0


def _nms(insts: List[Dict[str, Any]], iou_thr: float) -> List[Dict[str, Any]]:
    if iou_thr <= 0 or not insts:
        return insts
    sorted_insts = sorted(insts, key=lambda x: x["bbox"].get("score", 1.0), reverse=True)
    keep: List[Dict[str, Any]] = []
    while sorted_insts:
        best = sorted_insts.pop(0)
        keep.append(best)
        sorted_insts = [
            x for x in sorted_insts
            if bbox_iou_xyxy(best["bbox"], x["bbox"]) < iou_thr
        ]
    return keep


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_inst = int(params.get("max_instances", 100))
    iou_thr = float(params.get("iou_threshold", 0.5))
    min_area = float(params.get("min_area", 16))
    mask_format = str(params.get("mask_format", "polygon"))
    if mask_format not in VALID_MASK_FORMATS:
        mask_format = "polygon"

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"image_index": i}
        if not isinstance(item, dict) or not isinstance(item.get("instances"), list):
            rec.update({"ok": False, "count": 0, "instances": [],
                        "error": "missing_instances_list"})
            out.append(rec)
            continue
        validated = [_validate(x) for x in item["instances"]]
        kept = [x for x in validated if _compute_area(x) >= min_area]
        kept = _nms(kept, iou_thr)
        if len(kept) > max_inst:
            kept = sorted(kept, key=lambda x: x["bbox"].get("score", 1.0), reverse=True)[:max_inst]
        areas = [_compute_area(x) for x in kept]
        rec.update({
            "ok": True,
            "count": len(kept),
            "instances": kept,
            "mask_format": mask_format,
            "area_stats": {
                "total": round(sum(areas), 2),
                "mean": round(sum(areas) / len(areas), 2) if areas else 0.0,
                "max": round(max(areas), 2) if areas else 0.0,
                "min": round(min(areas), 2) if areas else 0.0,
            },
        })
        out.append(rec)
    return out