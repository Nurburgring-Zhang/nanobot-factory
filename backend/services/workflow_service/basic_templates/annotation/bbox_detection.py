"""Annotation template: Bounding-box detection (目标检测标注).

Pipeline:
  1.  prelabel       - GroundingDINO / DETA 给候选 bbox + class
  2.  prompt_tune    - 用户补 classes 描述
  3.  human_bbox     - 人工校验/增删 bbox (CVAT 集成)
  4.  iou_check      - 标注员间 IoU 检查
  5.  export_coco    - 导出 COCO JSON
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-ann-002",
    "name": "Bounding Box Detection (目标检测标注)",
    "category": "annotation",
    "description": (
        "GroundingDINO 预标注 + 人工校验 + IoU 一致性 + COCO 导出。"
    ),
    "tags": ["image", "annotation", "detection", "bbox"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "class_prompts": {"type": "array<string>", "required": True,
                           "description": "e.g. ['person', 'car', 'dog']"},
        "prelabel_threshold": {"type": "float", "default": 0.3},
        "reviewers_per_item": {"type": "int", "default": 2},
        "min_iou_threshold": {"type": "float", "default": 0.7},
        "oss_bucket": {"type": "string", "default": "annotations"},
    },
    "outputs": ["annotations_coco.json", "agreement.json"],
    "steps": [
        {"id": "pl", "name": "GroundingDINO Prelabel",
         "operator": "vision.detect",
         "config": {"model": "grounding-dino-base",
                    "prompts": "$inputs.class_prompts",
                    "threshold": "$inputs.prelabel_threshold"}},
        {"id": "hu", "name": "Human BBox",
         "operator": "annotation.bbox_human",
         "config": {"tool": "cvat",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item",
                    "sla_hours": 48}},
        {"id": "iou", "name": "IoU Consensus",
         "operator": "annotation.iou_check",
         "config": {"min_iou": "$inputs.min_iou_threshold",
                    "require_min_2_agree": True}},
        {"id": "ex", "name": "Export COCO",
         "operator": "annotation.export_coco",
         "config": {"include_segmentation": False,
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["items_total", "boxes_total", "avg_boxes_per_image",
                "iou_mean", "duration_hours"],
}


__all__ = ["TEMPLATE"]