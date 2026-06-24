"""Collection template: HuggingFace dataset download.

Pipeline:
  1. resolve      — 解析 repo_id / revision / subset / split
  2. snapshot     — huggingface_hub snapshot_download (流式 / 全量)
  3. verify       — 校验 parquet / arrow 完整性
  4. convert      — 统一转 Parquet, 写入 OSS
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-coll-004",
    "name": "HuggingFace Dataset Download (HF 数据集下载)",
    "category": "collection",
    "description": (
        "从 HuggingFace Hub 下载数据集, 校验完整性后转 Parquet, "
        "上传到对象存储。"
    ),
    "tags": ["huggingface", "dataset", "collection", "parquet"],
    "version": "1.0.0",
    "inputs": {
        "repo_id": {"type": "string", "required": True,
                     "description": "e.g. laion/laion2B-en-aesthetic"},
        "revision": {"type": "string", "default": "main"},
        "subsets": {"type": "array<string>", "default": []},
        "splits": {"type": "array<string>", "default": ["train"]},
        "max_rows": {"type": "int", "default": 0,
                      "description": "0 = 全部"},
        "oss_bucket": {"type": "string", "default": "raw-datasets"},
    },
    "outputs": ["manifest.json", "parquet/*.parquet"],
    "steps": [
        {"id": "resolve", "name": "Resolve",
         "operator": "hf.resolve",
         "config": {"repo_id": "$inputs.repo_id",
                    "revision": "$inputs.revision",
                    "repo_type": "dataset"}},
        {"id": "snapshot", "name": "Snapshot Download",
         "operator": "hf.snapshot_download",
         "config": {"repo_id": "$inputs.repo_id",
                    "repo_type": "dataset",
                    "allow_patterns": ["*.parquet", "*.arrow",
                                       "*.json", "*.jsonl"]}},
        {"id": "verify", "name": "Verify Integrity",
         "operator": "hf.verify",
         "config": {"checksum": True, "row_count": True}},
        {"id": "convert", "name": "Parquet Convert",
         "operator": "dataset.to_parquet",
         "config": {"compression": "zstd",
                    "row_group_size": 10000,
                    "max_rows": "$inputs.max_rows"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "collection/huggingface/",
                    "manifest": True}},
    ],
    "metrics": ["files_downloaded", "bytes_downloaded",
                "rows_kept", "duration_seconds"],
}


__all__ = ["TEMPLATE"]