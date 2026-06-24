"""P3-6-W2: 5 export-format business templates.

Covers the canonical ML training data export formats:
  * Alpaca (SFT single-turn instruction tuning)
  * ShareGPT (SFT multi-turn conversation)
  * COCO (object detection)
  * YOLO (Ultralytics training)
  * HuggingFace Parquet (HF datasets / generic ML)

Each template includes rich ``inputs`` / ``outputs`` / ``steps`` /
``metrics`` metadata for downstream UI rendering, while still
exposing the canonical ``nodes`` array for ``NodeModel`` validation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._helpers import _n, _meta


_EXPORT_TEMPLATES: List[Dict[str, Any]] = [

    # ---- 1. Alpaca SFT -----------------------------------------------
    {"id": "tpl-biz-exp-001", "category": "export",
     "name": "Alpaca SFT Export",
     "tags": ["alpaca", "sft", "instruction-tuning", "jsonl"],
     "description": ("Export curated image+caption dataset to Alpaca-format "
                     "JSONL for instruction tuning (instruction / input / "
                     "output schema)."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "dataset_id": {"type": "string", "required": True,
                            "description": "Source dataset UUID"},
             "field_map": {"type": "object", "required": False,
                            "description": "{instruction,input,output} -> "
                                           "field names; defaults to "
                                           "{prompt,context,caption}"},
             "split": {"type": "string", "default": "train",
                       "enum": ["train", "val", "test"]},
             "shuffle": {"type": "boolean", "default": True},
             "limit": {"type": "int", "default": 0,
                       "description": "0 = all rows"},
             "oss_bucket": {"type": "string", "default": "sft-alpaca"},
         },
         outputs=["manifest.jsonl", "alpaca.jsonl", "stats.json"],
         steps=[
             {"id": "load", "name": "Load Curated Dataset",
              "operator": "dataset.load",
              "config": {"dataset_id": "$inputs.dataset_id",
                         "split": "$inputs.split"}},
             {"id": "map", "name": "Field Map to Alpaca Schema",
              "operator": "format.alpaca_map",
              "config": {"field_map": "$inputs.field_map"}},
             {"id": "shuf", "name": "Shuffle",
              "operator": "data.shuffle",
              "config": {"seed": 42}},
             {"id": "lim", "name": "Limit",
              "operator": "data.limit",
              "config": {"limit": "$inputs.limit"}},
             {"id": "val", "name": "Schema Validate",
              "operator": "format.alpaca_validate",
              "config": {"require": ["instruction", "output"]}},
             {"id": "wr", "name": "Write JSONL",
              "operator": "export.write_jsonl",
              "config": {"line_per_record": True}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket",
                         "key_prefix": "alpaca/"}},
         ],
         metrics=["records_written", "records_skipped",
                  "schema_errors", "bytes_written", "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_dataset", "collection"),
               _n("mp", "alpaca_map", "export", "ld"),
               _n("vl", "schema_validate", "export", "mp"),
               _n("wr", "write_jsonl", "export", "vl"),
               _n("up", "oss_upload", "export", "wr", retry_max=2)]},

    # ---- 2. ShareGPT multi-turn -------------------------------------
    {"id": "tpl-biz-exp-002", "category": "export",
     "name": "ShareGPT Conversation Export",
     "tags": ["sharegpt", "sft", "multi-turn", "conversation", "json"],
     "description": ("Export dialogue dataset to ShareGPT JSON format "
                     "(conversations[].from/value) for multi-turn SFT."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "dataset_id": {"type": "string", "required": True},
             "min_turns": {"type": "int", "default": 2, "min": 1},
             "max_turns": {"type": "int", "default": 20, "min": 1},
             "role_map": {"type": "object", "default": {"human": "user",
                                                          "gpt": "assistant",
                                                          "system": "system"}},
             "oss_bucket": {"type": "string", "default": "sft-sharegpt"},
         },
         outputs=["sharegpt.json", "stats.json"],
         steps=[
             {"id": "load", "name": "Load Dialogues",
              "operator": "dataset.load_dialogues",
              "config": {"dataset_id": "$inputs.dataset_id"}},
             {"id": "norm", "name": "Normalize Roles",
              "operator": "format.sharegpt_normalize",
              "config": {"role_map": "$inputs.role_map"}},
             {"id": "flt", "name": "Turn Count Filter",
              "operator": "data.filter_turns",
              "config": {"min": "$inputs.min_turns",
                         "max": "$inputs.max_turns"}},
             {"id": "wr", "name": "Write ShareGPT JSON",
              "operator": "export.write_sharegpt",
              "config": {"indent": 2}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket",
                         "key_prefix": "sharegpt/"}},
         ],
         metrics=["conversations_written", "turns_total",
                  "avg_turns_per_conv", "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_dialogues", "collection"),
               _n("nm", "normalize_roles", "export", "ld"),
               _n("ft", "filter_turns", "export", "nm"),
               _n("wr", "write_sharegpt", "export", "ft"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 3. COCO detection ------------------------------------------
    {"id": "tpl-biz-exp-003", "category": "export",
     "name": "COCO Detection Export",
     "tags": ["coco", "object-detection", "bbox", "json"],
     "description": ("Export annotated bbox dataset to COCO format with "
                     "images / annotations / categories JSON."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "dataset_id": {"type": "string", "required": True},
             "category_set": {"type": "array<object>",
                              "description": "{id, name, supercategory}"},
             "image_subdir": {"type": "string", "default": "images/"},
             "oss_bucket": {"type": "string", "default": "det-coco"},
         },
         outputs=["annotations.json", "instances_train.json",
                  "instances_val.json", "stats.json"],
         steps=[
             {"id": "load", "name": "Load Annotations",
              "operator": "dataset.load_annotations",
              "config": {"dataset_id": "$inputs.dataset_id"}},
             {"id": "cat", "name": "Build Category Index",
              "operator": "format.coco_categories",
              "config": {"category_set": "$inputs.category_set"}},
             {"id": "bnd", "name": "Normalize BBox to XYWH",
              "operator": "format.coco_bbox_normalize",
              "config": {"to": "xywh"}},
             {"id": "sp", "name": "Train/Val Split",
              "operator": "data.split",
              "config": {"ratio": [0.8, 0.2], "stratify": "category"}},
             {"id": "wr", "name": "Write COCO JSON",
              "operator": "export.write_coco",
              "config": {"splits": ["train", "val"]}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket",
                         "key_prefix": "coco/"}},
         ],
         metrics=["images_total", "annotations_total",
                  "categories_count", "bbox_stats", "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_annotations", "collection"),
               _n("ci", "coco_categories", "export", "ld"),
               _n("bn", "bbox_normalize", "export", "ci"),
               _n("sp", "split", "export", "bn"),
               _n("wr", "write_coco", "export", "sp"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 4. YOLO training -------------------------------------------
    {"id": "tpl-biz-exp-004", "category": "export",
     "name": "YOLO Training Export",
     "tags": ["yolo", "ultralytics", "detection", "txt"],
     "description": ("Export bbox dataset to Ultralytics YOLO format: "
                     "images/*.jpg + labels/*.txt + data.yaml + "
                     "train.txt / val.txt."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "dataset_id": {"type": "string", "required": True},
             "class_names": {"type": "array<string>", "required": True},
             "img_size": {"type": "int", "default": 640},
             "oss_bucket": {"type": "string", "default": "det-yolo"},
         },
         outputs=["data.yaml", "labels/", "images/",
                  "train.txt", "val.txt", "stats.json"],
         steps=[
             {"id": "load", "name": "Load Annotations",
              "operator": "dataset.load_annotations",
              "config": {"dataset_id": "$inputs.dataset_id"}},
             {"id": "cnv", "name": "BBox to YOLO XYWHN",
              "operator": "format.yolo_normalize",
              "config": {"to": "xywhn",
                         "class_names": "$inputs.class_names"}},
             {"id": "rs", "name": "Letterbox Resize",
              "operator": "image.letterbox",
              "config": {"size": "$inputs.img_size"}},
             {"id": "sp", "name": "Train/Val Split",
              "operator": "data.split",
              "config": {"ratio": [0.9, 0.1]}},
             {"id": "wr", "name": "Write YOLO Files",
              "operator": "export.write_yolo",
              "config": {"write_data_yaml": True}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket",
                         "key_prefix": "yolo/"}},
         ],
         metrics=["images_total", "labels_total",
                  "avg_objs_per_image", "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_annotations", "collection"),
               _n("cn", "yolo_normalize", "export", "ld"),
               _n("rs", "letterbox_resize", "preprocessing", "cn"),
               _n("sp", "split", "export", "rs"),
               _n("wr", "write_yolo", "export", "sp"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 5. HF Parquet -----------------------------------------------
    {"id": "tpl-biz-exp-005", "category": "export",
     "name": "HuggingFace Parquet Export",
     "tags": ["parquet", "huggingface", "datasets", "arrow"],
     "description": ("Pack dataset into HF datasets-compatible Parquet "
                     "shards with manifest + repo card."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "dataset_id": {"type": "string", "required": True},
             "shard_size_mb": {"type": "int", "default": 500},
             "compression": {"type": "string", "default": "zstd",
                             "enum": ["snappy", "gzip", "zstd", "lz4"]},
             "row_group_size": {"type": "int", "default": 10000},
             "write_card": {"type": "boolean", "default": True},
             "oss_bucket": {"type": "string", "default": "hf-parquet"},
         },
         outputs=["data/train-00000-of-*.parquet",
                  "dataset_info.json", "README.md",
                  "manifest.json"],
         steps=[
             {"id": "load", "name": "Load Dataset",
              "operator": "dataset.load",
              "config": {"dataset_id": "$inputs.dataset_id"}},
             {"id": "norm", "name": "Schema Normalize",
              "operator": "format.hf_schema_normalize",
              "config": {"target": "datasets.Dataset"}},
             {"id": "pq", "name": "Write Parquet Shards",
              "operator": "export.to_parquet",
              "config": {"shard_size_mb": "$inputs.shard_size_mb",
                         "compression": "$inputs.compression",
                         "row_group_size": "$inputs.row_group_size"}},
             {"id": "card", "name": "Render Dataset Card",
              "operator": "docs.render_card",
              "config": {"enabled": "$inputs.write_card"}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket",
                         "key_prefix": "hf_parquet/"}},
         ],
         metrics=["rows_total", "shards_count",
                  "bytes_total", "compression_ratio",
                  "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_dataset", "collection"),
               _n("nm", "schema_normalize", "export", "ld"),
               _n("pq", "parquet_shards", "export", "nm"),
               _n("cd", "render_card", "docs", "pq"),
               _n("up", "oss_upload", "export", "cd", retry_max=2)]},
]


__all__ = ["_EXPORT_TEMPLATES"]