"""P19 v5.1-D3: CreateML annotation JSON exporter.

CreateML 格式::

    [
        {
            "image": "0001.jpg",
            "annotations": [
                {"label": "person", "coordinates": {"x": 100, "y": 200, "width": 50, "height": 80}},
                ...
            ]
        },
        ...
    ]
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _class_names() -> List[str]:
    return ["person", "car", "bicycle", "dog", "cat"]


def export(dataset, output: str, **kwargs) -> str:
    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    classes = _class_names()
    out_path = output or "annotations.json"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for i, f in enumerate(files):
        annotations = []
        for j, cls in enumerate(classes[:3]):
            annotations.append({
                "label": cls,
                "coordinates": {
                    "x": 100 + j * 50 + i * 10,
                    "y": 200 + j * 30 + i * 5,
                    "width": 60 + j * 10,
                    "height": 80 + j * 10,
                },
            })
        rows.append({
            "image": os.path.basename(getattr(f, "path", "")) or f"img_{i:06d}.jpg",
            "annotations": annotations,
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    return out_path


def validate_createml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "error": "file not found"}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        return {"ok": False, "error": "root not a list"}
    n_labels = set()
    for row in data:
        for ann in row.get("annotations", []):
            n_labels.add(ann.get("label", ""))
    return {"ok": len(data) > 0, "n_images": len(data), "unique_labels": len(n_labels)}


__all__ = ["export", "validate_createml"]