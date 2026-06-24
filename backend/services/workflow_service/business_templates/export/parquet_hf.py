"""P3-6-W1: business export template — HuggingFace Parquet export.

Pipeline (HF datasets-compatible Parquet shards):
  1.  load           - 加载 dataset
  2.  pii_redact     - 文本字段 PII 脱敏 (email/phone/id_card)
  3.  schema_norm    - 归一化为 HF datasets.Dataset schema
  4.  shard          - 按 shard_size_mb 切分
  5.  parquet_write  - 写出 Parquet shards (snappy/gzip/zstd/lz4)
  6.  info_json      - 生成 dataset_info.json (features/stats/splits)
  7.  card_render    - 渲染 README.md (HF datasets card 格式)
  8.  manifest       - 写 manifest.json (sha256 + size + row_count)
  9.  oss_upload     - 上传到 hf-parquet bucket

vs basic_templates/export.py::tpl-biz-exp-005: 本模板加入 PII redact +
  manifest sha256 + dataset_info.json + HF 标准 README card。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-exp-005",
    "name": "HuggingFace Parquet Export (商业级)",
    "category": "export",
    "description": (
        "HF datasets 兼容 Parquet 分片导出:PII 脱敏 + schema 归一化 + "
        "shard 切分 + parquet 写出 + dataset_info.json + HF README。"
    ),
    "tags": ["parquet", "huggingface", "datasets", "arrow",
             "shard", "export", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "dataset_id": {"type": "string", "required": True},
        "shard_size_mb": {"type": "int", "default": 500, "min": 1},
        "compression": {"type": "string", "default": "zstd",
                        "enum": ["snappy", "gzip", "zstd", "lz4"]},
        "row_group_size": {"type": "int", "default": 10000},
        "redact_pii": {"type": "boolean", "default": True},
        "write_card": {"type": "boolean", "default": True},
        "write_manifest": {"type": "boolean", "default": True},
        "hash_algorithm": {"type": "string", "default": "sha256",
                            "enum": ["sha256", "md5"]},
        "oss_bucket": {"type": "string", "default": "hf-parquet"},
        "oss_key_prefix": {"type": "string", "default": "hf_parquet/"},
    },
    "outputs": [
        "data/train-00000-of-*.parquet",
        "data/validation-00000-of-*.parquet",
        "dataset_info.json",
        "README.md",
        "manifest.json",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Dataset",
         "operator": "dataset.load",
         "config": {"dataset_id": "$inputs.dataset_id"}},
        {"id": "pi", "name": "PII Redact",
         "operator": "cleaning.pii_redact",
         "config": {"enabled": "$inputs.redact_pii",
                    "patterns": ["email", "phone", "id_card"]}},
        {"id": "nm", "name": "HF Schema Normalize",
         "operator": "format.hf_schema_normalize",
         "config": {"target": "datasets.Dataset"}},
        {"id": "sp", "name": "Train/Val Split",
         "operator": "data.split",
         "config": {"ratio": [0.9, 0.1]}},
        {"id": "sh", "name": "Shard by Size",
         "operator": "data.shard_by_size",
         "config": {"shard_size_mb": "$inputs.shard_size_mb"}},
        {"id": "pq", "name": "Write Parquet Shards",
         "operator": "export.to_parquet",
         "config": {"compression": "$inputs.compression",
                    "row_group_size": "$inputs.row_group_size"}},
        {"id": "if", "name": "Write dataset_info.json",
         "operator": "docs.dataset_info",
         "config": {"enabled": True}},
        {"id": "cd", "name": "Render HF README Card",
         "operator": "docs.render_card",
         "config": {"enabled": "$inputs.write_card",
                    "format": "hf_dataset_card"}},
        {"id": "mn", "name": "Write Manifest",
         "operator": "export.write_manifest",
         "config": {"enabled": "$inputs.write_manifest",
                    "hash": "$inputs.hash_algorithm"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"},
         "retry_max": 2},
    ],
    "metrics": [
        "rows_total", "rows_after_pii", "shards_count",
        "bytes_total", "compression_ratio",
        "pii_redactions", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]