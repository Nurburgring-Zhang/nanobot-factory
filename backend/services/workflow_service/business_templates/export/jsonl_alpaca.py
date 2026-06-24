"""P3-6-W1: business export template — Alpaca SFT JSONL.

Pipeline (chaining basic_templates cleaning + dataset operators):
  1.  load           - 从清洗后的 dataset 加载记录
  2.  clean_filter   - 过滤 NSFW / blur / OCR text-in-image
  3.  dedup          - pHash + CLIP embedding 双 dedup
  4.  field_map      - 映射到 Alpaca schema (instruction/input/output)
  5.  schema_check   - 校验 required fields 存在
  6.  jsonl_write    - 写 .jsonl (one record per line)
  7.  oss_upload     - 上传到 OSS sft-alpaca bucket

vs basic_templates/export.py::tpl-biz-exp-001 (5 steps): 本模板细化到 7 步,
  加入 NSFW + blur 清洗 + 双 dedup + 强 schema 校验,适合商业级 SFT 数据导出。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-exp-001",
    "name": "Alpaca SFT JSONL Export (商业级)",
    "category": "export",
    "description": (
        "串联 cleaning + dataset 双 dedup + Alpaca schema 强校验 + "
        "JSONL 写出 + OSS 上传,7 步 SFT 数据导出。"
    ),
    "tags": ["alpaca", "sft", "jsonl", "instruction-tuning", "export", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "dataset_id": {"type": "string", "required": True,
                       "description": "清洗后 dataset 的 UUID"},
        "field_map": {"type": "object", "required": False, "default": {
            "instruction": "prompt", "input": "context", "output": "caption"
        }, "description": "{instruction,input,output} -> dataset 字段名映射"},
        "shuffle": {"type": "boolean", "default": True},
        "shuffle_seed": {"type": "int", "default": 42},
        "limit": {"type": "int", "default": 0,
                  "description": "0 = 全部; >0 = 截断到该数量"},
        "drop_nsfw": {"type": "boolean", "default": True},
        "drop_blurry": {"type": "boolean", "default": True},
        "blurry_threshold": {"type": "float", "default": 80.0,
                             "description": "Laplacian variance 阈值"},
        "dedup_method": {"type": "string", "default": "phash_clip",
                          "enum": ["phash", "clip", "phash_clip"]},
        "oss_bucket": {"type": "string", "default": "sft-alpaca"},
        "oss_key_prefix": {"type": "string", "default": "alpaca/"},
    },
    "outputs": [
        "manifest.jsonl",
        "alpaca.jsonl",
        "schema_errors.jsonl",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Dataset",
         "operator": "dataset.load",
         "config": {"dataset_id": "$inputs.dataset_id"}},
        {"id": "cl", "name": "NSFW + Blur Filter",
         "operator": "cleaning.safety_filter",
         "config": {"drop_nsfw": "$inputs.drop_nsfw",
                    "drop_blurry": "$inputs.drop_blurry",
                    "blur_threshold": "$inputs.blurry_threshold"}},
        {"id": "dd", "name": "Dedup (pHash + CLIP)",
         "operator": "cleaning.dedup",
         "config": {"method": "$inputs.dedup_method"}},
        {"id": "mp", "name": "Field Map to Alpaca",
         "operator": "format.alpaca_map",
         "config": {"field_map": "$inputs.field_map"}},
        {"id": "sc", "name": "Schema Validate",
         "operator": "format.alpaca_schema_check",
         "config": {"require": ["instruction", "output"],
                    "min_output_len": 5}},
        {"id": "sh", "name": "Shuffle + Limit",
         "operator": "data.shuffle_limit",
         "config": {"shuffle": "$inputs.shuffle",
                    "seed": "$inputs.shuffle_seed",
                    "limit": "$inputs.limit"}},
        {"id": "wr", "name": "Write JSONL",
         "operator": "export.write_jsonl",
         "config": {"line_per_record": True,
                    "include_stats": True}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"},
         "retry_max": 2},
    ],
    "metrics": [
        "records_loaded", "records_after_clean", "records_after_dedup",
        "records_written", "records_skipped_schema",
        "bytes_written", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]