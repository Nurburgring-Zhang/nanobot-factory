"""P3-6.5-W2: Hybrid Multimodal — Character Consistency.

Multi-image character dataset pipeline: collect character shots ->
face/pose detect -> CLIP embedding dedup -> per-shot caption ->
top-K selection -> LoRA/DreamBooth export with trigger token.

Category: multimodal
Improvements over ``tpl-biz-mm-003``:
  * Multi-character support (per-character trigger token)
  * Pose-aware sampling (keep diverse poses)
  * Expression tag (smile/neutral/angry/...) per shot
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-mm-h03",
    "category": "multimodal",
    "name": "Character Consistency Training Pipeline (Hybrid)",
    "tags": ["character", "consistency", "ip-adapter", "dreambooth",
             "multi-character"],
    "description": (
        "Multi-image character dataset: collect character shots (multi-char "
        "supported) -> face/pose/expression detect -> CLIP embedding dedup "
        "-> per-shot caption with pose+expression tag -> top-K diverse-pose "
        "selection -> LoRA / DreamBooth export with per-character trigger."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "characters": {"type": "array<object>", "required": True,
                            "description": "[{name, trigger_token, "
                                            "image_sources}]"},
            "min_shots_per_char": {"type": "int", "default": 20},
            "max_shots_per_char": {"type": "int", "default": 200},
            "embed_dedup_threshold": {"type": "float", "default": 0.92,
                                        "min": 0.0, "max": 1.0},
            "caption_model": {"type": "string",
                              "default": "llava-1.5-13b"},
            "oss_bucket": {"type": "string", "default": "char-data"},
        },
        outputs=["lora_train_data/", "captions.txt",
                 "trigger_tokens.json", "pose_stats.json",
                 "stats.json"],
        steps=[
            {"id": "col", "name": "Multi-Character Collect",
             "operator": "collection.character_source",
             "config": {"characters": "$inputs.characters"}},
            {"id": "fd", "name": "Face + Pose + Expression",
             "operator": "preprocessing.character_detect",
             "config": {"detect": ["face", "pose", "expression"]}},
            {"id": "dd", "name": "CLIP Embedding Dedup",
             "operator": "cleaning.clip_dedup",
             "config": {"threshold": "$inputs.embed_dedup_threshold"}},
            {"id": "cg", "name": "Per-Shot Caption",
             "operator": "annotation.vlm_caption",
             "config": {"model": "$inputs.caption_model",
                        "include": ["pose", "expression"]}},
            {"id": "tk", "name": "Diverse-Pose Top-K",
             "operator": "dataset.diverse_topk",
             "config": {"min": "$inputs.min_shots_per_char",
                        "max": "$inputs.max_shots_per_char",
                        "diversity_key": "pose"}},
            {"id": "wr", "name": "LoRA Export",
             "operator": "export.write_lora_dataset",
             "config": {"per_character": True}},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["characters", "shots_per_char",
                 "after_dedup", "after_quality",
                 "lora_rows", "duration_seconds"],
    ),
    "nodes": [_n("col", "multi_char_collect", "collection"),
              _n("fd", "face_pose_expression", "preprocessing", "col"),
              _n("dd", "clip_embed_dedup", "cleaning", "fd"),
              _n("cg", "vlm_caption", "annotation", "dd"),
              _n("tk", "diverse_topk", "dataset", "cg"),
              _n("wr", "lora_export", "export", "tk"),
              _n("up", "oss_upload", "export", "wr")],
}