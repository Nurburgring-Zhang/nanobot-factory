"""P3-6.5-W2: Hybrid Business Pipeline — Video Edit SFT.

Video edit instruction SFT pipeline with source/target pair loading,
keyframe extraction, VLM-based diff caption (edit description), human
review, and Alpaca export.

Category: pipeline
Stage coverage: dataset -> preprocessing -> generation -> review -> export

Improvements over ``tpl-biz-pipe-009``:
  * Edit-type classification (replace/insert/remove/style/...)
  * Temporal edit localization (start/end timestamps)
  * Negative-edit sampling for contrastive training
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h09",
    "category": "pipeline",
    "name": "Video Edit SFT Pipeline (Hybrid)",
    "tags": ["video-edit", "sft", "instruction", "edit-classification"],
    "description": (
        "Video-edit instruction SFT: load source/target pairs -> "
        "keyframe extract -> diff caption with edit-type classification "
        "(replace/insert/remove/style/temporal) -> temporal localization -> "
        "human review -> Alpaca export (with negative edits)."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "source_clips": {"type": "array<object>", "required": True},
            "target_clips": {"type": "array<object>", "required": True},
            "edit_model": {"type": "string",
                            "default": "videocap-7b"},
            "edit_types": {"type": "array<string>",
                            "default": ["replace", "insert", "remove",
                                        "style", "temporal"]},
            "include_negative_edits": {"type": "boolean", "default": True},
            "negative_ratio": {"type": "float", "default": 0.2,
                               "min": 0.0, "max": 1.0},
            "oss_bucket": {"type": "string", "default": "videoedit-sft"},
        },
        outputs=["alpaca.jsonl", "alpaca_negatives.jsonl",
                 "edit_type_distribution.json", "stats.json"],
        steps=[
            {"id": "ld", "name": "Load Source/Target Pairs",
             "operator": "dataset.load_pairs",
             "config": {"source": "$inputs.source_clips",
                        "target": "$inputs.target_clips"}},
            {"id": "kf", "name": "Key-Frame Extract",
             "operator": "preprocessing.keyframe_sample"},
            {"id": "cap", "name": "Diff Caption (VLM)",
             "operator": "annotation.vlm_diff_caption",
             "config": {"model": "$inputs.edit_model"}},
            {"id": "et", "name": "Edit-Type Classify",
             "operator": "annotation.edit_type_classify",
             "config": {"types": "$inputs.edit_types"}},
            {"id": "tl", "name": "Temporal Localization",
             "operator": "annotation.temporal_localize"},
            {"id": "neg", "name": "Build Negative Edits",
             "operator": "dataset.build_negatives",
             "config": {"enabled": "$inputs.include_negative_edits",
                        "ratio": "$inputs.negative_ratio"}},
            {"id": "rv", "name": "Human Review",
             "operator": "annotation.review"},
            {"id": "wr", "name": "Alpaca Export",
             "operator": "format.alpaca_export"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["pairs", "captions", "edit_type_counts",
                 "temporal_spans", "negatives",
                 "alpaca_rows", "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_pairs", "collection"),
              _n("kf", "keyframe_sample", "preprocessing", "ld"),
              _n("cp", "vlm_diff_caption", "annotation", "kf"),
              _n("et", "edit_type_classify", "annotation", "cp"),
              _n("tl", "temporal_localize", "annotation", "et"),
              _n("ng", "build_negatives", "dataset", "tl"),
              _n("rv", "review", "review", "ng"),
              _n("wr", "alpaca_export", "export", "rv"),
              _n("up", "oss_upload", "export", "wr")],
}