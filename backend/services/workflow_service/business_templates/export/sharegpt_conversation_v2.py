"""P3-6.5-W2: Hybrid Export — ShareGPT Multi-turn Conversation.

ShareGPT export with role normalization, turn count filter, token-length
filter (LLaMA tokenizer), and conversation hashing.

Category: export
Improvements over ``tpl-biz-exp-002``:
  * Token-length filter (drop too-long or too-short convs)
  * Conversation SHA256 for dedup
  * Multi-language role mapping
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-exp-h02",
    "category": "export",
    "name": "ShareGPT Conversation Export (Hybrid)",
    "tags": ["sharegpt", "sft", "multi-turn", "token-filter", "multilang"],
    "description": (
        "ShareGPT export with role normalization, turn count filter, "
        "token-length filter (LLaMA tokenizer), conversation SHA256 dedup, "
        "and multi-language role mapping."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "dataset_id": {"type": "string", "required": True},
            "min_turns": {"type": "int", "default": 2, "min": 1},
            "max_turns": {"type": "int", "default": 20, "min": 1},
            "min_total_tokens": {"type": "int", "default": 64,
                                  "min": 0},
            "max_total_tokens": {"type": "int", "default": 4096,
                                  "min": 64},
            "tokenizer": {"type": "string",
                           "default": "llama-3"},
            "language": {"type": "string", "default": "en",
                         "enum": ["en", "zh", "ja", "ko", "es"]},
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
            {"id": "norm", "name": "Normalize Roles (multilang)",
             "operator": "format.sharegpt_normalize",
             "config": {"role_map": "$inputs.role_map",
                        "language": "$inputs.language"}},
            {"id": "flt", "name": "Turn Count Filter",
             "operator": "data.filter_turns",
             "config": {"min": "$inputs.min_turns",
                        "max": "$inputs.max_turns"}},
            {"id": "tk", "name": "Token Length Filter",
             "operator": "data.filter_token_length",
             "config": {"tokenizer": "$inputs.tokenizer",
                        "min": "$inputs.min_total_tokens",
                        "max": "$inputs.max_total_tokens"}},
            {"id": "dd", "name": "Conversation SHA256 Dedup",
             "operator": "data.dedupe_by_hash",
             "config": {"hash_key": "conv_sha256"}},
            {"id": "wr", "name": "Write ShareGPT JSON",
             "operator": "export.write_sharegpt",
             "config": {"indent": 2}},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["conversations_in", "after_turn_filter",
                 "after_token_filter", "after_dedupe",
                 "turns_total", "avg_turns_per_conv",
                 "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_dialogues", "collection"),
              _n("nm", "normalize_roles", "export", "ld"),
              _n("ft", "filter_turns", "export", "nm"),
              _n("tk", "filter_token_length", "data", "ft"),
              _n("dd", "conv_dedupe", "data", "tk"),
              _n("wr", "write_sharegpt", "export", "dd"),
              _n("up", "oss_upload", "export", "wr")],
}