"""P3-6.5-W2: Hybrid Business Pipeline — SFT Video Caption.

Video caption SFT pipeline with shot detection, keyframe sampling,
per-shot VLM caption, human review, and ShareGPT export.

Category: pipeline
Stage coverage: collection -> preprocessing -> generation -> review -> export

Improvements over ``tpl-biz-pipe-004``:
  * Audio-aware captioning (uses ASR transcript as context)
  * Per-shot CLIP score (filters low-quality shots)
  * Optional long-video chunking for >5min videos
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h04",
    "category": "pipeline",
    "name": "SFT Video Caption Pipeline (Hybrid)",
    "tags": ["sft", "video-caption", "sharegpt", "asr-context"],
    "description": (
        "Video caption SFT: video collect -> shot detection (TransNetV2) -> "
        "keyframe sample -> ASR transcript extract (audio-aware) -> "
        "per-shot VLM caption -> CLIP score -> human review -> "
        "ShareGPT export."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "sources": {"type": "array<object>", "required": True},
            "shot_method": {"type": "string",
                            "default": "transnetv2",
                            "enum": ["transnetv2", "pyscenedetect",
                                     "autoshot"]},
            "fps_sample": {"type": "int", "default": 1,
                           "min": 1, "max": 10},
            "use_asr_context": {"type": "boolean", "default": True},
            "asr_model": {"type": "string",
                          "default": "whisper-large-v3"},
            "min_shot_clip": {"type": "float", "default": 0.20,
                              "min": 0.0, "max": 1.0},
            "max_video_seconds": {"type": "int", "default": 300,
                                   "description": "Long-video chunk size"},
            "oss_bucket": {"type": "string", "default": "sft-vcap"},
        },
        outputs=["sharegpt.json", "shot_meta.json",
                 "asr_transcripts.json", "stats.json"],
        steps=[
            {"id": "col", "name": "Video Collect",
             "operator": "collection.video_source"},
            {"id": "chk", "name": "Long-Video Chunk",
             "operator": "preprocessing.chunk",
             "config": {"max_seconds": "$inputs.max_video_seconds"}},
            {"id": "sh", "name": "Shot Detection",
             "operator": "preprocessing.shot_detect",
             "config": {"method": "$inputs.shot_method"}},
            {"id": "kf", "name": "Key-Frame Sample",
             "operator": "preprocessing.keyframe_sample",
             "config": {"fps": "$inputs.fps_sample"}},
            {"id": "asr", "name": "ASR Transcript (optional)",
             "operator": "audio.asr",
             "config": {"model": "$inputs.asr_model",
                        "enabled": "$inputs.use_asr_context"}},
            {"id": "cg", "name": "Per-Shot VLM Caption",
             "operator": "annotation.vlm_shot_caption",
             "config": {"use_asr_context": "$inputs.use_asr_context"}},
            {"id": "sc", "name": "Shot CLIP Score",
             "operator": "scoring.clip_filter",
             "config": {"min": "$inputs.min_shot_clip"}},
            {"id": "rv", "name": "Human Review",
             "operator": "annotation.review"},
            {"id": "wr", "name": "ShareGPT Export",
             "operator": "format.sharegpt_export"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["videos", "shots", "keyframes", "captions",
                 "approved", "duration_seconds"],
    ),
    "nodes": [_n("col", "video_collect", "collection"),
              _n("chk", "long_video_chunk", "preprocessing", "col"),
              _n("sh", "shot_detect", "preprocessing", "chk"),
              _n("kf", "keyframe_sample", "preprocessing", "sh"),
              _n("asr", "asr_transcript", "audio", "kf"),
              _n("cg", "vlm_shot_caption", "annotation", "kf", "asr"),
              _n("sc", "shot_clip_score", "scoring", "cg"),
              _n("rv", "review", "review", "sc"),
              _n("wr", "sharegpt_export", "export", "rv"),
              _n("up", "oss_upload", "export", "wr")],
}