"""Cleaning template: Text PII redaction (复用 pii_engine).

Pipeline:
  1.  load          - 读 jsonl 输入
  2.  lang_detect   - 语言检测 (决定 PII 规则集)
  3.  pii_detect    - 复用 pii_engine (正则 + NER)
  4.  redact        - 替换策略 (mask / hash / fake / drop)
  5.  policy_audit  - 输出审计日志 (哪些字段被改)
  6.  write         - 输出 jsonl + audit.jsonl
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-cln-003",
    "name": "Text PII Redact (文本 PII 脱敏)",
    "category": "cleaning",
    "description": (
        "复用 imdf.cleaning_service.pii_engine 对文本 jsonl 做 PII "
        "检测与脱敏, 支持 mask/hash/fake/drop 四种策略。"
    ),
    "tags": ["text", "cleaning", "pii", "gdpr"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "text_field": {"type": "string", "default": "text"},
        "language": {"type": "string", "default": "auto"},
        "redact_strategy": {"type": "string", "default": "mask",
                             "enum": ["mask", "hash", "fake", "drop"]},
        "pii_types": {"type": "array<string>",
                       "default": ["email", "phone", "id_card",
                                    "credit_card", "ip", "url",
                                    "name", "address"]},
        "oss_bucket": {"type": "string", "default": "cleaned-text"},
    },
    "outputs": ["redacted.jsonl", "audit.jsonl", "stats.json"],
    "steps": [
        {"id": "load", "name": "Load jsonl",
         "operator": "text.read_jsonl",
         "config": {"source": "$inputs.input_manifest",
                    "fields": ["$inputs.text_field"]}},
        {"id": "lang", "name": "Language Detect",
         "operator": "text.lang_detect",
         "config": {"target_lang": "$inputs.language"}},
        {"id": "det", "name": "PII Detect",
         "operator": "pii.detect",
         "config": {"engine": "imdf.cleaning_service.pii_engine",
                    "types": "$inputs.pii_types",
                    "use_ner": True}},
        {"id": "redact", "name": "PII Redact",
         "operator": "pii.redact",
         "config": {"strategy": "$inputs.redact_strategy",
                    "preserve_format": True}},
        {"id": "audit", "name": "Policy Audit",
         "operator": "pii.audit",
         "config": {"log_each": True,
                    "include_context": False}},
        {"id": "write", "name": "Write jsonl",
         "operator": "text.write_jsonl",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/pii/"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/pii/",
                    "manifest": True}},
    ],
    "metrics": ["rows_in", "rows_out", "pii_entities_redacted",
                "by_type", "duration_seconds"],
}


__all__ = ["TEMPLATE"]