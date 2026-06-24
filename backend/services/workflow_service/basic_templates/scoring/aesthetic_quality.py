"""Scoring template: Aesthetic + technical quality (美学+技术质量评分).

Pipeline:
  1.  aes_score     - LAION-Aesthetic v2 评分
  2.  tech_score    - 技术质量 (BRISQUE / NIQE / blur / exposure)
  3.  comp_score    - 综合加权 (默认 aes*0.6 + tech*0.4)
  4.  histogram     - 分数分布直方图
  5.  write_scores  - 写回 jsonl (per-image)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-scr-001",
    "name": "Aesthetic + Technical Quality (美学+技术质量评分)",
    "category": "scoring",
    "description": (
        "LAION-Aesthetic 美学 + BRISQUE/NIQE/blur/exposure 技术质量 "
        "综合评分, 输出 per-image 分数 + 分布直方图。"
    ),
    "tags": ["image", "scoring", "aesthetic", "quality"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "aes_model": {"type": "string",
                       "default": "laion-aes-v2"},
        "aes_weight": {"type": "float", "default": 0.6},
        "tech_weight": {"type": "float", "default": 0.4},
        "expose_low": {"type": "float", "default": 0.1},
        "expose_high": {"type": "float", "default": 0.9},
        "oss_bucket": {"type": "string", "default": "scores"},
    },
    "outputs": ["scores.jsonl", "histogram.json"],
    "steps": [
        {"id": "aes", "name": "Aesthetic Score",
         "operator": "image.aesthetic_score",
         "config": {"model": "$inputs.aes_model",
                    "output_field": "aes_score"}},
        {"id": "tech", "name": "Technical Quality",
         "operator": "image.tech_quality",
         "config": {"metrics": ["brisque", "niqe",
                                "blur_var", "exposure"],
                    "expose_low": "$inputs.expose_low",
                    "expose_high": "$inputs.expose_high"},
         "depends_on": []},
        {"id": "comp", "name": "Composite",
         "operator": "scoring.weighted_combine",
         "config": {"formula": "aes*$aes_weight+tech*$tech_weight",
                    "aes_weight": "$inputs.aes_weight",
                    "tech_weight": "$inputs.tech_weight",
                    "output_field": "composite_score"}},
        {"id": "hist", "name": "Histogram",
         "operator": "scoring.histogram",
         "config": {"field": "composite_score",
                    "bins": 20}},
        {"id": "wr", "name": "Write Scores",
         "operator": "scoring.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["items_scored", "score_mean", "score_std",
                "score_p50", "score_p99", "duration_seconds"],
}


__all__ = ["TEMPLATE"]