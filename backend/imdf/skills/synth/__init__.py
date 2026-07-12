"""Synth skill registry — 17 skills (synth/*)."""

from __future__ import annotations

from typing import Dict, List

from .synth_caption_expand import caption_expand
from .synth_qa_generate import qa_generate
from .synth_dialog_generate import dialog_generate
from .synth_summary import summary
from .synth_translate_en import translate_en
from .synth_translate_zh import translate_zh
from .synth_back_translate import back_translate
from .synth_paraphrase import paraphrase
from .synth_style_transfer import style_transfer
from .synth_image_caption import image_caption
from .synth_image_edit_caption import image_edit_caption
from .synth_video_caption import video_caption
from .synth_video_temporal import video_temporal
from .synth_audio_caption import audio_caption
from .synth_3d_caption import three_d_caption
from .synth_neg_prompt import neg_prompt
from .synth_seed_expand import seed_expand

__all__ = [
    "caption_expand",
    "qa_generate",
    "dialog_generate",
    "summary",
    "translate_en",
    "translate_zh",
    "back_translate",
    "paraphrase",
    "style_transfer",
    "image_caption",
    "image_edit_caption",
    "video_caption",
    "video_temporal",
    "audio_caption",
    "three_d_caption",
    "neg_prompt",
    "seed_expand",
    "SYNTH_SKILLS",
    "BY_MODULE",
    "list_synth_skills",
    "get_synth_skill",
]

# ── Registry metadata ────────────────────────────────────────────────
SYNTH_SKILLS: List[dict] = [
    {
        "module": "synth_caption_expand",
        "function": "caption_expand",
        "name_zh": "短描述扩写为长描述",
        "category": "synth",
    },
    {
        "module": "synth_qa_generate",
        "function": "qa_generate",
        "name_zh": "QA 对生成",
        "category": "synth",
    },
    {
        "module": "synth_dialog_generate",
        "function": "dialog_generate",
        "name_zh": "多轮对话生成",
        "category": "synth",
    },
    {
        "module": "synth_summary",
        "function": "summary",
        "name_zh": "文本摘要",
        "category": "synth",
    },
    {
        "module": "synth_translate_en",
        "function": "translate_en",
        "name_zh": "英译中",
        "category": "synth",
    },
    {
        "module": "synth_translate_zh",
        "function": "translate_zh",
        "name_zh": "中译英",
        "category": "synth",
    },
    {
        "module": "synth_back_translate",
        "function": "back_translate",
        "name_zh": "回译增强",
        "category": "synth",
    },
    {
        "module": "synth_paraphrase",
        "function": "paraphrase",
        "name_zh": "文本改写",
        "category": "synth",
    },
    {
        "module": "synth_style_transfer",
        "function": "style_transfer",
        "name_zh": "风格迁移",
        "category": "synth",
    },
    {
        "module": "synth_image_caption",
        "function": "image_caption",
        "name_zh": "图像描述合成",
        "category": "synth",
    },
    {
        "module": "synth_image_edit_caption",
        "function": "image_edit_caption",
        "name_zh": "图像编辑指令生成",
        "category": "synth",
    },
    {
        "module": "synth_video_caption",
        "function": "video_caption",
        "name_zh": "视频描述合成",
        "category": "synth",
    },
    {
        "module": "synth_video_temporal",
        "function": "video_temporal",
        "name_zh": "时序动作描述",
        "category": "synth",
    },
    {
        "module": "synth_audio_caption",
        "function": "audio_caption",
        "name_zh": "音频描述合成",
        "category": "synth",
    },
    {
        "module": "synth_3d_caption",
        "function": "three_d_caption",
        "name_zh": "3D 场景描述",
        "category": "synth",
    },
    {
        "module": "synth_neg_prompt",
        "function": "neg_prompt",
        "name_zh": "负向 prompt 生成",
        "category": "synth",
    },
    {
        "module": "synth_seed_expand",
        "function": "seed_expand",
        "name_zh": "种子词扩展",
        "category": "synth",
    },
]

BY_MODULE: Dict[str, str] = {entry['module']: entry['function'] for entry in SYNTH_SKILLS}


def list_synth_skills() -> List[dict]:
    """Return a copy of the SYNTH_SKILLS registry."""
    return list(SYNTH_SKILLS)


def get_synth_skill(module_name: str):
    """Look up a synth skill by its module name (e.g. ``synth_caption_expand``).

    Returns the function, or raises ``KeyError`` if not found.
    """
    fn_name = BY_MODULE.get(module_name)
    if fn_name is None:
        raise KeyError(f"synth skill not found: {module_name}")
    return globals()[fn_name]

