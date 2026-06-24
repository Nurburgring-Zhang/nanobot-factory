"""P3-6-W2: 5 feedback-loop business templates.

These templates close the data flywheel by feeding evaluation and
human feedback back into the dataset:

  * Bad-case auto analysis
  * Model eval feedback
  * Human review loop
  * Auto relabel
  * Data iteration (full closed loop)
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._helpers import _n, _meta


_FEEDBACK_TEMPLATES: List[Dict[str, Any]] = [

    # ---- 1. Bad-case auto analysis ---------------------------------
    {"id": "tpl-biz-fb-001", "category": "feedback",
     "name": "Bad Case Auto Analysis",
     "tags": ["bad-case", "failure", "analysis"],
     "description": ("Find model failures: low reward / low CLIP / "
                     "low human rating -> cluster -> root-cause tag -> "
                     "export bad-case report."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "eval_dataset_id": {"type": "string", "required": True},
             "reward_threshold": {"type": "float", "default": 0.3},
             "clip_threshold": {"type": "float", "default": 0.18},
             "oss_bucket": {"type": "string", "default": "badcase"},
         },
         outputs=["badcase.jsonl", "clusters.json",
                  "root_cause.csv", "stats.json"],
         steps=[
             {"id": "ld", "name": "Load Eval Outputs",
              "operator": "dataset.load_eval",
              "config": {"dataset_id": "$inputs.eval_dataset_id"}},
             {"id": "flt", "name": "Failure Filter",
              "operator": "dataset.badcase_filter",
              "config": {"reward_max": "$inputs.reward_threshold",
                         "clip_max": "$inputs.clip_threshold"}},
             {"id": "cl", "name": "Cluster Bad Cases",
              "operator": "analysis.cluster",
              "config": {"method": "embedding_kmeans"}},
             {"id": "rc", "name": "Root-cause Tag",
              "operator": "analysis.root_cause"},
             {"id": "wr", "name": "Bad-case Report",
              "operator": "export.write_badcase"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["total", "badcases", "clusters",
                  "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_eval", "collection"),
               _n("flt", "badcase_filter", "dataset", "ld"),
               _n("cl", "cluster", "analysis", "flt"),
               _n("rc", "root_cause", "analysis", "cl"),
               _n("wr", "badcase_export", "export", "rc"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 2. Model eval feedback ------------------------------------
    {"id": "tpl-biz-fb-002", "category": "feedback",
     "name": "Model Eval Feedback Pipeline",
     "tags": ["eval", "benchmark", "feedback"],
     "description": ("Run model eval suite -> collect metric drift -> "
                     "flag regressions -> emit retrain signal."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "model_id": {"type": "string", "required": True},
             "benchmarks": {"type": "array<string>", "required": True,
                             "description": "e.g. mmlu, gpqa, mmmu"},
             "drift_threshold": {"type": "float", "default": 0.05,
                                  "description": "metric drop vs baseline"},
             "oss_bucket": {"type": "string", "default": "eval-fb"},
         },
         outputs=["eval_results.json", "drift_report.json",
                  "retrain_signal.json"],
         steps=[
             {"id": "run", "name": "Run Benchmarks",
              "operator": "evaluation.run_suite",
              "config": {"model_id": "$inputs.model_id",
                         "benchmarks": "$inputs.benchmarks"}},
             {"id": "cmp", "name": "Compare to Baseline",
              "operator": "evaluation.compare",
              "config": {"drift_threshold": "$inputs.drift_threshold"}},
             {"id": "flg", "name": "Flag Regressions",
              "operator": "evaluation.flag_regression"},
             {"id": "sig", "name": "Emit Retrain Signal",
              "operator": "ops.retrain_signal"},
             {"id": "wr", "name": "Persist Reports",
              "operator": "export.write_eval_reports"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["benchmarks_run", "regressions_flagged",
                  "duration_seconds"],
     ),
     "nodes": [_n("run", "run_benchmarks", "evaluation"),
               _n("cmp", "compare_baseline", "evaluation", "run"),
               _n("flg", "flag_regression", "evaluation", "cmp"),
               _n("sig", "retrain_signal", "ops", "flg"),
               _n("wr", "persist_reports", "export", "sig"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 3. Human review loop --------------------------------------
    {"id": "tpl-biz-fb-003", "category": "feedback",
     "name": "Human Review Loop Pipeline",
     "tags": ["human-review", "loop", "annotation"],
     "description": ("Sample model outputs -> human review form -> "
                     "score -> requeue low-rated for relabel -> "
                     "audit trail export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "source_dataset_id": {"type": "string", "required": True},
             "sample_size": {"type": "int", "default": 500},
             "min_rating": {"type": "int", "default": 3,
                            "min": 1, "max": 5},
             "oss_bucket": {"type": "string", "default": "human-review"},
         },
         outputs=["review_form.json", "audit.jsonl",
                  "requeue.jsonl", "stats.json"],
         steps=[
             {"id": "sp", "name": "Sample Outputs",
              "operator": "dataset.sample",
              "config": {"k": "$inputs.sample_size"}},
             {"id": "fr", "name": "Build Review Form",
              "operator": "annotation.review_form"},
             {"id": "rv", "name": "Human Review",
              "operator": "annotation.review_collect"},
             {"id": "rq", "name": "Requeue Low-rated",
              "operator": "annotation.requeue",
              "config": {"min_rating": "$inputs.min_rating"}},
             {"id": "au", "name": "Audit Trail",
              "operator": "annotation.audit_trail"},
             {"id": "wr", "name": "Export Audit",
              "operator": "export.write_audit"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["sampled", "reviewed", "requeued",
                  "avg_rating", "duration_seconds"],
     ),
     "nodes": [_n("sp", "sample", "dataset"),
               _n("fr", "review_form", "annotation", "sp"),
               _n("rv", "human_review", "annotation", "fr"),
               _n("rq", "requeue", "annotation", "rv"),
               _n("au", "audit_trail", "annotation", "rq"),
               _n("wr", "audit_export", "export", "au"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 4. Auto relabel -------------------------------------------
    {"id": "tpl-biz-fb-004", "category": "feedback",
     "name": "Auto Relabel Pipeline",
     "tags": ["relabel", "auto-label", "feedback"],
     "description": ("Identify low-confidence labels -> run stronger "
                     "model prelabel -> consensus with previous labels "
                     "-> write new annotations."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "annotation_dataset_id": {"type": "string", "required": True},
             "max_confidence": {"type": "float", "default": 0.7,
                                 "description": "labels with conf < this "
                                                "are relabeled"},
             "stronger_model": {"type": "string",
                                 "default": "qwen-vl-max"},
             "oss_bucket": {"type": "string", "default": "relabel"},
         },
         outputs=["relabel.jsonl", "diff.jsonl",
                  "merged.jsonl", "stats.json"],
         steps=[
             {"id": "ld", "name": "Load Existing Annotations",
              "operator": "dataset.load_annotations",
              "config": {"dataset_id": "$inputs.annotation_dataset_id"}},
             {"id": "flt", "name": "Low-Confidence Filter",
              "operator": "dataset.low_confidence",
              "config": {"max": "$inputs.max_confidence"}},
             {"id": "pl", "name": "Strong-Model Prelabel",
              "operator": "annotation.prelabel",
              "config": {"model": "$inputs.stronger_model"}},
             {"id": "cs", "name": "Consensus Merge",
              "operator": "annotation.consensus_merge"},
             {"id": "wr", "name": "Export Diff + Merged",
              "operator": "export.write_relabel"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["annotations", "low_conf", "relabeled",
                  "changed", "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_annotations", "collection"),
               _n("flt", "low_confidence", "dataset", "ld"),
               _n("pl", "stronger_prelabel", "annotation", "flt"),
               _n("cs", "consensus_merge", "consensus", "pl"),
               _n("wr", "relabel_export", "export", "cs"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 5. Data iteration (closed loop) ---------------------------
    {"id": "tpl-biz-fb-005", "category": "feedback",
     "name": "Data Iteration Closed Loop",
     "tags": ["iteration", "closed-loop", "flywheel"],
     "description": ("Full data flywheel: bad-case analysis -> relabel "
                     "-> human review -> merge into next version -> "
                     "trigger retrain -> re-evaluate."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "eval_dataset_id": {"type": "string", "required": True},
             "annotation_dataset_id": {"type": "string", "required": True},
             "model_id": {"type": "string", "required": True},
             "version_strategy": {"type": "string", "default": "append",
                                   "enum": ["append", "replace"]},
             "oss_bucket": {"type": "string", "default": "iteration"},
         },
         outputs=["v_next/", "iteration_log.json", "stats.json"],
         steps=[
             {"id": "bc", "name": "Bad-case Analysis",
              "operator": "feedback.badcase",
              "config": {"eval_dataset_id": "$inputs.eval_dataset_id"}},
             {"id": "rl", "name": "Auto Relabel",
              "operator": "feedback.relabel",
              "config": {"annotation_dataset_id":
                              "$inputs.annotation_dataset_id"}},
             {"id": "hr", "name": "Human Review",
              "operator": "feedback.human_review"},
             {"id": "mg", "name": "Merge Into Next Version",
              "operator": "dataset.merge_version",
              "config": {"strategy": "$inputs.version_strategy"}},
             {"id": "rt", "name": "Trigger Retrain Signal",
              "operator": "ops.retrain_signal",
              "config": {"model_id": "$inputs.model_id"}},
             {"id": "ev", "name": "Re-evaluate",
              "operator": "evaluation.run_suite",
              "config": {"model_id": "$inputs.model_id"}},
             {"id": "wr", "name": "Persist Iteration Log",
              "operator": "export.write_iteration_log"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["badcases", "relabeled", "merged",
                  "retrain_signals", "eval_score",
                  "duration_seconds"],
     ),
     "nodes": [_n("bc", "badcase", "feedback", "ev"),
               _n("rl", "relabel", "feedback", "bc"),
               _n("hr", "human_review", "annotation", "rl"),
               _n("mg", "merge_version", "dataset", "hr"),
               _n("rt", "retrain_signal", "ops", "mg"),
               _n("ev", "reevaluate", "evaluation", "rt"),
               _n("wr", "iteration_log", "export", "ev"),
               _n("up", "oss_upload", "export", "wr")]},
]


__all__ = ["_FEEDBACK_TEMPLATES"]