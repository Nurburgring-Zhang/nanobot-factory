"""P3-6.5-W2: Hybrid Business Pipeline — SFT Image Classification.

Complete SFT image classification pipeline with prelabel, multi-reviewer
consensus, composite scoring, and Alpaca export.

Category: pipeline
Stage coverage: collection -> cleaning -> prelabel -> annotation ->
consensus -> scoring -> export

Improvements over ``tpl-biz-pipe-002``:
  * Confidence-aware consensus (weighted by reviewer confidence)
  * Optional stratified split (train/val/test)
  * Direct Alpaca JSONL with field_map support
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h02",
    "category": "pipeline",
    "name": "SFT Image Classification Pipeline (Hybrid)",
    "tags": ["sft", "image-classification", "alpaca", "consensus"],
    "description": (
        "SFT pipeline for image classification: collect -> clean -> "
        "CLIP zero-shot prelabel -> human annotate (multi-reviewer) -> "
        "weighted consensus -> aesthetic+CLIP score -> Alpaca export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "sources": {"type": "array<object>", "required": True},
            "labels": {"type": "array<string>", "required": True},
            "reviewers": {"type": "int", "default": 2, "min": 1, "max": 5},
            "min_agreement": {"type": "float", "default": 0.6,
                              "min": 0.0, "max": 1.0,
                              "description": "Minimum weighted agreement"},
            "stratify_split": {"type": "boolean", "default": True,
                                "description": "Stratify by label"},
            "oss_bucket": {"type": "string", "default": "sft-cls"},
        },
        outputs=["alpaca.jsonl", "stats.json", "split_manifest.json"],
        steps=[
            {"id": "col", "name": "Collect",
             "operator": "collection.multi_source",
             "config": {"sources": "$inputs.sources"}},
            {"id": "cln", "name": "Clean (blur/NSFW)",
             "operator": "cleaning.quality_filter"},
            {"id": "pl", "name": "Pre-label (CLIP zero-shot)",
             "operator": "annotation.prelabel_classify",
             "config": {"labels": "$inputs.labels"}},
            {"id": "an", "name": "Human Annotate (multi-reviewer)",
             "operator": "annotation.classify",
             "config": {"labels": "$inputs.labels",
                        "reviewers": "$inputs.reviewers"}},
            {"id": "ag", "name": "Weighted Consensus",
             "operator": "annotation.consensus",
             "config": {"min_agreement": "$inputs.min_agreement",
                        "weighted": True}},
            {"id": "sc", "name": "Composite Score",
             "operator": "scoring.composite",
             "config": {"score_keys": ["clip", "aesthetic"]}},
            {"id": "sp", "name": "Train/Val/Test Split",
             "operator": "data.split",
             "config": {"ratio": [0.8, 0.1, 0.1],
                        "stratify": "label" if "$inputs.stratify_split"
                                     else None}},
            {"id": "alp", "name": "Alpaca Export",
             "operator": "format.alpaca_export"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["collected", "labeled", "consensus_kept",
                 "alpaca_rows", "split_counts", "duration_seconds"],
    ),
    "nodes": [_n("col", "multi_source_collect", "collection"),
              _n("cln", "quality_filter", "cleaning", "col"),
              _n("pl", "prelabel_classify", "prelabel", "cln"),
              _n("an", "classify_annotate", "annotation", "pl"),
              _n("ag", "consensus", "consensus", "an"),
              _n("sc", "composite_score", "scoring", "ag"),
              _n("sp", "split", "data", "sc"),
              _n("alp", "alpaca_export", "export", "sp"),
              _n("up", "oss_upload", "export", "alp")],
}