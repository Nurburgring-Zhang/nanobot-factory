"""P19 v5.1-D3: YOLO TXT format exporter.

YOLOv5/v8 格式::

    <dataset_root>/
        images/
            0001.jpg
            0002.jpg
        labels/
            0001.txt        # 每行: <class_id> <cx> <cy> <w> <h> (normalized 0..1)
            0002.txt
        classes.names      # 一行一个 class name

我们把 dataset 内的 image 文件映射到 labels/, 写 classes.names (mock 类别).
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List


def _class_names() -> List[str]:
    return ["person", "car", "bicycle", "dog", "cat", "tree", "building", "sky"]


def export(dataset, output: str, **kwargs) -> str:
    out_path = output or "yolo_dataset.zip"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    classes = _class_names()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("classes.names", "\n".join(classes) + "\n")
        zf.writestr("data.yaml", (
            f"train: ./images\n"
            f"val: ./images\n"
            f"nc: {len(classes)}\n"
            f"names: {classes}\n"
        ))
        for i, f in enumerate(files):
            stem = os.path.splitext(os.path.basename(getattr(f, "path", "")))[0] or f"img_{i:06d}"
            stem_safe = stem.replace("/", "_").replace("\\", "_")
            # mock labels: 1-3 boxes per image, random but deterministic
            n_boxes = (i % 3) + 1
            label_lines: List[str] = []
            for b in range(n_boxes):
                cls_id = (i + b) % len(classes)
                cx = 0.1 + 0.7 * ((i + b) % 10) / 10
                cy = 0.1 + 0.7 * ((i + b * 2) % 10) / 10
                w = 0.1 + 0.05 * b
                h = 0.1 + 0.05 * b
                label_lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            zf.writestr(f"labels/{stem_safe}.txt", "\n".join(label_lines) + "\n")
    return out_path


def validate_yolo_zip(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "error": "file not found"}
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    has_classes = any(n.endswith("classes.names") for n in names)
    n_labels = sum(1 for n in names if n.endswith(".txt") and "/labels/" in n)
    return {
        "ok": has_classes and n_labels > 0,
        "n_files": len(names),
        "n_labels": n_labels,
        "has_classes_names": has_classes,
    }


__all__ = ["export", "validate_yolo_zip"]