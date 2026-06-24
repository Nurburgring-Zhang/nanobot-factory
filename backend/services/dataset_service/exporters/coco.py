"""coco — COCO 目标检测格式导出器.

op_id: export.coco
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

OP_ID = "export.coco"
NAME = "COCO 导出"
CATEGORY = "detection"
DESCRIPTION = "导出目标检测 dataset 到 COCO JSON 格式 (images + annotations + categories)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "image_field", "type": "str", "default": "image", "required": False},
    {"name": "bbox_field", "type": "str", "default": "bbox", "required": False},
    {"name": "category_field", "type": "str", "default": "category", "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    image_field = str(params.get("image_field", "image"))
    bbox_field = str(params.get("bbox_field", "bbox"))
    category_field = str(params.get("category_field", "category"))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    images = []
    annotations = []
    categories_set = {}
    ann_id = 1
    for img_id, x in enumerate(items, start=1):
        if not isinstance(x, dict):
            continue
        file_name = str(x.get(image_field, x.get("path", f"img_{img_id}.jpg")))
        width = int(x.get("width", 1024))
        height = int(x.get("height", 1024))
        images.append({
            "id": img_id,
            "file_name": file_name,
            "width": width,
            "height": height,
        })
        bboxes = x.get(bbox_field) or []
        cats = x.get(category_field) or []
        if isinstance(bboxes, list):
            for i, b in enumerate(bboxes):
                if not isinstance(b, (list, tuple)) or len(b) < 4:
                    continue
                x_, y_, w_, h_ = b[:4]
                cat_name = cats[i] if i < len(cats) else "object"
                if cat_name not in categories_set:
                    categories_set[cat_name] = len(categories_set) + 1
                cat_id = categories_set[cat_name]
                annotations.append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": [float(x_), float(y_), float(w_), float(h_)],
                    "area": float(w_) * float(h_),
                    "iscrowd": 0,
                })
                ann_id += 1
    coco = {
        "info": {"description": "nanobot-factory COCO export", "version": "1.0"},
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": [
            {"id": cid, "name": name, "supercategory": "none"}
            for name, cid in categories_set.items()
        ],
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(coco, fp, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "format": "coco",
        "path": os.path.abspath(path),
        "image_count": len(images),
        "annotation_count": len(annotations),
        "category_count": len(categories_set),
    }
