"""P3-6-W1: business feedback template — Human Review Loop.

Pipeline (人工审核闭环,带 callback URL):
  1.  sample_outputs  - 从模型输出采样 N 条
  2.  build_form      - 构建审核表单 (UI 配置 + schema)
  3.  dispatch        - 派发给 reviewer (按 SLA 路由)
  4.  callback        - 等待 webhook callback (URL + token)
  5.  collect_rating  - 收集审核结果 (rating 1-5 + comments)
  6.  requeue         - rating < min_rating 重新进入标注队列
  7.  audit_trail     - 全链路审计日志 (谁/何时/做了什么)
  8.  export          - 输出 audit.jsonl + requeue.jsonl
  9.  oss_upload      - 上传到 human-review bucket

vs basic_templates/feedback.py::tpl-biz-fb-003: 本模板加入 webhook callback
  + SLA 路由 + audit_trail + 自动 requeue。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-fb-003",
    "name": "Human Review Loop (商业级)",
    "category": "feedback",
    "description": (
        "人工审核闭环:采样 + 派单 + webhook callback + 评分收集 + "
        "自动 requeue + 全链路 audit。"
    ),
    "tags": ["human-review", "loop", "callback",
             "audit", "requeue", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "source_dataset_id": {"type": "string", "required": True},
        "sample_size": {"type": "int", "default": 500, "min": 1},
        "sample_strategy": {"type": "string", "default": "stratified_difficulty",
                             "enum": ["random", "stratified_difficulty",
                                      "lowest_confidence", "diverse"]},
        "reviewer_pool": {"type": "array<string>", "required": False,
                          "description": "reviewer ID 池"},
        "sla_hours": {"type": "float", "default": 24.0,
                      "description": "单条 review SLA (小时)"},
        "min_rating": {"type": "int", "default": 3, "min": 1, "max": 5,
                        "description": "rating < 此值自动 requeue"},
        "callback_url": {"type": "string", "required": True,
                          "description": "webhook callback URL"},
        "callback_token": {"type": "string", "required": False,
                            "description": "callback 鉴权 token"},
        "callback_timeout_sec": {"type": "int", "default": 86400},
        "form_schema": {"type": "object", "required": False,
                         "description": "审核表单 schema (overrides default)"},
        "oss_bucket": {"type": "string", "default": "human-review"},
        "oss_key_prefix": {"type": "string", "default": "review/"},
    },
    "outputs": [
        "review_form.json",
        "dispatched.jsonl",
        "callback_received.jsonl",
        "audit.jsonl",
        "requeue.jsonl",
        "stats.json",
    ],
    "steps": [
        {"id": "sp", "name": "Sample Outputs",
         "operator": "dataset.sample",
         "config": {"k": "$inputs.sample_size",
                    "strategy": "$inputs.sample_strategy"}},
        {"id": "fm", "name": "Build Review Form",
         "operator": "annotation.review_form",
         "config": {"schema": "$inputs.form_schema",
                    "rating_scale": [1, 5]}},
        {"id": "dp", "name": "Dispatch to Reviewers",
         "operator": "annotation.dispatch",
         "config": {"reviewer_pool": "$inputs.reviewer_pool",
                    "sla_hours": "$inputs.sla_hours"}},
        {"id": "cb", "name": "Wait Webhook Callback",
         "operator": "annotation.callback_wait",
         "config": {"url": "$inputs.callback_url",
                    "token": "$inputs.callback_token",
                    "timeout_sec": "$inputs.callback_timeout_sec"}},
        {"id": "cr", "name": "Collect Ratings",
         "operator": "annotation.collect_ratings"},
        {"id": "rq", "name": "Requeue Low-rated",
         "operator": "annotation.requeue",
         "config": {"min_rating": "$inputs.min_rating"}},
        {"id": "au", "name": "Audit Trail",
         "operator": "annotation.audit_trail"},
        {"id": "wr", "name": "Export Audit",
         "operator": "export.write_audit"},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "sampled", "dispatched", "reviewed",
        "avg_rating", "requeued", "callback_timeouts",
        "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]