"""P3-6-W1: business feedback template — Model Eval Feedback.

Pipeline (模型评测反馈数据生成):
  1.  load_model       - 加载模型 checkpoint (local/hf_url)
  2.  load_benchmarks  - 加载基准集 (mmlu/gpqa/mmmu/mmstar/...)
  3.  run_suite        - 并发跑 benchmark suite
  4.  drift_compare    - 与 baseline (上一个版本) 对比
  5.  regression_flag  - 标记回归 (drop > drift_threshold)
  6.  feedback_gen     - 生成 per-task 反馈数据 (correct/wrong/coverage)
  7.  retrain_signal   - 写入 retrain signal 到 ops
  8.  report           - 输出 eval_results.json + drift_report.json
  9.  oss_upload       - 上传到 eval-fb bucket

vs basic_templates/feedback.py::tpl-biz-fb-002: 本模板加入 benchmark 并发
  + per-task feedback 数据生成 + 写入 retrain signal queue。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-fb-002",
    "name": "Model Eval Feedback Generation (商业级)",
    "category": "feedback",
    "description": (
        "模型评测反馈:并发 benchmark + drift 对比 + 回归标记 + "
        "per-task 反馈数据 + retrain signal。"
    ),
    "tags": ["eval", "benchmark", "feedback",
             "drift", "retrain", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "model_id": {"type": "string", "required": True},
        "model_path": {"type": "string", "required": True,
                       "description": "本地路径或 HF repo"},
        "baseline_model_id": {"type": "string", "required": False,
                              "description": "对比的上一版本 model_id"},
        "benchmarks": {"type": "array<string>", "required": True,
                        "description": "如 ['mmlu', 'gpqa', 'mmmu', 'mmstar']"},
        "max_concurrent": {"type": "int", "default": 4},
        "drift_threshold": {"type": "float", "default": 0.05,
                              "description": "指标下降 > 此值 = 回归"},
        "feedback_per_task": {"type": "boolean", "default": True,
                                "description": "生成 per-task feedback 数据"},
        "emit_retrain_signal": {"type": "boolean", "default": True},
        "oss_bucket": {"type": "string", "default": "eval-fb"},
        "oss_key_prefix": {"type": "string", "default": "eval_feedback/"},
    },
    "outputs": [
        "eval_results.json",
        "drift_report.json",
        "regression_flags.json",
        "per_task_feedback.jsonl",
        "retrain_signal.json",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Model",
         "operator": "model.load",
         "config": {"model_id": "$inputs.model_id",
                    "path": "$inputs.model_path"}},
        {"id": "bl", "name": "Load Baseline",
         "operator": "model.load_baseline",
         "config": {"baseline_model_id": "$inputs.baseline_model_id"}},
        {"id": "lb", "name": "Load Benchmarks",
         "operator": "evaluation.load_benchmarks",
         "config": {"benchmarks": "$inputs.benchmarks"}},
        {"id": "rn", "name": "Run Benchmarks (concurrent)",
         "operator": "evaluation.run_suite",
         "config": {"max_concurrent": "$inputs.max_concurrent"}},
        {"id": "cm", "name": "Compare to Baseline",
         "operator": "evaluation.compare",
         "config": {"drift_threshold": "$inputs.drift_threshold"}},
        {"id": "fl", "name": "Flag Regressions",
         "operator": "evaluation.flag_regression"},
        {"id": "fb", "name": "Generate per-task Feedback",
         "operator": "evaluation.per_task_feedback",
         "config": {"enabled": "$inputs.feedback_per_task"}},
        {"id": "sg", "name": "Emit Retrain Signal",
         "operator": "ops.retrain_signal",
         "config": {"enabled": "$inputs.emit_retrain_signal"}},
        {"id": "wr", "name": "Persist Reports",
         "operator": "export.write_eval_reports"},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "benchmarks_run", "tasks_total", "tasks_correct",
        "accuracy", "regressions_flagged",
        "retrain_signals_emitted", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]