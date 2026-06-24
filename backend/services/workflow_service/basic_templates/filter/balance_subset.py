"""Filter template: Balanced subset (类别平衡子集).

Pipeline:
  1.  load          - 读 jsonl
  2.  label_extract - 提 label_field (支持多标签)
  3.  per_class_n   - 计算每类配额 (max / min / ratio)
  4.  sample        - 每类配额内随机采样
  5.  long_tail     - 长尾类可选上采样 (重复 + augmentation)
  6.  write         - 输出 balanced.jsonl
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-flt-002",
    "name": "Balanced Subset (类别平衡子集)",
    "category": "filter",
    "description": (
        "按类别平衡采样, 支持 max/min/ratio 三种配额, "
        "长尾类可上采样。"
    ),
    "tags": ["filter", "balanced", "stratified"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "label_field": {"type": "string", "default": "label"},
        "multi_label": {"type": "bool", "default": False},
        "balance_mode": {"type": "string", "default": "max",
                          "enum": ["max", "min", "ratio"]},
        "balance_value": {"type": "int", "default": 1000},
        "upsample_long_tail": {"type": "bool", "default": False},
        "long_tail_threshold": {"type": "int", "default": 100},
        "random_seed": {"type": "int", "default": 42},
        "oss_bucket": {"type": "string", "default": "filtered"},
    },
    "outputs": ["balanced.jsonl", "stats.json"],
    "steps": [
        {"id": "ld", "name": "Load",
         "operator": "filter.load",
         "config": {"source": "$inputs.input_manifest"}},
        {"id": "lb", "name": "Extract Labels",
         "operator": "filter.label_extract",
         "config": {"field": "$inputs.label_field",
                    "multi_label": "$inputs.multi_label"}},
        {"id": "qn", "name": "Per-class Quota",
         "operator": "filter.per_class_quota",
         "config": {"mode": "$inputs.balance_mode",
                    "value": "$inputs.balance_value",
                    "long_tail_threshold":
                        "$inputs.long_tail_threshold"}},
        {"id": "sp", "name": "Stratified Sample",
         "operator": "filter.stratified_sample",
         "config": {"seed": "$inputs.random_seed",
                    "upsample": "$inputs.upsample_long_tail"}},
        {"id": "wr", "name": "Write",
         "operator": "filter.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "n_classes",
                "per_class_counts", "duration_seconds"],
}


__all__ = ["TEMPLATE"]