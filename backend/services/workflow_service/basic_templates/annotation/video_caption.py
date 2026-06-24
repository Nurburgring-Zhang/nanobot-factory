"""Annotation template: Video caption annotation (视频描述标注).

Pipeline:
  1.  shot_detect   - 镜头边界检测 (PySceneDetect)
  2.  frame_extract - 每镜关键帧
  3.  prelabel_cap  - LLaVA / Video-LLaVA 给候选描述
  4.  human_review  - 人工润色 + 时间戳对齐
  5.  export        - 输出 JSONL (含 start/end/caption)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-ann-003",
    "name": "Video Caption Annotation (视频描述标注)",
    "category": "annotation",
    "description": (
        "镜头分割 + 关键帧 + 多模态 LLM 预描述 + 人工润色 + 时间戳对齐, "
        "输出 VideoCaption JSONL。"
    ),
    "tags": ["video", "annotation", "caption"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "shot_threshold": {"type": "float", "default": 27.0},
        "caption_model": {"type": "string",
                           "default": "video-llava-7b"},
        "max_caption_words": {"type": "int", "default": 80},
        "reviewers_per_item": {"type": "int", "default": 1},
        "oss_bucket": {"type": "string", "default": "annotations"},
    },
    "outputs": ["captions.jsonl", "stats.json"],
    "steps": [
        {"id": "shot", "name": "Shot Detect",
         "operator": "video.shot_detect",
         "config": {"threshold": "$inputs.shot_threshold",
                    "method": "content"}},
        {"id": "kf", "name": "Extract Keyframes",
         "operator": "video.extract_keyframes",
         "config": {"fps": 0.5}},
        {"id": "cap", "name": "Prelabel Caption",
         "operator": "video.caption",
         "config": {"model": "$inputs.caption_model",
                    "max_words": "$inputs.max_caption_words"}},
        {"id": "hu", "name": "Human Review",
         "operator": "annotation.caption_human",
         "config": {"tool": "label-studio",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item",
                    "align_timestamps": True}},
        {"id": "ex", "name": "Export",
         "operator": "annotation.export",
         "config": {"format": "jsonl",
                    "include_timestamps": True,
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["videos_total", "shots_total",
                "avg_shot_duration_sec",
                "captions_per_video", "duration_hours"],
}


__all__ = ["TEMPLATE"]