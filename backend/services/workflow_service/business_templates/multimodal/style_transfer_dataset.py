"""P3-6.5-W2: Hybrid Multimodal — Style Transfer Dataset.

Style transfer dataset pipeline: collect content + style images ->
style embedding -> paired train data (content|content+style) ->
Alpaca-style instruction export with style category tags.

Category: multimodal
Improvements over ``tpl-biz-mm-004``:
  * Style category taxonomy (oil/watercolor/sketch/anime/...)
  * Style intensity control (weak/medium/strong)
  * Per-style negative samples (style failure cases)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-mm-h04",
    "category": "multimodal",
    "name": "Style Transfer Dataset Pipeline (Hybrid)",
    "tags": ["style", "transfer", "aesthetic", "category-taxonomy"],
    "description": (
        "Style transfer dataset: collect content + style images -> "
        "style category tag (oil/watercolor/sketch/anime/...) -> "
        "style embedding -> intensity-tagged pairs (content|content+style) "
        "-> Alpaca-style instruction export with negative samples."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "content_sources": {"type": "array<object>", "required": True},
            "style_sources": {"type": "array<object>", "required": True},
            "style_model": {"type": "string",
                              "default": "vit-style-encoder"},
            "style_categories": {"type": "array<string>",
                                  "default": ["oil", "watercolor",
                                                "sketch", "anime",
                                                "pixel", "ink"]},
            "min_style_score": {"type": "float", "default": 0.6,
                                 "min": 0.0, "max": 1.0},
            "include_negatives": {"type": "boolean", "default": True},
            "oss_bucket": {"type": "string", "default": "style-data"},
        },
        outputs=["alpaca.jsonl", "pairs.jsonl", "negatives.jsonl",
                 "stats.json"],
        steps=[
            {"id": "ic", "name": "Content Collect",
             "operator": "collection.image_source",
             "config": {"sources": "$inputs.content_sources"}},
            {"id": "sc", "name": "Style Collect + Category Tag",
             "operator": "collection.style_source",
             "config": {"sources": "$inputs.style_sources",
                        "categories": "$inputs.style_categories"}},
            {"id": "emb", "name": "Style Embedding",
             "operator": "scoring.style_embed",
             "config": {"model": "$inputs.style_model"}},
            {"id": "pr", "name": "Intensity-Tagged Pairs",
             "operator": "dataset.style_pair",
             "config": {"min_style_score": "$inputs.min_style_score",
                        "intensity_bins": ["weak", "medium", "strong"]}},
            {"id": "ng", "name": "Build Style Negatives",
             "operator": "dataset.build_style_negatives",
             "config": {"enabled": "$inputs.include_negatives"}},
            {"id": "wr", "name": "Alpaca Instruction Export",
             "operator": "format.alpaca_style_export"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["content", "styles", "by_category",
                 "pairs", "negatives", "alpaca_rows",
                 "duration_seconds"],
    ),
    "nodes": [_n("ic", "content_collect", "collection"),
              _n("sc", "style_collect", "collection"),
              _n("em", "style_embed", "scoring", "sc"),
              _n("pr", "style_pair", "dataset", "ic", "em"),
              _n("ng", "style_negatives", "dataset", "pr"),
              _n("wr", "alpaca_export", "export", "ng"),
              _n("up", "oss_upload", "export", "wr")],
}