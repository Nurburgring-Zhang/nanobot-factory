"""P3-6.5-W2: Hybrid Business Pipeline — Multimodal SFT.

Multimodal image+text SFT pipeline with paired data alignment, CLIP-based
quality filter, conversation formatting, and ShareGPT + Parquet export.

Category: pipeline
Stage coverage: collection -> alignment -> cleaning -> scoring -> format -> export

Improvements over ``tpl-biz-pipe-008``:
  * Aspect-ratio aware filtering (keep AR 1:1 to 16:9)
  * Multi-image conversation support (up to N images per turn)
  * Conversation quality score (turn coherence + entity coverage)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h08",
    "category": "pipeline",
    "name": "Multimodal SFT Pipeline (Hybrid)",
    "tags": ["multimodal", "sft", "vision-language", "multi-image"],
    "description": (
        "Image+text SFT: collect paired image+text -> align by image_id -> "
        "aspect-ratio + NSFW filter -> CLIP score + conversation-quality "
        "score -> multi-image conversation format -> ShareGPT + Parquet "
        "export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "image_sources": {"type": "array<object>", "required": True},
            "text_sources": {"type": "array<object>", "required": True},
            "min_clip": {"type": "float", "default": 0.25,
                         "min": 0.0, "max": 1.0},
            "max_images_per_turn": {"type": "int", "default": 4,
                                     "min": 1, "max": 16},
            "allowed_aspect_ratios": {"type": "array<string>",
                                       "default": ["1:1", "4:3", "3:4",
                                                    "16:9", "9:16"]},
            "oss_bucket": {"type": "string", "default": "mm-sft"},
        },
        outputs=["sharegpt.json", "parquet/*.parquet",
                 "conv_quality_report.json", "stats.json"],
        steps=[
            {"id": "ic", "name": "Image Collect",
             "operator": "collection.image_source",
             "config": {"sources": "$inputs.image_sources"}},
            {"id": "tc", "name": "Text Collect",
             "operator": "collection.text_source",
             "config": {"sources": "$inputs.text_sources"}},
            {"id": "al", "name": "Image-Text Align",
             "operator": "dataset.align_mm",
             "config": {"key": "image_id"}},
            {"id": "ar", "name": "Aspect Ratio Filter",
             "operator": "cleaning.aspect_ratio_filter",
             "config": {"allowed": "$inputs.allowed_aspect_ratios"}},
            {"id": "cln", "name": "Quality Filter (NSFW/blur)",
             "operator": "cleaning.quality_filter"},
            {"id": "sc", "name": "CLIP + Conv-Quality Score",
             "operator": "scoring.multimodal_score",
             "config": {"score_keys": ["clip", "conv_coherence",
                                        "entity_coverage"]}},
            {"id": "al2", "name": "CLIP Threshold",
             "operator": "scoring.clip_filter",
             "config": {"min": "$inputs.min_clip"}},
            {"id": "fmt", "name": "Multi-Image Conversation Format",
             "operator": "format.sharegpt_multi_image_export",
             "config": {"max_images": "$inputs.max_images_per_turn"}},
            {"id": "pq", "name": "Parquet Shards",
             "operator": "export.to_parquet"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["fmt", "pq"]},
        ],
        metrics=["images", "texts", "aligned_pairs",
                 "after_clip", "sharegpt_rows",
                 "avg_conv_quality", "duration_seconds"],
    ),
    "nodes": [_n("ic", "image_collect", "collection"),
              _n("tc", "text_collect", "collection"),
              _n("al", "align_mm", "dataset", "ic", "tc"),
              _n("ar", "aspect_filter", "cleaning", "al"),
              _n("cln", "quality_filter", "cleaning", "ar"),
              _n("sc", "multimodal_score", "scoring", "cln"),
              _n("al2", "clip_filter", "scoring", "sc"),
              _n("fm", "sharegpt_multi_image", "export", "al2"),
              _n("pq", "parquet_shards", "export", "al2"),
              _n("up", "oss_upload", "export", "fm", "pq")],
}