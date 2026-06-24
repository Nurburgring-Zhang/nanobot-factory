"""Filter template: Top-K quality (Top-K 质量筛选).

Pipeline:
  1.  load_scores   - 读 jsonl (含 quality_score 字段)
  2.  sort          - 按 quality_score 降序
  3.  top_k         - 取前 K 个 (或 K% 比例)
  4.  tie_break     - 同分用 created_at / id 稳定排序
  5.  write         - 输出 topk.jsonl + manifest
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-flt-001",
    "name": "Top-K Quality (Top-K 质量筛选)",
    "category": "filter",
    "description": (
        "按 quality_score 排序取 Top-K (支持 K 或 比例), "
        "同分稳定排序, 输出 topk.jsonl。"
    ),
    "tags": ["filter", "topk", "quality"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "score_field": {"type": "string", "default": "quality_score"},
        "k_mode": {"type": "string", "default": "absolute",
                    "enum": ["absolute", "ratio"]},
        "k_value": {"type": "int", "default": 1000},
        "tie_break_field": {"type": "string", "default": "created_at"},
        "oss_bucket": {"type": "string", "default": "filtered"},
    },
    "outputs": ["topk.jsonl", "manifest.json"],
    "steps": [
        {"id": "ld", "name": "Load Scores",
         "operator": "filter.load_scores",
         "config": {"source": "$inputs.input_manifest",
                    "score_field": "$inputs.score_field"}},
        {"id": "sort", "name": "Sort Descending",
         "operator": "filter.sort",
         "config": {"by": "$inputs.score_field",
                    "ascending": False}},
        {"id": "tk", "name": "Top-K",
         "operator": "filter.top_k",
         "config": {"mode": "$inputs.k_mode",
                    "value": "$inputs.k_value",
                    "tie_break": "$inputs.tie_break_field"}},
        {"id": "wr", "name": "Write",
         "operator": "filter.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "score_min",
                "score_max", "score_mean", "duration_seconds"],
}


__all__ = ["TEMPLATE"]