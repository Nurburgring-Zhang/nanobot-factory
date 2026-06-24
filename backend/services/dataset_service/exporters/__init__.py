"""dataset_service/exporters — 12 导出算子注册表.

每个 .py 文件导出 OP_ID, NAME, CATEGORY, DESCRIPTION, PARAMS, run() 函数.

12 算子:
  text:     jsonl, csv
  tabular:  parquet
  binary:   tfrecord
  detection: coco, voc, yolo
  llm_sft:  alpaca, sharegpt, conversation
  video:    video_frames
  audio:    audio_wav

(mixed.py 保留为扩展; 不计入默认 12)
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import (
    jsonl,
    parquet,
    csv,
    tfrecord,
    coco,
    voc,
    yolo,
    alpaca,
    sharegpt,
    conversation,
    video_frames,
    audio_wav,
)


def _build_registry() -> Dict[str, Any]:
    modules = [
        jsonl,
        parquet,
        csv,
        tfrecord,
        coco,
        voc,
        yolo,
        alpaca,
        sharegpt,
        conversation,
        video_frames,
        audio_wav,
    ]
    reg: Dict[str, Any] = {}
    for m in modules:
        assert hasattr(m, "OP_ID"), f"{m.__name__} missing OP_ID"
        assert hasattr(m, "run"), f"{m.__name__} missing run()"
        assert callable(m.run), f"{m.__name__}.run not callable"
        reg[m.OP_ID] = m
    return reg


OPERATORS: Dict[str, Any] = _build_registry()


def list_operators() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for op_id, m in OPERATORS.items():
        out.append({
            "id": m.OP_ID,
            "name": m.NAME,
            "category": m.CATEGORY,
            "description": m.DESCRIPTION,
            "params": list(getattr(m, "PARAMS", []) or []),
        })
    out.sort(key=lambda x: x["id"])
    return out


def get_operator(op_id: str):
    return OPERATORS.get(op_id)


__all__ = ["OPERATORS", "list_operators", "get_operator"]


# ── Optional extension: mixed multi-modal exporter ────────────────────────────
# mixed.py is provided as an extra exporter for unified multi-modal datasets
# but not counted in the default 12. Import it explicitly via:
#     from services.dataset_service.exporters.mixed import run as run_mixed
# when a unified cross-modal export is needed.
