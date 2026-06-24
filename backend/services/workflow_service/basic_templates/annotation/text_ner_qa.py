"""Annotation template: Text NER + QA (文本 NER + QA 标注).

Pipeline:
  1.  prelabel_ner  - 调 NER 模型给候选实体 (per/token)
  2.  prelabel_qa   - LLM 给候选 QA 对 (SQuAD 风格)
  3.  human_ner     - 人工修正实体边界/类别 (BIO)
  4.  human_qa      - 人工校验 QA 对
  5.  consistency   - 跨标注员一致性
  6.  export        - 输出 CoNLL-2003 / SQuAD JSON
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-ann-004",
    "name": "Text NER + QA Annotation (文本 NER + QA 标注)",
    "category": "annotation",
    "description": (
        "文本 NER + QA 双任务标注, 预标注 + 人工修正 + 一致性, "
        "输出 CoNLL 与 SQuAD 两种格式。"
    ),
    "tags": ["text", "annotation", "ner", "qa"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "ner_labels": {"type": "array<string>",
                        "default": ["PER", "ORG", "LOC", "MISC"]},
        "ner_model": {"type": "string", "default": "bert-base-ner"},
        "qa_model": {"type": "string", "default": "llama-3-8b-instruct"},
        "qa_per_passage": {"type": "int", "default": 5},
        "reviewers_per_item": {"type": "int", "default": 2},
        "oss_bucket": {"type": "string", "default": "annotations"},
    },
    "outputs": ["ner_conll.txt", "qa_squad.json",
                "agreement.json"],
    "steps": [
        {"id": "pl_n", "name": "Prelabel NER",
         "operator": "text.ner_predict",
         "config": {"model": "$inputs.ner_model",
                    "labels": "$inputs.ner_labels"}},
        {"id": "pl_q", "name": "Prelabel QA",
         "operator": "llm.qa_generate",
         "config": {"model": "$inputs.qa_model",
                    "per_passage": "$inputs.qa_per_passage"}},
        {"id": "hu_n", "name": "Human NER",
         "operator": "annotation.ner_human",
         "config": {"tool": "doccano",
                    "scheme": "BIO",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item"}},
        {"id": "hu_q", "name": "Human QA",
         "operator": "annotation.qa_human",
         "config": {"tool": "doccano",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item"}},
        {"id": "ag", "name": "Consensus",
         "operator": "annotation.consensus",
         "config": {"metric": "f1_agreement"}},
        {"id": "ex", "name": "Export",
         "operator": "annotation.export",
         "config": {"formats": ["conll2003", "squad"],
                    "bucket": "$inputs.oss_bucket"}},
    ],
    "metrics": ["passages_total", "entities_total",
                "qa_pairs_total", "f1_agreement",
                "duration_hours"],
}


__all__ = ["TEMPLATE"]