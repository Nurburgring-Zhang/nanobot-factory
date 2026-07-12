"""P19 v5.1-D3: CLIP JSONL exporter (image-text pairs).

CLIP 训练格式: 每行一个 ``{"image": path, "caption": text}`` JSON 对象.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


_MOCK_CAPTIONS = [
    "a photo of a person",
    "a cat sitting on a chair",
    "a car parked on the street",
    "a dog running in the park",
    "a bicycle leaning against a wall",
    "a tree in autumn",
    "a building with glass windows",
    "an airplane flying in the sky",
]


def export(dataset, output: str, **kwargs) -> str:
    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    out_path = output or "clip_pairs.jsonl"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for i, f in enumerate(files):
            cap = _MOCK_CAPTIONS[i % len(_MOCK_CAPTIONS)]
            row = {
                "image": os.path.basename(getattr(f, "path", "")) or f"img_{i:06d}.jpg",
                "caption": cap,
                "image_id": i,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_path


def validate_clip_jsonl(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "error": "file not found"}
    n = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                return {"ok": False, "error": f"line {n + 1} not valid JSON"}
            if "image" not in obj or "caption" not in obj:
                return {"ok": False, "error": f"line {n + 1} missing image/caption"}
            n += 1
    return {"ok": n > 0, "n_pairs": n}


__all__ = ["export", "validate_clip_jsonl"]