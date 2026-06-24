"""Filter template: Domain balanced (领域平衡).

Pipeline:
  1.  load          - 读 jsonl
  2.  domain        - 域分类器 (基于关键词/embedding/LLM)
  3.  quota         - 按目标域配额采样
  4.  long_tail     - 长尾域可选补齐
  5.  write         - 输出 domain_balanced.jsonl
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-flt-004",
    "name": "Domain Balanced (领域平衡)",
    "category": "filter",
    "description": (
        "按域 (domain) 分类后按配额平衡采样, 支持 embedding/"
        "LLM 自动分类, 长尾域可补齐。"
    ),
    "tags": ["filter", "domain", "balanced"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "domain_field": {"type": "string", "default": "domain"},
        "auto_classify": {"type": "bool", "default": False},
        "classifier": {"type": "string", "default": "embedding",
                        "enum": ["keyword", "embedding",
                                  "llm", "explicit"]},
        "target_quotas": {"type": "object", "default": {
            "code": 1000, "math": 1000, "general": 2000,
            "creative": 1000, "multilingual": 1000,
        }},
        "random_seed": {"type": "int", "default": 42},
        "oss_bucket": {"type": "string", "default": "filtered"},
    },
    "outputs": ["domain_balanced.jsonl", "stats.json"],
    "steps": [
        {"id": "ld", "name": "Load",
         "operator": "filter.load",
         "config": {"source": "$inputs.input_manifest"}},
        {"id": "cl", "name": "Domain Classify",
         "operator": "filter.domain_classify",
         "config": {"auto_classify": "$inputs.auto_classify",
                    "classifier": "$inputs.classifier",
                    "field": "$inputs.domain_field"}},
        {"id": "qt", "name": "Compute Quotas",
         "operator": "filter.domain_quota",
         "config": {"target_quotas": "$inputs.target_quotas",
                    "long_tail_oversample": True}},
        {"id": "sp", "name": "Sample",
         "operator": "filter.stratified_sample",
         "config": {"seed": "$inputs.random_seed"}},
        {"id": "wr", "name": "Write",
         "operator": "filter.write",
         "config": {"format": "jsonl",
                    "bucket": "$inputs.oss_bucket",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total",
                "per_domain_counts", "duration_seconds"],
}


__all__ = ["TEMPLATE"]