"""P3-6.5-W2: Hybrid Multimodal — Image-to-Video.

Image-to-video generation pipeline: text prompt -> T2I -> aesthetic
filter -> I2V animation -> caption overlay -> OSS upload.

Category: multimodal
Improvements over ``tpl-biz-mm-001``:
  * Multi-prompt batching with rate-limit-aware concurrency
  * Motion strength control per-prompt
  * Per-video CLIP coherence score (text <-> video frames)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-mm-h01",
    "category": "multimodal",
    "name": "Image-to-Video Pipeline (Hybrid)",
    "tags": ["i2v", "text2img", "animate", "motion-strength"],
    "description": (
        "Text prompt batch -> T2I (sdxl) -> aesthetic filter -> I2V with "
        "per-prompt motion strength -> caption overlay -> CLIP coherence "
        "score (text <-> video) -> OSS upload."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "prompts": {"type": "array<object>", "required": True,
                         "description": "[{text, motion_strength, "
                                        "duration_sec}]"},
            "t2i_model": {"type": "string",
                          "default": "sdxl-1.0"},
            "i2v_model": {"type": "string",
                          "default": "stable-video-diffusion"},
            "default_fps": {"type": "int", "default": 8},
            "default_duration_sec": {"type": "float", "default": 4.0},
            "min_coherence": {"type": "float", "default": 0.22,
                              "description": "Min text-video CLIP coherence"},
            "max_concurrent": {"type": "int", "default": 4,
                                "description": "Rate-limit aware concurrency"},
            "oss_bucket": {"type": "string", "default": "i2v-out"},
        },
        outputs=["videos/*.mp4", "frames/*.jpg", "manifest.json",
                 "coherence_report.json"],
        steps=[
            {"id": "t2i", "name": "Batch T2I",
             "operator": "generation.text_to_image",
             "config": {"model": "$inputs.t2i_model",
                        "prompts": "$inputs.prompts",
                        "max_concurrent": "$inputs.max_concurrent"}},
            {"id": "q1", "name": "Aesthetic Filter",
             "operator": "cleaning.aesthetic_filter",
             "config": {"min": 5.0}},
            {"id": "i2v", "name": "Per-Prompt I2V",
             "operator": "video_generation.image_to_video",
             "config": {"model": "$inputs.i2v_model",
                        "default_fps": "$inputs.default_fps",
                        "default_duration_sec":
                            "$inputs.default_duration_sec"}},
            {"id": "cap", "name": "Caption Overlay",
             "operator": "postprocessing.caption_overlay"},
            {"id": "coh", "name": "Text-Video Coherence Score",
             "operator": "scoring.text_video_coherence",
             "config": {"min": "$inputs.min_coherence"}},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["i2v", "coh"]},
        ],
        metrics=["prompts", "images", "videos",
                 "avg_coherence", "avg_duration",
                 "duration_seconds"],
    ),
    "nodes": [_n("t2i", "batch_text_to_image", "generation"),
              _n("q1", "aesthetic_filter", "cleaning", "t2i"),
              _n("i2v", "image_to_video", "video_generation", "q1"),
              _n("cap", "caption_overlay", "postprocessing", "i2v"),
              _n("coh", "text_video_coherence", "scoring", "i2v"),
              _n("up", "oss_upload", "export", "cap", "coh")],
}