"""Collection template: YouTube video batch download.

Pipeline:
  1. video_list    — 输入 video_id / playlist_id / channel_url 列表
  2. metadata_fetch — yt-dlp 拉元数据 (title, duration, channel)
  3. filter        — 按 duration / resolution / caption 过滤
  4. download      — yt-dlp 下载 (默认 1080p mp4)
  5. transcribe    — 调用 ASR (whisper) 生成字幕/对齐
  6. oss_upload    — 上传到对象存储
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-coll-002",
    "name": "YouTube Video Batch (视频批量下载)",
    "category": "collection",
    "description": (
        "批量下载 YouTube 视频列表, 支持按元数据过滤, "
        "可选 ASR 转写生成字幕, 输出 manifest.jsonl。"
    ),
    "tags": ["youtube", "video", "collection", "asr"],
    "version": "1.0.0",
    "inputs": {
        "video_ids": {"type": "array<string>", "required": True,
                       "description": "YouTube video IDs 或完整 URL"},
        "max_duration_sec": {"type": "int", "default": 600},
        "min_duration_sec": {"type": "int", "default": 5},
        "preferred_resolution": {"type": "string", "default": "1080p"},
        "run_asr": {"type": "bool", "default": False},
        "oss_bucket": {"type": "string", "default": "raw-videos"},
    },
    "outputs": ["manifest.jsonl", "transcripts/*.vtt"],
    "steps": [
        {"id": "list", "name": "Video List",
         "operator": "youtube.list_resolve",
         "config": {"ids": "$inputs.video_ids"}},
        {"id": "meta", "name": "Fetch Metadata",
         "operator": "youtube.fetch_metadata",
         "config": {"fields": ["title", "channel", "duration",
                                "resolution", "captions"]}},
        {"id": "flt", "name": "Filter",
         "operator": "filter.duration_range",
         "config": {"min_sec": "$inputs.min_duration_sec",
                    "max_sec": "$inputs.max_duration_sec"}},
        {"id": "dl", "name": "Download",
         "operator": "youtube.download",
         "config": {"format": "$inputs.preferred_resolution",
                    "merge_output_format": "mp4"}},
        {"id": "asr", "name": "ASR (optional)",
         "operator": "asr.transcribe",
         "config": {"enabled": "$inputs.run_asr",
                    "model": "whisper-large-v3",
                    "language": "auto"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "collection/youtube/",
                    "manifest": True}},
    ],
    "metrics": ["videos_resolved", "videos_downloaded",
                "total_bytes", "asr_minutes", "duration_seconds"],
}


__all__ = ["TEMPLATE"]