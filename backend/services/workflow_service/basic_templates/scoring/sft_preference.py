"""Scoring template: SFT/DPO preference (SFT/DPO 偏好评分).

Pipeline:
  1.  pair_align    - 对齐 chosen/rejected (id 匹配)
  2.  rm_score      - Reward model 打分 (Skywork/InternLM)
  3.  pairwise      - chosen/rejected 分数对比 -> preference label
  4.  margin        - 计算 margin (chosen - rejected)
  5.  export_dpo    - 输出 DPO 训练 jsonl (含 margin)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-scr-002",
    "name": "SFT/DPO Preference Score (SFT/DPO 偏好评分)",
    "category": "scoring",
    "description": (
        "对齐 chosen/rejected 配对, 调 reward model 打分, 输出 margin "
        "和 DPO 训练格式。"
    ),
    "tags": ["text", "scoring", "dpo", "rlhf"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "reward_model": {"type": "string",
                           "default": "skywork-reward-llama-8b"},
        "min_margin": {"type": "float", "default": 0.0,
                        "description": "过滤 margin < min_margin 的对"},
        "normalize": {"type": "bool", "default": True},
        "oss_bucket": {"type": "string", "default": "scores"},
    },
    "outputs": ["preferences.jsonl", "stats.json"],
    "steps": [
        {"id": "align", "name": "Pair Align",
         "operator": "preference.align",
         "config": {"on": "prompt_id",
                    "require_chosen_rejected": True}},
        {"id": "rm", "name": "Reward Model Score",
         "operator": "llm.reward_score",
         "config": {"model": "$inputs.reward_model",
                    "inputs": ["chosen", "rejected"],
                    "normalize": "$inputs.normalize"}},
        {"id": "pw", "name": "Pairwise Compare",
         "operator": "preference.pairwise",
         "config": {"margin_field": "margin",
                    "label_field": "label"}},
        {"id": "flt", "name": "Margin Filter",
         "operator": "preference.filter",
         "config": {"min_margin": "$inputs.min_margin"}},
        {"id": "ex", "name": "Export DPO",
         "operator": "preference.export_dpo",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["pairs_total", "pairs_kept",
                "margin_mean", "margin_std",
                "duration_seconds"],
}


__all__ = ["TEMPLATE"]