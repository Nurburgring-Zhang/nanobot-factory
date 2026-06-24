"""P3-6.5-W2: Hybrid Export — Alpaca SFT + Cardinality Check.

Alpaca JSONL export with cardinality check (instruction/input/output
uniqueness), schema strict validation, dataset card, and OSS upload.

Category: export
Improvements over ``tpl-biz-exp-001``:
  * Cardinality uniqueness check (drop duplicate instruction/input pairs)
  * Field-map auto-suggest from first 100 rows
  * Strict schema validate (Pydantic schema match)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-exp-h01",
    "category": "export",
    "name": "Alpaca SFT Export (Hybrid)",
    "tags": ["alpaca", "sft", "instruction-tuning", "cardinality"],
    "description": (
        "Alpaca-format export with cardinality uniqueness check "
        "(instruction/input), auto field-map suggestion, Pydantic strict "
        "schema validation, and dataset card generation."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "dataset_id": {"type": "string", "required": True},
            "field_map": {"type": "object", "required": False,
                          "description": "{instruction,input,output} -> "
                                          "field names"},
            "auto_field_map": {"type": "boolean", "default": True,
                                "description": "Auto-suggest field_map "
                                                "from first 100 rows"},
            "drop_duplicate_instructions": {"type": "boolean",
                                              "default": True},
            "split": {"type": "string", "default": "train",
                      "enum": ["train", "val", "test"]},
            "limit": {"type": "int", "default": 0},
            "oss_bucket": {"type": "string", "default": "sft-alpaca"},
        },
        outputs=["manifest.jsonl", "alpaca.jsonl",
                 "card.md", "stats.json"],
        steps=[
            {"id": "load", "name": "Load Curated Dataset",
             "operator": "dataset.load",
             "config": {"dataset_id": "$inputs.dataset_id",
                        "split": "$inputs.split"}},
            {"id": "afm", "name": "Auto Field-Map Suggest",
             "operator": "format.alpaca_field_map_suggest",
             "config": {"enabled": "$inputs.auto_field_map"}},
            {"id": "map", "name": "Field Map to Alpaca",
             "operator": "format.alpaca_map",
             "config": {"field_map": "$inputs.field_map"}},
            {"id": "cd", "name": "Cardinality Dedupe",
             "operator": "data.dedupe_by_key",
             "config": {"key": ["instruction", "input"],
                        "enabled":
                            "$inputs.drop_duplicate_instructions"}},
            {"id": "shuf", "name": "Shuffle",
             "operator": "data.shuffle",
             "config": {"seed": 42}},
            {"id": "lim", "name": "Limit",
             "operator": "data.limit",
             "config": {"limit": "$inputs.limit"}},
            {"id": "val", "name": "Pydantic Strict Validate",
             "operator": "format.alpaca_pydantic_validate",
             "config": {"require": ["instruction", "output"]}},
            {"id": "wr", "name": "Write JSONL",
             "operator": "export.write_jsonl"},
            {"id": "card", "name": "Dataset Card",
             "operator": "docs.render_card"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["wr", "card"]},
        ],
        metrics=["records_in", "records_after_dedupe",
                 "records_skipped", "schema_errors",
                 "bytes_written", "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_dataset", "collection"),
              _n("afm", "field_map_suggest", "export", "ld"),
              _n("mp", "alpaca_map", "export", "afm"),
              _n("cd", "cardinality_dedupe", "data", "mp"),
              _n("sh", "shuffle", "data", "cd"),
              _n("lm", "limit", "data", "sh"),
              _n("vl", "pydantic_validate", "export", "lm"),
              _n("wr", "write_jsonl", "export", "vl"),
              _n("card", "render_card", "docs", "wr"),
              _n("up", "oss_upload", "export", "card")],
}