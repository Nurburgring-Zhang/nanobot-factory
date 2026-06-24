"""Annotation template: Image classification (图像分类标注).

Pipeline:
  1.  prelabel      - 调 foundation model 给 top-K 候选标签
  2.  split         - 切分流 (prelabel 信心高 -> auto; 否则人工)
  3.  human         - 人工标注 (label studio / CVAT 集成)
  4.  consensus     - 多标注员一致性 (Cohen's Kappa)
  5.  export        - 导出 JSONL/CSV (含 confidence)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-ann-001",
    "name": "Image Classification Annotation (图像分类标注)",
    "category": "annotation",
    "description": (
        "基础模型预标注 + 人工标注 + 多标注员一致性, 输出含 confidence "
        "的分类标签 JSONL。"
    ),
    "tags": ["image", "annotation", "classification", "consensus"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "label_taxonomy": {"type": "string", "required": True,
                            "description": "label taxonomy JSON path"},
        "prelabel_topk": {"type": "int", "default": 5},
        "auto_threshold": {"type": "float", "default": 0.85},
        "reviewers_per_item": {"type": "int", "default": 2},
        "oss_bucket": {"type": "string", "default": "annotations"},
    },
    "outputs": ["labels.jsonl", "agreement.json", "stats.json"],
    "steps": [
        {"id": "pl", "name": "Prelabel",
         "operator": "vision.classify",
         "config": {"model": "clip-vit-l",
                    "taxonomy": "$inputs.label_taxonomy",
                    "top_k": "$inputs.prelabel_topk"}},
        {"id": "sp", "name": "Auto/Human Split",
         "operator": "annotation.split",
         "config": {"auto_threshold": "$inputs.auto_threshold"}},
        {"id": "hu", "name": "Human Annotate",
         "operator": "annotation.human",
         "config": {"tool": "label-studio",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item",
                    "sla_hours": 24}},
        {"id": "ag", "name": "Consensus",
         "operator": "annotation.consensus",
         "config": {"metric": "cohens_kappa",
                    "min_kappa": 0.6}},
        {"id": "ex", "name": "Export",
         "operator": "annotation.export",
         "config": {"format": "jsonl",
                    "include_confidence": True,
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["items_total", "auto_labeled", "human_labeled",
                "kappa", "duration_hours"],
}


__all__ = ["TEMPLATE"]