"""Filter template: Human preference (人类偏好筛选).

Pipeline:
  1.  load          - 读 jsonl
  2.  rm_score      - reward model 打分
  3.  threshold     - 按阈值筛
  4.  dedup         - prompt 级别去重 (留分数最高的)
  5.  diversity     - embedding 多样性约束 (MMR)
  6.  write         - 输出 preference_filtered.jsonl
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-flt-005",
    "name": "Human Preference Filter (人类偏好筛选)",
    "category": "filter",
    "description": (
        "Reward model 打分 + 阈值过滤 + prompt 级去重 + MMR 多样性, "
        "输出高质量偏好子集。"
    ),
    "tags": ["filter", "preference", "rlhf", "mmr"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "reward_model": {"type": "string",
                           "default": "skywork-reward-llama-8b"},
        "min_reward_score": {"type": "float", "default": 0.5},
        "prompt_field": {"type": "string", "default": "prompt"},
        "enable_mmr": {"type": "bool", "default": True},
        "mmr_lambda": {"type": "float", "default": 0.7,
                        "description": "1=纯相关, 0=纯多样"},
        "embed_field": {"type": "string", "default": "embedding"},
        "max_outputs": {"type": "int", "default": 5000},
        "oss_bucket": {"type": "string", "default": "filtered"},
    },
    "outputs": ["preference_filtered.jsonl", "stats.json"],
    "steps": [
        {"id": "ld", "name": "Load",
         "operator": "filter.load",
         "config": {"source": "$inputs.input_manifest"}},
        {"id": "rm", "name": "Reward Score",
         "operator": "llm.reward_score",
         "config": {"model": "$inputs.reward_model",
                    "output_field": "reward_score"}},
        {"id": "th", "name": "Threshold",
         "operator": "filter.threshold",
         "config": {"min": "$inputs.min_reward_score",
                    "by": "reward_score"}},
        {"id": "dd", "name": "Prompt Dedup",
         "operator": "filter.prompt_dedup",
         "config": {"prompt_field": "$inputs.prompt_field",
                    "keep": "max_score"}},
        {"id": "mmr", "name": "MMR Diversity",
         "operator": "filter.mmr",
         "config": {"enabled": "$inputs.enable_mmr",
                    "lambda_": "$inputs.mmr_lambda",
                    "embed_field": "$inputs.embed_field",
                    "max_outputs": "$inputs.max_outputs"}},
        {"id": "wr", "name": "Write",
         "operator": "filter.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total",
                "score_mean", "dedup_count",
                "duration_seconds"],
}


__all__ = ["TEMPLATE"]