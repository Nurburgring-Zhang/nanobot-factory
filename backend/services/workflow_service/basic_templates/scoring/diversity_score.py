"""Scoring template: Diversity score (多样性评分).

Pipeline:
  1.  cluster       - 嵌入聚类 (cosine / L2)
  2.  intra_diver   - 类内多样性 (平均 pairwise 距离)
  3.  inter_diver   - 类间多样性 (centroid 距离)
  4.  coverage      - 嵌入空间覆盖率 (Vendi / KNN density)
  5.  composite     - 加权综合
  6.  write         - 写回 dataset-level 多样性分数
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-scr-005",
    "name": "Diversity Score (多样性评分)",
    "category": "scoring",
    "description": (
        "嵌入聚类 + 类内/类间多样性 + 空间覆盖率 (Vendi/KNN), "
        "输出 dataset-level 多样性综合分。"
    ),
    "tags": ["diversity", "scoring", "embedding", "vendi"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "embed_field": {"type": "string", "default": "embedding"},
        "n_clusters": {"type": "int", "default": 100},
        "cluster_algo": {"type": "string", "default": "kmeans",
                          "enum": ["kmeans", "leiden", "hdbscan"]},
        "intra_weight": {"type": "float", "default": 0.4},
        "inter_weight": {"type": "float", "default": 0.3},
        "coverage_weight": {"type": "float", "default": 0.3},
        "oss_bucket": {"type": "string", "default": "scores"},
    },
    "outputs": ["diversity.json", "per_cluster.json", "stats.json"],
    "steps": [
        {"id": "cl", "name": "Cluster",
         "operator": "vector.cluster",
         "config": {"algo": "$inputs.cluster_algo",
                    "n_clusters": "$inputs.n_clusters",
                    "field": "$inputs.embed_field"}},
        {"id": "intra", "name": "Intra-cluster Diversity",
         "operator": "diversity.intra",
         "config": {"metric": "cosine",
                    "per_cluster": True}},
        {"id": "inter", "name": "Inter-cluster Diversity",
         "operator": "diversity.inter",
         "config": {"metric": "centroid_cosine"}},
        {"id": "cov", "name": "Coverage (Vendi)",
         "operator": "diversity.vendi",
         "config": {"order": 1, "perplexity": True}},
        {"id": "comp", "name": "Composite",
         "operator": "scoring.weighted_combine",
         "config": {"formula": "intra*$intra_weight+inter*$inter_weight+coverage*$coverage_weight",
                    "intra_weight": "$inputs.intra_weight",
                    "inter_weight": "$inputs.inter_weight",
                    "coverage_weight": "$inputs.coverage_weight",
                    "output_field": "diversity_score"}},
        {"id": "wr", "name": "Write",
         "operator": "scoring.write",
         "config": {"format": "json",
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["n_clusters", "intra_mean",
                "inter_mean", "vendi_score",
                "diversity_score", "duration_seconds"],
}


__all__ = ["TEMPLATE"]