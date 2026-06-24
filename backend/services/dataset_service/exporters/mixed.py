"""mixed — 混合多模态导出器 (统一 metadata + 各模态分目录).

op_id: export.mixed
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

OP_ID = "export.mixed"
NAME = "混合多模态导出"
CATEGORY = "multimodal"
DESCRIPTION = "混合多模态 dataset 统一 metadata JSONL + 各模态子目录"
PARAMS: list = [
    {"name": "dir", "type": "str", "default": "", "required": True},
    {"name": "modalities", "type": "list", "default": ["image", "text", "audio"], "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    base = str(params.get("dir", "")).strip()
    if not base:
        return {"ok": False, "error": "missing_dir"}
    modalities = [str(m) for m in params.get("modalities", ["image", "text", "audio"])]
    os.makedirs(base, exist_ok=True)
    for m in modalities:
        os.makedirs(os.path.join(base, m), exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    metadata_path = os.path.join(base, "metadata.jsonl")
    counts = {m: 0 for m in modalities}
    with open(metadata_path, "w", encoding="utf-8") as fp:
        for idx, x in enumerate(items):
            if isinstance(x, dict):
                rec_id = str(x.get("id", f"sample_{idx:06d}"))
                mod_paths = {}
                for m in modalities:
                    rel = x.get(m) or x.get(f"{m}_path")
                    if rel:
                        mod_paths[m] = str(rel)
                        counts[m] += 1
                text = x.get("text") or x.get("caption") or x.get("transcript")
                label = x.get("label") or x.get("category")
            else:
                rec_id = f"sample_{idx:06d}"
                mod_paths = {}
                text = str(x)
                label = None
            rec = {
                "id": rec_id,
                "modalities": mod_paths,
                "text": text,
                "label": label,
            }
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "format": "mixed",
        "dir": os.path.abspath(base),
        "metadata_path": os.path.abspath(metadata_path),
        "modalities": modalities,
        "modality_counts": counts,
        "sample_count": len(items),
    }
