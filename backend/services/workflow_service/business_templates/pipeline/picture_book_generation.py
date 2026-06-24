"""P3-6.5-W2: Hybrid Business Pipeline — Picture Book Generation.

Picture book SFT pipeline: story text -> page split -> per-page T2I
illustration + TTS -> human review -> PDF compose -> OSS upload.

Category: pipeline
Stage coverage: scripting -> generation -> audio -> review -> export

Improvements over ``tpl-biz-mm-005``:
  * Character consistency (IP-Adapter per book character)
  * Per-page quality gate (CLIP + aesthetic)
  * Multi-language TTS with per-language voice selection
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-pipe-h10",
    "category": "pipeline",
    "name": "Picture Book Generation Pipeline (Hybrid)",
    "tags": ["picture-book", "story", "illustration", "tts", "ip-adapter"],
    "description": (
        "Picture book SFT: story parse -> page split -> character "
        "consistency anchor (IP-Adapter) -> per-page T2I illustration -> "
        "multi-lang TTS -> page quality gate -> human review -> PDF "
        "compose -> OSS upload."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "story_id": {"type": "string", "required": True},
            "illustration_model": {"type": "string",
                                    "default": "sdxl-1.0"},
            "character_reference": {"type": "object",
                                     "default": None,
                                     "description": "Optional IP-Adapter "
                                                    "reference"},
            "tts_model": {"type": "string", "default": "cosyvoice"},
            "language": {"type": "string", "default": "zh",
                         "enum": ["zh", "en", "ja", "ko"]},
            "style": {"type": "string", "default": "watercolor"},
            "min_page_clip": {"type": "float", "default": 0.22},
            "oss_bucket": {"type": "string", "default": "picturebook"},
        },
        outputs=["book.pdf", "pages/*.jpg", "audio/*.wav",
                 "manifest.json", "character_anchors.json"],
        steps=[
            {"id": "st", "name": "Story Parse + Page Split",
             "operator": "scripting.page_split",
             "config": {"story_id": "$inputs.story_id"}},
            {"id": "ch", "name": "Character Anchor",
             "operator": "preprocessing.character_anchor",
             "config": {"reference": "$inputs.character_reference"}},
            {"id": "t2i", "name": "Per-Page T2I Illustration",
             "operator": "generation.text_to_image",
             "config": {"model": "$inputs.illustration_model",
                        "style": "$inputs.style",
                        "use_ip_adapter":
                            "$inputs.character_reference != None"}},
            {"id": "qa", "name": "Page Quality Gate",
             "operator": "scoring.multimodal_score",
             "config": {"score_keys": ["clip", "aesthetic"],
                        "min_clip": "$inputs.min_page_clip"}},
            {"id": "tts", "name": "Per-Page TTS",
             "operator": "audio.tts",
             "config": {"model": "$inputs.tts_model",
                        "language": "$inputs.language"}},
            {"id": "rv", "name": "Human Page Review",
             "operator": "annotation.review"},
            {"id": "pdf", "name": "Book PDF Compose",
             "operator": "export.compose_picturebook"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"}},
        ],
        metrics=["pages", "illustrations", "audio",
                 "after_quality_gate", "approved",
                 "duration_seconds"],
    ),
    "nodes": [_n("st", "story_parse", "scripting"),
              _n("ch", "character_anchor", "preprocessing", "st"),
              _n("t2i", "page_illustration", "generation", "ch"),
              _n("qa", "page_quality_gate", "scoring", "t2i"),
              _n("tts", "page_tts", "audio", "st"),
              _n("rv", "page_review", "review", "qa", "tts"),
              _n("pdf", "compose_pdf", "export", "rv"),
              _n("up", "oss_upload", "export", "pdf")],
}