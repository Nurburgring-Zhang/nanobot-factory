"""voc — Pascal VOC 目标检测格式导出器 (XML per image).

op_id: export.voc
"""
from __future__ import annotations

import os
from typing import Any, Dict
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

OP_ID = "export.voc"
NAME = "Pascal VOC 导出"
CATEGORY = "detection"
DESCRIPTION = "导出目标检测 dataset 到 Pascal VOC 格式 (XML per image)"
PARAMS: list = [
    {"name": "dir", "type": "str", "default": "", "required": True,
     "description": "Output directory (will create Annotations/, ImageSets/, JPEGImages/)"},
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
    ann_dir = os.path.join(base, "Annotations")
    imgset_dir = os.path.join(base, "ImageSets", "Main")
    os.makedirs(ann_dir, exist_ok=True)
    os.makedirs(imgset_dir, exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    written = 0
    image_ids = []
    for x in items:
        if not isinstance(x, dict):
            continue
        file_name = str(x.get(image_field, x.get("path", "")))
        if not file_name:
            continue
        # Derive image_id from file_name stem
        stem = os.path.splitext(os.path.basename(file_name))[0]
        image_ids.append(stem)
        width = int(x.get("width", 1024))
        height = int(x.get("height", 1024))
        depth = int(x.get("depth", 3))
        bboxes = x.get(bbox_field) or []
        cats = x.get(category_field) or []
        root = Element("annotation")
        SubElement(root, "folder").text = "JPEGImages"
        SubElement(root, "filename").text = os.path.basename(file_name)
        size = SubElement(root, "size")
        SubElement(size, "width").text = str(width)
        SubElement(size, "height").text = str(height)
        SubElement(size, "depth").text = str(depth)
        for i, b in enumerate(bboxes):
            if not isinstance(b, (list, tuple)) or len(b) < 4:
                continue
            xmin, ymin, xmax, ymax = b[:4]
            obj = SubElement(root, "object")
            cat_name = cats[i] if i < len(cats) else "object"
            SubElement(obj, "name").text = str(cat_name)
            SubElement(obj, "pose").text = "Unspecified"
            SubElement(obj, "truncated").text = "0"
            SubElement(obj, "difficult").text = "0"
            bb = SubElement(obj, "bndbox")
            SubElement(bb, "xmin").text = str(int(xmin))
            SubElement(bb, "ymin").text = str(int(ymin))
            SubElement(bb, "xmax").text = str(int(xmax))
            SubElement(bb, "ymax").text = str(int(ymax))
        xml_str = minidom.parseString(tostring(root, encoding="utf-8")).toprettyxml(indent="  ")
        ann_path = os.path.join(ann_dir, f"{stem}.xml")
        with open(ann_path, "w", encoding="utf-8") as fp:
            fp.write(xml_str)
        written += 1
    # ImageSets/Main/{train,val,test}.txt
    for split in ("train", "val", "test"):
        with open(os.path.join(imgset_dir, f"{split}.txt"), "w", encoding="utf-8") as fp:
            fp.write("\n".join(image_ids) + "\n")
    return {
        "ok": True,
        "format": "voc",
        "dir": os.path.abspath(base),
        "annotation_count": written,
        "image_ids": len(image_ids),
    }
