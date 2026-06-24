"""Scoring template: Safety filter score (安全性评分).

Pipeline:
  1.  nsfw          - NSFW 分类
  2.  violence      - 暴力分类 (image/video)
  3.  hate          - 仇恨/歧视 (text/CLIP)
  4.  self_harm     - 自残/自杀信号
  5.  pii_leak      - PII 泄露检测
  6.  aggregate     - 取最严重风险 + 总分
  7.  write         - 输出安全等级 + 处置建议
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-scr-004",
    "name": "Safety Filter Score (安全性评分)",
    "category": "scoring",
    "description": (
        "NSFW + 暴力 + 仇恨 + 自残 + PII 多维安全评分, "
        "聚合输出 risk_level (low/medium/high) 和处置建议。"
    ),
    "tags": ["safety", "scoring", "nsfw", "moderation"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "nsfw_threshold": {"type": "float", "default": 0.85},
        "violence_threshold": {"type": "float", "default": 0.7},
        "hate_threshold": {"type": "float", "default": 0.7},
        "self_harm_threshold": {"type": "float", "default": 0.6},
        "modality": {"type": "string", "default": "image",
                      "enum": ["image", "video", "text"]},
        "oss_bucket": {"type": "string", "default": "scores-safety"},
    },
    "outputs": ["safety_scores.jsonl", "stats.json"],
    "steps": [
        {"id": "nsfw", "name": "NSFW",
         "operator": "safety.nsfw",
         "config": {"threshold": "$inputs.nsfw_threshold",
                    "modality": "$inputs.modality"}},
        {"id": "vio", "name": "Violence",
         "operator": "safety.violence",
         "config": {"threshold": "$inputs.violence_threshold",
                    "modality": "$inputs.modality"}},
        {"id": "hate", "name": "Hate",
         "operator": "safety.hate",
         "config": {"threshold": "$inputs.hate_threshold",
                    "modality": "$inputs.modality"}},
        {"id": "sh", "name": "Self-Harm",
         "operator": "safety.self_harm",
         "config": {"threshold": "$inputs.self_harm_threshold",
                    "modality": "$inputs.modality"}},
        {"id": "pii", "name": "PII Leak",
         "operator": "safety.pii_leak",
         "config": {"engine":
                        "imdf.cleaning_service.pii_engine"}},
        {"id": "agg", "name": "Aggregate",
         "operator": "safety.aggregate",
         "config": {"policy": "max_severity",
                    "level_thresholds": {"low": 0.3,
                                          "medium": 0.6,
                                          "high": 0.85}}},
        {"id": "wr", "name": "Write",
         "operator": "scoring.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["items_scored",
                "by_level", "by_category",
                "duration_seconds"],
}


__all__ = ["TEMPLATE"]