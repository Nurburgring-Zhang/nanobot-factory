"""Filter template: Difficulty curriculum (难度课程子集).

Pipeline:
  1.  load          - 读 jsonl
  2.  score_diff    - 计算难度分数 (loss / entropy / 规则难度)
  3.  bucket        - 分桶 (easy/medium/hard)
  4.  schedule      - 课程排程 (阶段 -> 桶比例)
  5.  sample        - 按 schedule 采样
  6.  write         - 输出 curriculum.jsonl + schedule.json
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-flt-003",
    "name": "Difficulty Curriculum (难度课程子集)",
    "category": "filter",
    "description": (
        "按难度分数分桶 (easy/medium/hard), 按课程 schedule 比例 "
        "采样, 适合 curriculum learning。"
    ),
    "tags": ["filter", "curriculum", "difficulty"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "score_field": {"type": "string", "default": "loss"},
        "n_buckets": {"type": "int", "default": 3,
                       "enum": [3, 5, 10]},
        "schedule": {"type": "array<object>",
                      "default": [
                          {"stage": 0, "ratios": [1.0, 0.0, 0.0]},
                          {"stage": 1, "ratios": [0.5, 0.5, 0.0]},
                          {"stage": 2, "ratios": [0.3, 0.4, 0.3]},
                          {"stage": 3, "ratios": [0.0, 0.3, 0.7]},
                      ]},
        "current_stage": {"type": "int", "default": 0},
        "random_seed": {"type": "int", "default": 42},
        "oss_bucket": {"type": "string", "default": "filtered"},
    },
    "outputs": ["curriculum.jsonl", "schedule.json", "stats.json"],
    "steps": [
        {"id": "ld", "name": "Load",
         "operator": "filter.load",
         "config": {"source": "$inputs.input_manifest"}},
        {"id": "diff", "name": "Score Difficulty",
         "operator": "filter.score_difficulty",
         "config": {"score_field": "$inputs.score_field",
                    "normalize": "quantile"}},
        {"id": "bk", "name": "Bucket",
         "operator": "filter.bucket",
         "config": {"n_buckets": "$inputs.n_buckets",
                    "strategy": "quantile"}},
        {"id": "sch", "name": "Apply Schedule",
         "operator": "filter.curriculum_schedule",
         "config": {"schedule": "$inputs.schedule",
                    "current_stage": "$inputs.current_stage"}},
        {"id": "sp", "name": "Sample",
         "operator": "filter.stratified_sample",
         "config": {"seed": "$inputs.random_seed"}},
        {"id": "wr", "name": "Write",
         "operator": "filter.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total",
                "per_bucket_counts", "stage", "duration_seconds"],
}


__all__ = ["TEMPLATE"]