"""P3-6.5-W2: Hybrid Business Pipeline — RLHF Reward Model.

Reward model training data pipeline with K-response sampling, multi-rater
human ranking, Bradley-Terry conversion to pairwise, and Parquet export.

Category: pipeline
Stage coverage: dataset -> generation -> annotation -> conversion -> export

Improvements over ``tpl-biz-pipe-007``:
  * Inter-rater agreement metrics (Kendall's W)
  * Disagreement resolution (3rd adjudicator on disputed ranks)
  * Pairwise export format compatible with HF trl RewardTrainer
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h07",
    "category": "pipeline",
    "name": "RLHF Reward Model Pipeline (Hybrid)",
    "tags": ["rlhf", "reward-model", "ranking", "bradley-terry", "kendall"],
    "description": (
        "Reward-model training data: load prompts -> sample K responses "
        "(diverse) -> multi-rater human ranking (with adjudicator on "
        "disagreement) -> Bradley-Terry pairwise conversion -> "
        "Parquet + HF trl-compatible export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "prompt_source": {"type": "object", "required": True},
            "k": {"type": "int", "default": 4, "min": 2, "max": 8},
            "rankers_per_group": {"type": "int", "default": 3},
            "enable_adjudicator": {"type": "boolean", "default": True,
                                    "description": "Use 3rd rater to "
                                                   "break ties"},
            "kendall_threshold": {"type": "float", "default": 0.4,
                                   "min": 0.0, "max": 1.0,
                                   "description": "Min Kendall's W to "
                                                  "skip adjudication"},
            "oss_bucket": {"type": "string", "default": "rm-data"},
        },
        outputs=["rm_ranking.jsonl", "rm_pairwise.jsonl",
                 "kendall_report.json", "stats.json"],
        steps=[
            {"id": "ld", "name": "Load Prompts",
             "operator": "dataset.load_prompts"},
            {"id": "gen", "name": "Sample K Responses (diverse)",
             "operator": "generation.sample",
             "config": {"k": "$inputs.k", "diversity": True}},
            {"id": "rk", "name": "Multi-Rater Ranking",
             "operator": "annotation.ranking",
             "config": {"rankers": "$inputs.rankers_per_group"}},
            {"id": "kw", "name": "Kendall's W Agreement",
             "operator": "analysis.kendall_w"},
            {"id": "adj", "name": "Adjudicator (optional)",
             "operator": "annotation.adjudicator",
             "config": {"enabled": "$inputs.enable_adjudicator",
                        "kendall_threshold":
                            "$inputs.kendall_threshold"}},
            {"id": "bt", "name": "Bradley-Terry Pairs",
             "operator": "dataset.bradley_terry"},
            {"id": "wr", "name": "Pairwise Export (HF trl)",
             "operator": "export.write_pairwise_trl"},
            {"id": "pq", "name": "Parquet Export",
             "operator": "export.to_parquet"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["wr", "pq"]},
        ],
        metrics=["prompts", "rankings", "disputes_resolved",
                 "pairwise_rows", "avg_kendall_w",
                 "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_prompts", "collection"),
              _n("gn", "sample_responses", "generation", "ld"),
              _n("rk", "ranking_annotate", "annotation", "gn"),
              _n("kw", "kendall_w", "analysis", "rk"),
              _n("adj", "adjudicator", "annotation", "kw"),
              _n("bt", "bradley_terry", "dataset", "adj"),
              _n("wr", "write_pairwise_trl", "export", "bt"),
              _n("pq", "parquet_export", "export", "bt"),
              _n("up", "oss_upload", "export", "wr", "pq")],
}