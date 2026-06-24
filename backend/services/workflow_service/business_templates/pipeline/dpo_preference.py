"""P3-6.5-W2: Hybrid Business Pipeline — DPO Preference.

DPO preference data pipeline with prompt collection, K-response
sampling, reward scoring, chosen/rejected pairing with margin filter,
DPO JSONL export.

Category: pipeline
Stage coverage: dataset -> generation -> scoring -> pairing -> export

Improvements over ``tpl-biz-pipe-006``:
  * Diversity-aware sampling (rejection sampling for diverse K)
  * Margin distribution stats (gamma, p25/p50/p75)
  * Safety tag (drop unsafe responses before pairing)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h06",
    "category": "pipeline",
    "name": "DPO Preference Pipeline (Hybrid)",
    "tags": ["dpo", "preference", "rlhf", "pair", "diversity"],
    "description": (
        "DPO data pipeline: load prompts -> K-response diversity-aware "
        "sample -> safety filter -> reward score -> chosen/rejected pair "
        "with margin -> DPO JSONL export with margin distribution stats."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "prompt_source": {"type": "object", "required": True},
            "k_responses": {"type": "int", "default": 4,
                            "min": 2, "max": 16},
            "temperatures": {"type": "array<float>",
                              "default": [0.7, 0.9, 1.1, 1.3]},
            "reward_model": {"type": "string", "default": "skywork-rm"},
            "margin": {"type": "float", "default": 0.5,
                       "description": "Min chosen-rejected reward gap"},
            "enable_safety_filter": {"type": "boolean", "default": True},
            "safety_model": {"type": "string", "default": "llama-guard"},
            "oss_bucket": {"type": "string", "default": "dpo"},
        },
        outputs=["dpo.jsonl", "margin_distribution.json",
                 "safety_report.json", "stats.json"],
        steps=[
            {"id": "ld", "name": "Load Prompts",
             "operator": "dataset.load_prompts",
             "config": {"source": "$inputs.prompt_source"}},
            {"id": "gen", "name": "K-Response Diversity Sample",
             "operator": "generation.sample",
             "config": {"k": "$inputs.k_responses",
                        "temperatures": "$inputs.temperatures",
                        "diversity": "embedding_min_dist"}},
            {"id": "sf", "name": "Safety Filter",
             "operator": "cleaning.safety_filter",
             "config": {"enabled": "$inputs.enable_safety_filter",
                        "model": "$inputs.safety_model"}},
            {"id": "rm", "name": "Reward Score",
             "operator": "scoring.reward",
             "config": {"model": "$inputs.reward_model"}},
            {"id": "pair", "name": "Pair Chosen/Rejected",
             "operator": "dataset.pair_preference",
             "config": {"margin": "$inputs.margin"}},
            {"id": "md", "name": "Margin Distribution Stats",
             "operator": "analysis.margin_distribution",
             "config": {"percentiles": [25, 50, 75, 90]}},
            {"id": "wr", "name": "DPO JSONL Export",
             "operator": "export.write_dpo"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["wr", "md"]},
        ],
        metrics=["prompts", "responses", "after_safety",
                 "pairs_kept", "avg_margin", "p50_margin",
                 "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_prompts", "collection"),
              _n("gn", "sample_responses", "generation", "ld"),
              _n("sf", "safety_filter", "cleaning", "gn"),
              _n("rm", "reward_score", "scoring", "sf"),
              _n("pr", "pair_preference", "dataset", "rm"),
              _n("md", "margin_distribution", "analysis", "pr"),
              _n("wr", "write_dpo", "export", "pr"),
              _n("up", "oss_upload", "export", "wr", "md")],
}