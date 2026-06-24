"""P3-6-W1: business feedback template — Data Iteration Loop.

Pipeline (Bad Case -> 重采集闭环):
  1.  badcase_run     - 运行 badcase 分析 (引用 tpl-bz2-fb-001)
  2.  root_cause_map  - 根因 -> 数据需求映射 (覆盖度低/噪声/偏置)
  3.  collect_gaps    - 收集缺失/有偏数据 (按需采集配置)
  4.  pii_redact      - 新数据 PII 脱敏
  5.  quality_flt     - 质量过滤 (blur/nsfw/OCR)
  6.  relabel         - 自动重标注 (引用 tpl-bz2-fb-004)
  7.  human_review    - 人工抽样审核 (引用 tpl-bz2-fb-003)
  8.  merge_v_next    - 合并到下一版本 (append/replace)
  9.  retrain_signal  - 触发 retrain signal
  10. re_eval         - 跑 eval 验证改进
  11. iteration_log   - 写 iteration_log.json (本次闭环全量审计)
  12. oss_upload      - 上传到 iteration bucket

vs basic_templates/feedback.py::tpl-biz-fb-005: 本模板细化 12 步,加入
  root_cause_map + collect_gaps + re_eval 验证。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-fb-005",
    "name": "Data Iteration Closed Loop (商业级)",
    "category": "feedback",
    "description": (
        "完整数据飞轮:badcase 分析 -> 根因映射 -> 补采 -> 重标 -> "
        "审核 -> 合版 -> retrain -> 复评,12 步全闭环。"
    ),
    "tags": ["iteration", "closed-loop", "flywheel",
             "retrain", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "eval_dataset_id": {"type": "string", "required": True},
        "annotation_dataset_id": {"type": "string", "required": True},
        "model_id": {"type": "string", "required": True},
        "badcase_threshold": {"type": "float", "default": 0.05,
                               "description": "badcase 占比 > 此值触发补采"},
        "collect_targets": {"type": "array<object>", "required": False,
                              "description": "[{type:'hf', ...}] 补采目标"},
        "max_iteration_count": {"type": "int", "default": 3,
                                  "description": "最大迭代轮次"},
        "version_strategy": {"type": "string", "default": "append",
                               "enum": ["append", "replace"]},
        "retrain_auto": {"type": "boolean", "default": True},
        "oss_bucket": {"type": "string", "default": "iteration"},
        "oss_key_prefix": {"type": "string", "default": "iteration/"},
    },
    "outputs": [
        "v_next/",
        "iteration_log.json",
        "root_cause_map.json",
        "collect_manifest.jsonl",
        "improvement_metrics.json",
        "stats.json",
    ],
    "steps": [
        {"id": "bc", "name": "Bad-case Analysis",
         "operator": "feedback.badcase",
         "config": {"eval_dataset_id": "$inputs.eval_dataset_id",
                    "model_id": "$inputs.model_id"}},
        {"id": "rm", "name": "Root-cause -> Data Gap Map",
         "operator": "analysis.root_cause_to_data_gap"},
        {"id": "cg", "name": "Collect Gaps",
         "operator": "collection.gap_collect",
         "config": {"targets": "$inputs.collect_targets"}},
        {"id": "pi", "name": "PII Redact (new data)",
         "operator": "cleaning.pii_redact"},
        {"id": "qf", "name": "Quality Filter",
         "operator": "cleaning.quality_filter"},
        {"id": "rl", "name": "Auto Relabel",
         "operator": "feedback.relabel",
         "config": {"annotation_dataset_id":
                       "$inputs.annotation_dataset_id"}},
        {"id": "hr", "name": "Human Review (sample)",
         "operator": "feedback.human_review",
         "config": {"sample_size": 100}},
        {"id": "mg", "name": "Merge Into Next Version",
         "operator": "dataset.merge_version",
         "config": {"strategy": "$inputs.version_strategy"}},
        {"id": "rt", "name": "Trigger Retrain",
         "operator": "ops.retrain_signal",
         "config": {"model_id": "$inputs.model_id",
                    "auto": "$inputs.retrain_auto"}},
        {"id": "ev", "name": "Re-evaluate",
         "operator": "evaluation.run_suite",
         "config": {"model_id": "$inputs.model_id"}},
        {"id": "im", "name": "Compute Improvement Metrics",
         "operator": "analysis.improvement_diff"},
        {"id": "wr", "name": "Persist Iteration Log",
         "operator": "export.write_iteration_log"},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "badcases", "relabeled", "merged_count",
        "retrain_signals", "eval_score_prev", "eval_score_new",
        "improvement_pct", "iterations", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]