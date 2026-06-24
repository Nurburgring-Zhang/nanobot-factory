"""P3-6.5-W2: Hybrid Business Pipeline — SFT Text NER.

Text NER SFT pipeline with sentence splitting, BIO prelabel, multi-pass
human annotation, schema validation, and Alpaca + BIO format export.

Category: pipeline
Stage coverage: collection -> preprocessing -> prelabel -> annotation ->
validation -> export

Improvements over ``tpl-biz-pipe-005``:
  * Active learning loop (uncertain samples prioritized for re-annotation)
  * Token-level span validation (BIO schema strict)
  * Multi-language support (zh/en/ja)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h05",
    "category": "pipeline",
    "name": "SFT Text NER Pipeline (Hybrid)",
    "tags": ["sft", "text-ner", "token-classification", "multilang", "active-learning"],
    "description": (
        "Text NER SFT: text crawl -> sentence split -> BIO prelabel -> "
        "uncertainty-based active learning queue -> human annotate -> "
        "BIO schema strict validate -> Alpaca + BIO export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "sources": {"type": "array<object>", "required": True},
            "entity_types": {"type": "array<string>", "required": True},
            "language": {"type": "string", "default": "zh",
                         "enum": ["zh", "en", "ja"]},
            "model": {"type": "string",
                      "default": "bert-base-ner-multilang"},
            "uncertainty_threshold": {"type": "float", "default": 0.6,
                                       "min": 0.0, "max": 1.0},
            "max_active_iterations": {"type": "int", "default": 3},
            "oss_bucket": {"type": "string", "default": "sft-ner"},
        },
        outputs=["alpaca.jsonl", "bio.jsonl", "stats.json",
                 "active_learning_log.json"],
        steps=[
            {"id": "col", "name": "Text Collect",
             "operator": "collection.text_source"},
            {"id": "sp", "name": "Sentence Split",
             "operator": "preprocessing.sentence_split",
             "config": {"language": "$inputs.language"}},
            {"id": "pl", "name": "BIO Prelabel",
             "operator": "annotation.bio_prelabel",
             "config": {"entity_types": "$inputs.entity_types",
                        "model": "$inputs.model",
                        "language": "$inputs.language"}},
            {"id": "al", "name": "Active Learning Queue",
             "operator": "annotation.active_learning_queue",
             "config": {"uncertainty_threshold":
                            "$inputs.uncertainty_threshold",
                        "max_iterations":
                            "$inputs.max_active_iterations"}},
            {"id": "an", "name": "Human BIO Annotate",
             "operator": "annotation.bio_annotate",
             "config": {"entity_types": "$inputs.entity_types"}},
            {"id": "vl", "name": "BIO Strict Validate",
             "operator": "annotation.bio_validate",
             "config": {"strict": True}},
            {"id": "wr", "name": "Alpaca Export",
             "operator": "format.alpaca_ner_export"},
            {"id": "bj", "name": "BIO JSONL Export",
             "operator": "export.write_bio"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["sentences", "tokens", "entities",
                 "alpaca_rows", "bio_rows",
                 "active_iterations", "duration_seconds"],
    ),
    "nodes": [_n("col", "text_collect", "collection"),
              _n("sp", "sentence_split", "preprocessing", "col"),
              _n("pl", "bio_prelabel", "prelabel", "sp"),
              _n("al", "active_learning", "annotation", "pl"),
              _n("an", "bio_annotate", "annotation", "al"),
              _n("vl", "bio_validate", "export", "an"),
              _n("wr", "alpaca_export", "export", "vl"),
              _n("bj", "bio_export", "export", "vl"),
              _n("up", "oss_upload", "export", "wr", "bj")],
}