"""P3-6.5-W2: Hybrid Business Pipeline — Image Pretrain Collection.

End-to-end image pretraining data pipeline that combines multi-source
collection, perceptual-hash deduplication, quality + NSFW filtering,
aesthetic + CLIP scoring, top-K selection, and Parquet export with OSS
upload.

Category: pipeline
Stage coverage: collection -> cleaning -> scoring -> filter -> export

This template complements the legacy ``tpl-biz-pipe-001`` by:
  * Adding pHash hash column for audit
  * Using Parquet row-group + zstd compression by default
  * Wiring CLIP score >= 0.20 minimum as a quality gate
  * Auto-generating a dataset card from the run metrics
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h01",
    "category": "pipeline",
    "name": "Image Pretrain Collection Pipeline",
    "tags": ["pretrain", "image", "laion", "hybrid", "multisource"],
    "description": (
        "End-to-end image pretrain data collection: multi-source crawl -> "
        "pHash dedup -> blur/NSFW/OCR filter -> aesthetic+CLIP scoring -> "
        "top-K selection -> Parquet export with dataset card."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "sources": {"type": "array<object>", "required": True,
                         "description": "[{type: 'hf'|'web'|'oss', ...}]"},
            "target_count": {"type": "int", "default": 1000000,
                             "description": "Number of images to keep"},
            "min_aesthetic": {"type": "float", "default": 5.0,
                              "min": 0.0, "max": 10.0},
            "min_clip": {"type": "float", "default": 0.20,
                         "min": 0.0, "max": 1.0},
            "compression": {"type": "string", "default": "zstd",
                            "enum": ["snappy", "gzip", "zstd", "lz4"]},
            "oss_bucket": {"type": "string", "default": "pretrain-img"},
            "auto_card": {"type": "boolean", "default": True,
                          "description": "Auto-generate dataset card"},
        },
        outputs=["manifest.jsonl", "parquet/*.parquet",
                 "stats.json", "card.md"],
        steps=[
            {"id": "col", "name": "Multi-source Collect",
             "operator": "collection.multi_source",
             "config": {"sources": "$inputs.sources"}},
            {"id": "ph", "name": "pHash Compute",
             "operator": "cleaning.phash_compute"},
            {"id": "dd", "name": "pHash Dedup",
             "operator": "cleaning.phash_dedup",
             "config": {"threshold": 6}},
            {"id": "flt", "name": "Quality + Safety Filter",
             "operator": "cleaning.quality_filter",
             "config": {"checks": ["blur", "nsfw", "ocr_text"]}},
            {"id": "asc", "name": "Aesthetic + CLIP Score",
             "operator": "scoring.composite",
             "config": {"score_keys": ["aesthetic", "clip"]}},
            {"id": "tk", "name": "Top-K Selection",
             "operator": "dataset.topk",
             "config": {"k": "$inputs.target_count",
                        "min_aesthetic": "$inputs.min_aesthetic",
                        "min_clip": "$inputs.min_clip"}},
            {"id": "wr", "name": "Parquet Export",
             "operator": "export.to_parquet",
             "config": {"compression": "$inputs.compression",
                        "shard_size_mb": 500}},
            {"id": "cd", "name": "Dataset Card",
             "operator": "docs.render_card",
             "config": {"enabled": "$inputs.auto_card"}},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["wr", "cd"]},
        ],
        metrics=["collected", "after_dedup", "after_filter",
                 "scored", "kept", "shards", "duration_seconds"],
    ),
    "nodes": [_n("col", "multi_source_collect", "collection"),
              _n("ph", "phash_compute", "cleaning", "col"),
              _n("dd", "phash_dedup", "cleaning", "ph"),
              _n("flt", "quality_filter", "cleaning", "dd"),
              _n("asc", "composite_score", "scoring", "flt"),
              _n("tk", "topk_select", "dataset", "asc"),
              _n("wr", "parquet_export", "export", "tk"),
              _n("cd", "render_card", "docs", "wr"),
              _n("up", "oss_upload", "export", "cd", retry_max=2)],
}