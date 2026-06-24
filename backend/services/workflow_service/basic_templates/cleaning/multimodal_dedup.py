"""Cleaning template: Multimodal semantic dedup (多模态语义去重).

Pipeline:
  1.  encode_text   - 文本 embedding (bge-m3 / E5)
  2.  encode_image  - 图像 embedding (DINOv2 / CLIP)
  3.  encode_video  - 视频 frame-pooled embedding
  4.  fuse          - 跨模态融合向量
  5.  index         - 向量索引 (pgvector / faiss)
  6.  cluster       - 相似度聚类 (cosine / L2)
  7.  pick_rep      - 选代表 (最长/最高质量)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-cln-005",
    "name": "Multimodal Semantic Dedup (多模态语义去重)",
    "category": "cleaning",
    "description": (
        "基于文本/图像/视频 embedding 的跨模态语义去重, 向量索引 + "
        "聚类, 选代表样本。"
    ),
    "tags": ["multimodal", "cleaning", "embedding", "vector"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "text_model": {"type": "string", "default": "bge-m3"},
        "image_model": {"type": "string", "default": "dinov2-large"},
        "video_model": {"type": "string", "default": "clip-vit-l"},
        "fusion": {"type": "string", "default": "concat",
                    "enum": ["concat", "average", "weighted"]},
        "cosine_threshold": {"type": "float", "default": 0.92},
        "vector_index": {"type": "string", "default": "pgvector",
                          "enum": ["pgvector", "faiss", "milvus"]},
        "oss_bucket": {"type": "string", "default": "cleaned-multimodal"},
    },
    "outputs": ["clean_manifest.jsonl", "dup_clusters.json"],
    "steps": [
        {"id": "et", "name": "Text Embedding",
         "operator": "text.embed",
         "config": {"model": "$inputs.text_model",
                    "normalize": True}},
        {"id": "ei", "name": "Image Embedding",
         "operator": "image.embed",
         "config": {"model": "$inputs.image_model",
                    "normalize": True}},
        {"id": "ev", "name": "Video Embedding",
         "operator": "video.embed",
         "config": {"model": "$inputs.video_model",
                    "frame_pool": "mean",
                    "normalize": True}},
        {"id": "fuse", "name": "Fusion",
         "operator": "vector.fuse",
         "config": {"strategy": "$inputs.fusion"}},
        {"id": "idx", "name": "Build Index",
         "operator": "vector.index",
         "config": {"backend": "$inputs.vector_index",
                    "metric": "cosine"}},
        {"id": "cl", "name": "Cluster",
         "operator": "vector.cluster",
         "config": {"threshold": "$inputs.cosine_threshold",
                    "algorithm": "leiden"}},
        {"id": "rep", "name": "Pick Representative",
         "operator": "vector.pick_rep",
         "config": {"strategy": "centroid",
                    "tie_break": "longest"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/multimodal_dedup/",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "dup_clusters",
                "avg_cluster_size", "duration_seconds"],
}


__all__ = ["TEMPLATE"]