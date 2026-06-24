"""Scoring template: Multimodal consistency (多模态一致性评分).

Pipeline:
  1.  text_embed    - 文本 embedding (bge-m3)
  2.  img_embed     - 图像 embedding (CLIP/DINOv2)
  3.  clip_score    - CLIP cosine similarity
  4.  vision_check  - 视觉合理性 (VQA-LLM 判定)
  5.  composite     - 加权综合
  6.  write_scores  - 写回
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-scr-003",
    "name": "Multimodal Consistency (多模态一致性评分)",
    "category": "scoring",
    "description": (
        "CLIP 文本-图像一致性 + VQA 视觉合理性 + 综合分数, "
        "评估多模态对齐质量。"
    ),
    "tags": ["multimodal", "scoring", "clip", "alignment"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "text_field": {"type": "string", "default": "caption"},
        "image_field": {"type": "string", "default": "image_url"},
        "clip_model": {"type": "string", "default": "clip-vit-l"},
        "vqa_model": {"type": "string", "default": "llava-1.6-13b"},
        "clip_weight": {"type": "float", "default": 0.7},
        "vqa_weight": {"type": "float", "default": 0.3},
        "oss_bucket": {"type": "string", "default": "scores"},
    },
    "outputs": ["scores.jsonl", "stats.json"],
    "steps": [
        {"id": "et", "name": "Text Embedding",
         "operator": "text.embed",
         "config": {"model": "bge-m3",
                    "field": "$inputs.text_field",
                    "normalize": True}},
        {"id": "ei", "name": "Image Embedding",
         "operator": "image.embed",
         "config": {"model": "$inputs.clip_model",
                    "field": "$inputs.image_field",
                    "normalize": True}},
        {"id": "cs", "name": "CLIP Score",
         "operator": "multimodal.clip_score",
         "config": {"metric": "cosine",
                    "output_field": "clip_score"}},
        {"id": "vqa", "name": "Vision QA Check",
         "operator": "llm.vqa",
         "config": {"model": "$inputs.vqa_model",
                    "question": "Does the image match the caption?",
                    "output_field": "vqa_score"}},
        {"id": "comp", "name": "Composite",
         "operator": "scoring.weighted_combine",
         "config": {"formula":
                        "clip_score*$clip_weight+vqa_score*$vqa_weight",
                    "clip_weight": "$inputs.clip_weight",
                    "vqa_weight": "$inputs.vqa_weight",
                    "output_field": "consistency_score"}},
        {"id": "wr", "name": "Write Scores",
         "operator": "scoring.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["items_scored", "score_mean",
                "clip_score_mean", "vqa_score_mean",
                "duration_seconds"],
}


__all__ = ["TEMPLATE"]