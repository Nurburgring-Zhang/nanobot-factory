"""Cleaning template: Video dedup (视频去重清洗).

Pipeline:
  1.  probe        - ffprobe 提取元数据 (时长/codec/fps)
  2.  keyframe     - 抽关键帧 (1 fps)
  3.  frame_hash   - pHash 每帧
  4.  cluster      - 按帧序列相似度聚类
  5.  pick_rep     - 选每类代表帧
  6.  near_dup     - 接近重复片段检测 (SSIM)
  7.  trim         - 裁剪近重复片段 (可选)
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-cln-002",
    "name": "Video Dedup Clean (视频去重清洗)",
    "category": "cleaning",
    "description": (
        "基于关键帧 pHash 序列相似度的视频去重, 可选裁剪近重复片段。"
    ),
    "tags": ["video", "cleaning", "dedup", "phash"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "keyframe_fps": {"type": "float", "default": 1.0},
        "phash_bits": {"type": "int", "default": 64},
        "hamming_threshold": {"type": "int", "default": 8},
        "near_dup_ssim": {"type": "float", "default": 0.92},
        "trim_near_dup": {"type": "bool", "default": False},
        "oss_bucket": {"type": "string", "default": "cleaned-videos"},
    },
    "outputs": ["clean_manifest.jsonl",
                "dup_pairs.json",
                "stats.json"],
    "steps": [
        {"id": "probe", "name": "ffprobe",
         "operator": "video.ffprobe",
         "config": {"fields": ["duration", "codec", "fps",
                                "width", "height", "bit_rate"]}},
        {"id": "kf", "name": "Extract Keyframes",
         "operator": "video.extract_keyframes",
         "config": {"fps": "$inputs.keyframe_fps",
                    "method": "scene-adaptive"}},
        {"id": "fh", "name": "Frame Hash",
         "operator": "image.phash",
         "config": {"hash_bits": "$inputs.phash_bits"}},
        {"id": "cl", "name": "Cluster by Sequence",
         "operator": "video.cluster_keyframes",
         "config": {"hamming_threshold": "$inputs.hamming_threshold",
                    "min_chain_len": 3}},
        {"id": "rep", "name": "Pick Representative",
         "operator": "video.pick_rep",
         "config": {"strategy": "longest",
                    "tie_break": "highest_bitrate"}},
        {"id": "nd", "name": "Near-Dup Detect",
         "operator": "video.near_dup",
         "config": {"ssim_threshold": "$inputs.near_dup_ssim",
                    "min_window_sec": 2.0}},
        {"id": "trim", "name": "Trim Near-Dup",
         "operator": "video.trim",
         "config": {"enabled": "$inputs.trim_near_dup",
                    "policy": "keep_longest"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "cleaning/video_dedup/",
                    "manifest": True}},
    ],
    "metrics": ["in_total", "out_total", "dup_clusters",
                "near_dup_segments", "duration_seconds"],
}


__all__ = ["TEMPLATE"]