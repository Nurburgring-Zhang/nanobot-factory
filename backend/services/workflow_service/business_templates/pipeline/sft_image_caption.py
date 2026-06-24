"""P3-6.5-W2: Hybrid Business Pipeline — SFT Image Caption.

SFT image captioning pipeline with VLM dense captioning, human review,
and ShareGPT export.

Category: pipeline
Stage coverage: collection -> cleaning -> generation -> review -> export

Improvements over ``tpl-biz-pipe-003``:
  * Per-image caption length cap (configurable)
  * Negative-example filter (VLM confidence + reviewer rating)
  * Optional negative samples for contrastive training
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h03",
    "category": "pipeline",
    "name": "SFT Image Caption Pipeline (Hybrid)",
    "tags": ["sft", "image-caption", "llava", "sharegpt", "dense"],
    "description": (
        "SFT image-caption pipeline: collect -> clean -> VLM dense caption "
        "(per-region) -> human review (rating + reject) -> ShareGPT export "
        "with optional negative samples."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "sources": {"type": "array<object>", "required": True},
            "caption_model": {"type": "string",
                              "default": "llava-1.5-13b"},
            "max_caption_tokens": {"type": "int", "default": 256,
                                    "min": 32, "max": 2048},
            "review_threshold": {"type": "float", "default": 0.7,
                                  "min": 0.0, "max": 1.0},
            "include_negatives": {"type": "boolean", "default": False,
                                   "description": "Include rejected "
                                                  "samples as negative"},
            "oss_bucket": {"type": "string", "default": "sft-cap"},
        },
        outputs=["sharegpt.json", "negatives.jsonl",
                 "stats.json", "card.md"],
        steps=[
            {"id": "col", "name": "Collect",
             "operator": "collection.multi_source"},
            {"id": "cln", "name": "Clean",
             "operator": "cleaning.quality_filter"},
            {"id": "cg", "name": "VLM Dense Caption",
             "operator": "annotation.vlm_caption",
             "config": {"model": "$inputs.caption_model",
                        "max_tokens": "$inputs.max_caption_tokens",
                        "dense": True}},
            {"id": "rv", "name": "Human Review",
             "operator": "annotation.review",
             "config": {"approve_threshold": "$inputs.review_threshold",
                        "fields": ["caption", "quality", "relevance"]}},
            {"id": "neg", "name": "Build Negatives",
             "operator": "dataset.build_negatives",
             "config": {"enabled": "$inputs.include_negatives"}},
            {"id": "wr", "name": "ShareGPT Export",
             "operator": "format.sharegpt_export"},
            {"id": "cd", "name": "Dataset Card",
             "operator": "docs.render_card"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["wr", "cd"]},
        ],
        metrics=["collected", "captioned", "approved",
                 "rejected", "negatives", "duration_seconds"],
    ),
    "nodes": [_n("col", "multi_source_collect", "collection"),
              _n("cln", "quality_filter", "cleaning", "col"),
              _n("cg", "vlm_dense_caption", "annotation", "cln"),
              _n("rv", "review", "review", "cg"),
              _n("neg", "build_negatives", "dataset", "rv"),
              _n("wr", "sharegpt_export", "export", "neg"),
              _n("cd", "render_card", "docs", "wr"),
              _n("up", "oss_upload", "export", "cd")],
}