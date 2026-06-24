"""P3-6-W1: business export template — COCO detection.

Pipeline (object detection COCO format export):
  1.  load_ann        - 加载 bbox 标注 dataset
  2.  schema_check    - 检查 image_id/annotation 必要字段
  3.  cat_index       - 构建 categories (id/name/supercategory)
  4.  bbox_norm       - 归一化 bbox 到 COCO xywh
  5.  iou_dedup       - 同一 image 内 IoU>0.95 的 box 合并
  6.  split           - train/val 切分 (默认 0.8/0.2, 按 category 分层)
  7.  write_coco      - 写 annotations.json + instances_train.json + instances_val.json
  8.  oss_upload      - 上传到 det-coco bucket

vs basic_templates/export.py::tpl-biz-exp-003: 本模板加入 schema 严格校验
  + iou dedup + 按 category 分层 split。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-exp-003",
    "name": "COCO Detection Export (商业级)",
    "category": "export",
    "description": (
        "目标检测 COCO 格式导出:schema 校验 + bbox xywh 归一化 + "
        "IoU dedup + 分层 train/val 切分 + COCO JSON 写出。"
    ),
    "tags": ["coco", "object-detection", "bbox", "json",
             "iou-dedup", "export", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "dataset_id": {"type": "string", "required": True,
                       "description": "bbox 标注 dataset UUID"},
        "category_set": {"type": "array<object>", "required": True,
                          "description": "[{id:int, name:str, "
                                          "supercategory:str}]"},
        "image_subdir": {"type": "string", "default": "images/"},
        "split_ratio": {"type": "array<float>", "default": [0.8, 0.2],
                         "description": "[train, val] 比例, sum=1"},
        "stratify": {"type": "boolean", "default": True,
                     "description": "按 category 分层切分"},
        "min_bbox_area": {"type": "float", "default": 1.0,
                          "description": "丢弃 area < 此值的 box"},
        "iou_dedup_threshold": {"type": "float", "default": 0.95,
                                 "description": "IoU > 此值视为重复"},
        "oss_bucket": {"type": "string", "default": "det-coco"},
        "oss_key_prefix": {"type": "string", "default": "coco/"},
    },
    "outputs": [
        "annotations.json",
        "instances_train.json",
        "instances_val.json",
        "category_index.json",
        "iou_dropped.jsonl",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Annotations",
         "operator": "dataset.load_annotations",
         "config": {"dataset_id": "$inputs.dataset_id"}},
        {"id": "sc", "name": "Schema Validate",
         "operator": "format.coco_schema_check",
         "config": {"require": ["image_id", "bbox", "category_id"]}},
        {"id": "ci", "name": "Build Category Index",
         "operator": "format.coco_categories",
         "config": {"category_set": "$inputs.category_set"}},
        {"id": "fa", "name": "Filter Tiny Boxes",
         "operator": "data.filter_bbox_area",
         "config": {"min_area": "$inputs.min_bbox_area"}},
        {"id": "bn", "name": "BBox Normalize to XYWH",
         "operator": "format.coco_bbox_normalize",
         "config": {"to": "xywh"}},
        {"id": "id", "name": "IoU Dedup (intra-image)",
         "operator": "data.iou_dedup",
         "config": {"threshold": "$inputs.iou_dedup_threshold"}},
        {"id": "sp", "name": "Train/Val Split",
         "operator": "data.split",
         "config": {"ratio": "$inputs.split_ratio",
                    "stratify": "$inputs.stratify"}},
        {"id": "wr", "name": "Write COCO JSON",
         "operator": "export.write_coco",
         "config": {"splits": ["train", "val"],
                    "image_subdir": "$inputs.image_subdir"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "images_total", "annotations_total",
        "categories_count", "boxes_after_filter",
        "iou_dropped", "bbox_stats", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]