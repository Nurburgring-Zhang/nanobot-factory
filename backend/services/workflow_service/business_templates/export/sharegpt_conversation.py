"""P3-6-W1: business export template — ShareGPT conversation.

Pipeline (multi-turn dialogue export):
  1.  load_dial       - 加载多轮对话数据 (from dialogues dataset)
  2.  role_norm       - role 归一化 (human/gpt/system -> user/assistant/system)
  3.  turn_filter     - turn 数过滤 (min_turns/max_turns)
  4.  dedup_dialogue  - 按首句 + 末句 dedup
  5.  content_redact  - PII 邮箱/手机号/身份证号脱敏
  6.  json_write      - 写 ShareGPT JSON (conversations[].from/value)
  7.  oss_upload      - 上传到 sft-sharegpt bucket

vs basic_templates/export.py::tpl-biz-exp-002: 本模板新增 PII redact +
  dedup_dialogue + role 严格规范化。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-exp-002",
    "name": "ShareGPT Conversation Export (商业级)",
    "category": "export",
    "description": (
        "多轮对话 ShareGPT 导出:role 归一化 + PII 脱敏 + turn 过滤 + "
        "对话 dedup + JSON 写出。"
    ),
    "tags": ["sharegpt", "sft", "multi-turn", "conversation",
             "json", "pii", "export", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "dataset_id": {"type": "string", "required": True,
                       "description": "对话 dataset 的 UUID"},
        "min_turns": {"type": "int", "default": 2, "min": 1},
        "max_turns": {"type": "int", "default": 20, "min": 1},
        "role_map": {"type": "object", "required": False, "default": {
            "human": "user", "gpt": "assistant",
            "system": "system", "user": "user", "assistant": "assistant",
        }, "description": "源 role -> ShareGPT role 映射"},
        "redact_pii": {"type": "boolean", "default": True,
                       "description": "是否脱敏邮箱/手机号/身份证号"},
        "dedup_dialogues": {"type": "boolean", "default": True},
        "limit": {"type": "int", "default": 0},
        "oss_bucket": {"type": "string", "default": "sft-sharegpt"},
        "oss_key_prefix": {"type": "string", "default": "sharegpt/"},
    },
    "outputs": [
        "sharegpt.json",
        "dedup_dropped.jsonl",
        "pii_redactions.jsonl",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Dialogues",
         "operator": "dataset.load_dialogues",
         "config": {"dataset_id": "$inputs.dataset_id"}},
        {"id": "nm", "name": "Normalize Roles",
         "operator": "format.sharegpt_normalize",
         "config": {"role_map": "$inputs.role_map"}},
        {"id": "ft", "name": "Turn Count Filter",
         "operator": "data.filter_turns",
         "config": {"min": "$inputs.min_turns",
                    "max": "$inputs.max_turns"}},
        {"id": "pi", "name": "PII Redact",
         "operator": "cleaning.pii_redact",
         "config": {"enabled": "$inputs.redact_pii",
                    "patterns": ["email", "phone", "id_card"]}},
        {"id": "dd", "name": "Dedup Dialogues",
         "operator": "data.dedup_dialogues",
         "config": {"enabled": "$inputs.dedup_dialogues",
                    "key": ["first_msg", "last_msg"]}},
        {"id": "lm", "name": "Limit",
         "operator": "data.limit",
         "config": {"limit": "$inputs.limit"}},
        {"id": "wr", "name": "Write ShareGPT JSON",
         "operator": "export.write_sharegpt",
         "config": {"indent": 2}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "conversations_loaded", "conversations_after_filter",
        "conversations_written", "turns_total",
        "avg_turns_per_conv", "pii_redactions",
        "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]