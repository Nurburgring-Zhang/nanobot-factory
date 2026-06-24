"""P3-6-W1: business feedback template — Bad Case auto analysis.

Pipeline (调用 eval + scoring 自动分析 Bad Case):
  1.  load_eval       - 加载评测输出 (model_id + dataset_id + eval_run_id)
  2.  reward_score    - reward model 评分
  3.  clip_score      - CLIP text-image 对齐评分
  4.  threshold_flt   - 双阈值过滤 (reward<r_th AND clip<c_th -> badcase)
  5.  embedding       - 文本/图像 embedding (CLIP/SBERT)
  6.  cluster         - embedding KMeans 聚类 (auto k via silhouette)
  7.  root_cause      - 每簇打 root_cause tag (规则 + LLM)
  8.  report          - 输出 badcase.jsonl + clusters.json + root_cause.csv
  9.  oss_upload      - 上传到 badcase bucket

vs basic_templates/feedback.py::tpl-biz-fb-001: 本模板细化 reward + clip
  双路评分 + auto-k 聚类 + LLM 根因打标。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-fb-001",
    "name": "Bad Case Auto Analysis (商业级)",
    "category": "feedback",
    "description": (
        "调用 eval + scoring 自动分析 Bad Case:reward+CLIP 双路评分 + "
        "auto-k 聚类 + LLM 根因打标 + 报告导出。"
    ),
    "tags": ["bad-case", "failure", "analysis",
             "cluster", "reward", "clip", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "eval_dataset_id": {"type": "string", "required": True,
                            "description": "评测输出 dataset UUID"},
        "model_id": {"type": "string", "required": True,
                     "description": "被评测模型 ID"},
        "eval_run_id": {"type": "string", "required": False,
                        "description": "指定 eval run,空=最新"},
        "reward_model": {"type": "string", "default": "skywork-rm"},
        "clip_model": {"type": "string", "default": "clip-vit-l"},
        "reward_threshold": {"type": "float", "default": 0.3,
                              "description": "reward < 此值视为 badcase"},
        "clip_threshold": {"type": "float", "default": 0.18,
                            "description": "CLIP < 此值视为 badcase"},
        "embedding_model": {"type": "string", "default": "clip-vit-l"},
        "cluster_method": {"type": "string", "default": "kmeans",
                            "enum": ["kmeans", "hdbscan", "agglomerative"]},
        "auto_k": {"type": "boolean", "default": True,
                   "description": "True=用 silhouette 自动选 k"},
        "root_cause_model": {"type": "string", "default": "qwen-vl-max",
                              "description": "LLM 根因打标模型"},
        "sample_per_cluster": {"type": "int", "default": 5,
                                "description": "LLM 打标每簇采样数"},
        "oss_bucket": {"type": "string", "default": "badcase"},
        "oss_key_prefix": {"type": "string", "default": "badcase/"},
    },
    "outputs": [
        "badcase.jsonl",
        "clusters.json",
        "root_cause.csv",
        "embedding.npy",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Eval Outputs",
         "operator": "dataset.load_eval",
         "config": {"dataset_id": "$inputs.eval_dataset_id",
                    "model_id": "$inputs.model_id",
                    "run_id": "$inputs.eval_run_id"}},
        {"id": "rm", "name": "Reward Score",
         "operator": "scoring.reward",
         "config": {"model": "$inputs.reward_model"}},
        {"id": "cs", "name": "CLIP Score",
         "operator": "scoring.clip",
         "config": {"model": "$inputs.clip_model"}},
        {"id": "bf", "name": "Badcase Threshold Filter",
         "operator": "dataset.badcase_filter",
         "config": {"reward_max": "$inputs.reward_threshold",
                    "clip_max": "$inputs.clip_threshold",
                    "mode": "and"}},
        {"id": "em", "name": "Embedding (CLIP)",
         "operator": "embedding.clip",
         "config": {"model": "$inputs.embedding_model"}},
        {"id": "cl", "name": "Cluster Bad Cases",
         "operator": "analysis.cluster",
         "config": {"method": "$inputs.cluster_method",
                    "auto_k": "$inputs.auto_k"}},
        {"id": "rc", "name": "Root-cause Tag (LLM)",
         "operator": "analysis.root_cause_llm",
         "config": {"model": "$inputs.root_cause_model",
                    "sample_per_cluster": "$inputs.sample_per_cluster"}},
        {"id": "wr", "name": "Bad-case Report",
         "operator": "export.write_badcase",
         "config": {"include_embedding": True}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "eval_total", "reward_scored", "clip_scored",
        "badcases", "clusters", "root_causes_identified",
        "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]