"""Clean skill registry — 17 imdf clean/* skills.

Importable via::

    from backend.imdf.skills.clean import (
        CLEAN_SKILLS,
        clean_dedupe_hash,
        ...
        list_clean_skills,
        get_clean_skill,
    )

Each module exposes one async function ``clean_<name>(input: SkillInput)
-> SkillOutput`` plus Pydantic ``*Input / *Output`` models.

Notes
-----
* Offline-mode-safe: each handler returns a deterministic mock when no
  remote endpoint is reachable — see ``_base.safe_httpx_call``.
* Per-skill ``SkillSpec.id`` follows the convention ``skill_clean_<name>``
  so it composes with ``backend.skills_builtin.py``.
* The conftest.py at this directory patches the broken upstream registry
  so this package can be imported even when ``backend.imdf.skills``
  has failing cross-module imports.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from backend.skills import SkillInput, SkillOutput, SkillSpec  # type: ignore

from . import (
    clean_audio_denoise,
    clean_csv_normalize,
    clean_dedupe_embed,
    clean_dedupe_hash,
    clean_face_blur,
    clean_html_strip,
    clean_json_validate,
    clean_logo_watermark,
    clean_markdown_lint,
    clean_nsfw_detect,
    clean_pii_remove,
    clean_plate_blur,
    clean_subtitle_sync,
    clean_text_normalize,
    clean_video_stabilize,
    clean_xml_strip,
    clean_yaml_lint,
)


def _spec(name: str, desc: str, inputs: Dict[str, str], outputs: Dict[str, str]) -> SkillSpec:
    return SkillSpec(
        id=f"skill_{name}",
        name=name,
        category="clean",
        trigger_phrases=[name.replace("_", " ")],
        inputs=inputs,
        outputs=outputs,
        description=desc,
        enabled=True,
        version="1.0.0",
        dependencies=[],
    )


CLEAN_SKILLS: List[SkillSpec] = [
    _spec("clean_dedupe_hash", "Perceptual hash (pHash/dHash) deduplication",
          {"image_url": "string", "hash_size": "int?", "method": "string?"},
          {"hash": "string", "duplicates": "list", "groups": "list"}),
    _spec("clean_dedupe_embed", "Vector embedding (CLIP) deduplication",
          {"items": "list", "threshold": "float?", "dim": "int?"},
          {"duplicates": "list", "embeddings": "list"}),
    _spec("clean_text_normalize", "Text normalization (unicode/case/punct)",
          {"text": "string", "lowercase": "bool?", "strip_punct": "bool?"},
          {"normalized": "string", "changes": "list"}),
    _spec("clean_html_strip", "Strip HTML tags",
          {"html": "string", "keep_tags": "list?"},
          {"text": "string", "stripped_tags": "int"}),
    _spec("clean_markdown_lint", "Markdown syntax checker",
          {"markdown": "string", "max_line_length": "int?"},
          {"issues": "list", "error_count": "int"}),
    _spec("clean_json_validate", "JSON Schema validation",
          {"document": "object", "schema": "object"},
          {"valid": "bool", "errors": "list"}),
    _spec("clean_yaml_lint", "YAML syntax checker",
          {"yaml": "string", "strict_indent": "bool?"},
          {"valid": "bool", "issues": "list", "parsed": "bool"}),
    _spec("clean_csv_normalize", "CSV field normalization",
          {"csv": "string", "delimiter": "string?", "lowercase_headers": "bool?"},
          {"headers": "list", "rows": "list", "column_count": "int"}),
    _spec("clean_xml_strip", "XML namespace cleanup",
          {"xml": "string", "remove_namespaces": "bool?"},
          {"cleaned_xml": "string", "elements": "int", "namespaces": "list"}),
    _spec("clean_face_blur", "Auto face blurring",
          {"image_url": "string", "blur_strength": "int?"},
          {"faces": "list"}),
    _spec("clean_plate_blur", "Auto license-plate blurring",
          {"image_url": "string", "region_hint": "string?"},
          {"plates": "list"}),
    _spec("clean_logo_watermark", "Logo / watermark detection",
          {"image_url": "string", "min_area_ratio": "float?"},
          {"detections": "list", "has_watermark": "bool"}),
    _spec("clean_nsfw_detect", "NSFW content detection",
          {"image_url": "string", "threshold": "float?"},
          {"nsfw_score": "float", "label": "string", "flagged": "bool"}),
    _spec("clean_pii_remove", "PII redaction (email/phone/ip/id/cards)",
          {"text": "string", "replacement": "string?"},
          {"redacted": "string", "matches": "list"}),
    _spec("clean_audio_denoise", "Audio denoising",
          {"audio_url": "string", "strength": "float?"},
          {"output_url": "string", "snr_in": "float", "snr_out": "float"}),
    _spec("clean_video_stabilize", "Video stabilization",
          {"video_url": "string", "smoothing": "float?"},
          {"output_url": "string", "frames_analyzed": "int"}),
    _spec("clean_subtitle_sync", "Subtitle timing alignment",
          {"srt": "string", "offset_ms": "int?", "audio_url": "string?"},
          {"srt": "string", "cue_count": "int", "delta_ms": "int"}),
]


_HANDLER_MAP: Dict[str, Callable[[SkillInput], "Any"]] = {
    "clean_dedupe_hash": clean_dedupe_hash.clean_dedupe_hash,
    "clean_dedupe_embed": clean_dedupe_embed.clean_dedupe_embed,
    "clean_text_normalize": clean_text_normalize.clean_text_normalize,
    "clean_html_strip": clean_html_strip.clean_html_strip,
    "clean_markdown_lint": clean_markdown_lint.clean_markdown_lint,
    "clean_json_validate": clean_json_validate.clean_json_validate,
    "clean_yaml_lint": clean_yaml_lint.clean_yaml_lint,
    "clean_csv_normalize": clean_csv_normalize.clean_csv_normalize,
    "clean_xml_strip": clean_xml_strip.clean_xml_strip,
    "clean_face_blur": clean_face_blur.clean_face_blur,
    "clean_plate_blur": clean_plate_blur.clean_plate_blur,
    "clean_logo_watermark": clean_logo_watermark.clean_logo_watermark,
    "clean_nsfw_detect": clean_nsfw_detect.clean_nsfw_detect,
    "clean_pii_remove": clean_pii_remove.clean_pii_remove,
    "clean_audio_denoise": clean_audio_denoise.clean_audio_denoise,
    "clean_video_stabilize": clean_video_stabilize.clean_video_stabilize,
    "clean_subtitle_sync": clean_subtitle_sync.clean_subtitle_sync,
}


def list_clean_skills() -> List[SkillSpec]:
    """Return all 17 registered clean skills as SkillSpec objects."""
    return list(CLEAN_SKILLS)


def get_clean_skill(name: str) -> Optional[SkillSpec]:
    """Look up a clean skill by its short name (without ``skill_`` prefix)."""
    for spec in CLEAN_SKILLS:
        if spec.id == f"skill_{name}" or spec.name == name:
            return spec
    return None


def get_clean_handler(name: str) -> Optional[Callable[[SkillInput], "Any"]]:
    """Return the async handler for ``name`` (short form, no ``skill_`` prefix)."""
    return _HANDLER_MAP.get(name)


__all__ = [
    "SkillInput",
    "SkillOutput",
    "SkillSpec",
    "CLEAN_SKILLS",
    "list_clean_skills",
    "get_clean_skill",
    "get_clean_handler",
    "clean_audio_denoise",
    "clean_csv_normalize",
    "clean_dedupe_embed",
    "clean_dedupe_hash",
    "clean_face_blur",
    "clean_html_strip",
    "clean_json_validate",
    "clean_logo_watermark",
    "clean_markdown_lint",
    "clean_nsfw_detect",
    "clean_pii_remove",
    "clean_plate_blur",
    "clean_subtitle_sync",
    "clean_text_normalize",
    "clean_video_stabilize",
    "clean_xml_strip",
    "clean_yaml_lint",
]
