"""Collection template: Kaggle dataset import.

Pipeline:
  1. auth         — Kaggle API 凭证校验
  2. resolve      — 解析 dataset_slug / file_filter
  3. download     — kaggle datasets download (zip 拉取)
  4. unzip        — 解压 + 文件白名单
  5. convert      — 统一转 Parquet (CSV/JSON -> Parquet)
  6. oss_upload   — 上传
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-coll-005",
    "name": "Kaggle Dataset Import (Kaggle 数据集导入)",
    "category": "collection",
    "description": (
        "从 Kaggle 导入数据集, 解压后转 Parquet, 上传到对象存储。"
    ),
    "tags": ["kaggle", "dataset", "collection", "csv"],
    "version": "1.0.0",
    "inputs": {
        "dataset_slug": {"type": "string", "required": True,
                          "description": "e.g. andrewmvd/heart-failure-clinical-data"},
        "file_glob": {"type": "array<string>", "default": ["*.csv", "*.json"]},
        "max_rows": {"type": "int", "default": 0},
        "oss_bucket": {"type": "string", "default": "raw-datasets"},
        "kaggle_username": {"type": "string", "required": True,
                             "env": "KAGGLE_USERNAME"},
        "kaggle_key": {"type": "string", "required": True,
                        "env": "KAGGLE_KEY"},
    },
    "outputs": ["manifest.json", "parquet/*.parquet"],
    "steps": [
        {"id": "auth", "name": "Auth Check",
         "operator": "kaggle.auth_check",
         "config": {"username_env": "KAGGLE_USERNAME",
                    "key_env": "KAGGLE_KEY"}},
        {"id": "resolve", "name": "Resolve Files",
         "operator": "kaggle.list_files",
         "config": {"dataset_slug": "$inputs.dataset_slug",
                    "file_glob": "$inputs.file_glob"}},
        {"id": "dl", "name": "Download",
         "operator": "kaggle.download",
         "config": {"dataset_slug": "$inputs.dataset_slug",
                    "force": False}},
        {"id": "unzip", "name": "Unzip",
         "operator": "archive.unzip",
         "config": {"whitelist": "$inputs.file_glob",
                    "max_files": 1000}},
        {"id": "convert", "name": "Parquet Convert",
         "operator": "dataset.to_parquet",
         "config": {"compression": "zstd",
                    "max_rows": "$inputs.max_rows"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "collection/kaggle/",
                    "manifest": True}},
    ],
    "metrics": ["files_resolved", "bytes_downloaded",
                "rows_kept", "duration_seconds"],
}


__all__ = ["TEMPLATE"]