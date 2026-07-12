"""P19 v5.1-D3: Pascal VOC XML format exporter.

VOC 格式 (per-image XML)::

    <annotation>
        <folder>imagenet</folder>
        <filename>0001.jpg</filename>
        <size><width>640</width><height>480</height><depth>3</depth></size>
        <object>
            <name>person</name>
            <pose>Unspecified</pose>
            <truncated>0</truncated>
            <difficult>0</difficult>
            <bndbox><xmin>100</xmin><ymin>200</ymin><xmax>300</xmax><ymax>400</ymax></bndbox>
        </object>
    </annotation>

输出: 单个 .xml 文件 (mock 单张 image 的多 object annotation).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def _class_names() -> list:
    return ["person", "car", "bicycle", "dog", "cat"]


def export(dataset, output: str, image_width: int = 640, image_height: int = 480, **kwargs) -> str:
    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    classes = _class_names()
    out_path = output or "annotation.xml"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    lines: list = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append("<annotation>")
    lines.append("    <folder>nanobot-factory</folder")
    if files:
        first = files[0]
        fname = os.path.basename(getattr(first, "path", "0001.jpg"))
    else:
        fname = "0001.jpg"
    lines.append(f"    <filename>{fname}</filename>")
    lines.append("    <source>")
    lines.append("        <database>nanobot-factory VOC2007</database>")
    lines.append("        <annotation>nanobot-factory</annotation>")
    lines.append("        <image>flickr</image>")
    lines.append("    </source>")
    lines.append(f"    <size><width>{image_width}</width><height>{image_height}</height><depth>3</depth></size>")
    lines.append("    <segmented>0</segmented>")
    # mock 2-3 object
    for i, cls_name in enumerate(classes[:3]):
        xmin = 50 + i * 100
        ymin = 80 + i * 80
        xmax = xmin + 150
        ymax = ymin + 180
        lines.append("    <object>")
        lines.append(f"        <name>{cls_name}</name>")
        lines.append("        <pose>Unspecified</pose>")
        lines.append("        <truncated>0</truncated>")
        lines.append("        <difficult>0</difficult>")
        lines.append("        <bndbox>")
        lines.append(f"            <xmin>{xmin}</xmin><ymin>{ymin}</ymin><xmax>{xmax}</xmax><ymax>{ymax}</ymax>")
        lines.append("        </bndbox>")
        lines.append("    </object>")
    lines.append("</annotation>")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out_path


def validate_voc_xml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "error": "file not found"}
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    if "<annotation>" not in content:
        return {"ok": False, "error": "missing <annotation>"}
    n_objects = content.count("<object>")
    has_size = "<size>" in content
    return {"ok": n_objects > 0 and has_size, "n_objects": n_objects, "has_size": has_size}


__all__ = ["export", "validate_voc_xml"]