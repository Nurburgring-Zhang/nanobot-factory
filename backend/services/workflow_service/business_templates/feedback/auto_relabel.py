"""P3-6-W1: business feedback template — Auto Relabel.

Pipeline (基于评分阈值的自动重标注):
  1.  load_ann         - 加载已有标注 dataset
  2.  conf_flt         - 过滤 confidence < max_confidence 的样本
  3.  load_strong      - 加载更强模型 (e.g. qwen-vl-max)
  4.  prelabel         - 强模型预标注
  5.  consensus        - 与旧标注做共识 (IoU for bbox / exact for class)
  6.  conflict_resolve - 冲突时优先新模型 + 留 trace
  7.  diff_export      - 输出 diff.jsonl (old_label vs new_label)
  8.  merge_export     - 输出 merged.jsonl (final label)
  9.  oss_upload       - 上传到 relabel bucket

vs basic_templates/feedback.py::tpl-biz-fb-004: 本模板加入强模型加载 +
  consensus + 冲突解决策略 + diff/merge 双导出。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-fb-004",
    "name": "Auto Relabel (商业级)",
    "category": "feedback",
    "description": (
        "基于评分阈值的自动重标注:confidence 过滤 + 强模型预标注 + "
        "共识 + 冲突解决 + diff/merge 双导出。"
    ),
    "tags": ["relabel", "auto-label", "feedback",
             "consensus", "conflict", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "annotation_dataset_id": {"type": "string", "required": True},
        "max_confidence": {"type": "float", "default": 0.7,
                            "description": "labels with conf < 此值被重标注"},
        "stronger_model": {"type": "string", "default": "qwen-vl-max"},
        "stronger_model_path": {"type": "string", "required": False,
                                 "description": "本地路径或 HF repo"},
        "consensus_mode": {"type": "string", "default": "iou_bbox",
                            "enum": ["iou_bbox", "exact_match",
                                     "weighted", "majority"]},
        "iou_threshold": {"type": "float", "default": 0.5,
                           "description": "IoU > 此值视为一致 (bbox only)"},
        "conflict_strategy": {"type": "string", "default": "prefer_new",
                               "enum": ["prefer_new", "prefer_old",
                                        "reject", "human_review"]},
        "max_workers": {"type": "int", "default": 4},
        "oss_bucket": {"type": "string", "default": "relabel"},
        "oss_key_prefix": {"type": "string", "default": "relabel/"},
    },
    "outputs": [
        "relabel.jsonl",
        "diff.jsonl",
        "merged.jsonl",
        "conflict_review.jsonl",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Existing Annotations",
         "operator": "dataset.load_annotations",
         "config": {"dataset_id": "$inputs.annotation_dataset_id"}},
        {"id": "cf", "name": "Low-Confidence Filter",
         "operator": "dataset.low_confidence",
         "config": {"max": "$inputs.max_confidence"}},
        {"id": "sm", "name": "Load Stronger Model",
         "operator": "model.load",
         "config": {"name": "$inputs.stronger_model",
                    "path": "$inputs.stronger_model_path"}},
        {"id": "pl", "name": "Strong-Model Prelabel",
         "operator": "annotation.prelabel",
         "config": {"model": "$inputs.stronger_model",
                    "max_workers": "$inputs.max_workers"}},
        {"id": "cs", "name": "Consensus Compare",
         "operator": "annotation.consensus_merge",
         "config": {"mode": "$inputs.consensus_mode",
                    "iou_threshold": "$inputs.iou_threshold"}},
        {"id": "cr", "name": "Conflict Resolve",
         "operator": "annotation.conflict_resolve",
         "config": {"strategy": "$inputs.conflict_strategy"}},
        {"id": "wr", "name": "Export Diff + Merged",
         "operator": "export.write_relabel",
         "config": {"include_conflict_trace": True}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "annotations_total", "low_confidence_count",
        "relabeled", "consensus_kept", "conflicts",
        "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]