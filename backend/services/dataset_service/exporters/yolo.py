"""yolo — YOLO 目标检测格式导出器 (txt per image + classes.txt + yaml).

op_id: export.yolo
"""
from __future__ import annotations

import os
from typing import Any, Dict

OP_ID = "export.yolo"
NAME = "YOLO 导出"
CATEGORY = "detection"
DESCRIPTION = "导出目标检测 dataset 到 YOLO 格式 (归一化 cx,cy,w,h per image + classes.txt + data.yaml)"
PARAMS: list = [
    {"name": "dir", "type": "str", "default": "", "required": True},
    {"name": "image_field", "type": "str", "default": "image", "required": False},
    {"name": "bbox_field", "type": "str", "default": "bbox", "required": False},
    {"name": "category_field", "type": "str", "default": "category", "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    base = str(params.get("dir", "")).strip()
    if not base:
        return {"ok": False, "error": "missing_dir"}
    image_field = str(params.get("image_field", "image"))
    bbox_field = str(params.get("bbox_field", "bbox"))
    category_field = str(params.get("category_field", "category"))
    labels_dir = os.path.join(base, "labels")
    images_dir = os.path.join(base, "images")
    os.makedirs(labels_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    classes: Dict[str, int] = {}
    written = 0
    for x in items:
        if not isinstance(x, dict):
            continue
        file_name = str(x.get(image_field, x.get("path", "")))
        if not file_name:
            continue
        stem = os.path.splitext(os.path.basename(file_name))[0]
        width = float(x.get("width", 1024)) or 1.0
        height = float(x.get("height", 1024)) or 1.0
        bboxes = x.get(bbox_field) or []
        cats = x.get(category_field) or []
        lines = []
        for i, b in enumerate(bboxes):
            if not isinstance(b, (list, tuple)) or len(b) < 4:
                continue
            xmin, ymin, xmax, ymax = b[:4]
            cx = (float(xmin) + float(xmax)) / 2.0 / width
            cy = (float(ymin) + float(ymax)) / 2.0 / height
            w = (float(xmax) - float(xmin)) / width
            h = (float(ymax) - float(ymin)) / height
            cat_name = cats[i] if i < len(cats) else "object"
            if cat_name not in classes:
                classes[cat_name] = len(classes)
            cls_id = classes[cat_name]
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        with open(os.path.join(labels_dir, f"{stem}.txt"), "w", encoding="utf-8") as fp:
            fp.write("\n".join(lines) + "\n")
        written += 1
    # classes.txt
    class_names = [n for n, _ in sorted(classes.items(), key=lambda x: x[1])]
    with open(os.path.join(base, "classes.txt"), "w", encoding="utf-8") as fp:
        fp.write("\n".join(class_names) + "\n")
    # data.yaml
    yaml_text = (
        f"path: {os.path.abspath(base)}\n"
        f"train: images\n"
        f"val: images\n"
        f"test: images\n"
        f"nc: {len(classes)}\n"
        f"names: {class_names}\n"
    )
    with open(os.path.join(base, "data.yaml"), "w", encoding="utf-8") as fp:
        fp.write(yaml_text)
    return {
        "ok": True,
        "format": "yolo",
        "dir": os.path.abspath(base),
        "label_count": written,
        "class_count": len(classes),
        "classes": class_names,
    }
