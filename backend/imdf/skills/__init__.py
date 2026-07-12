"""V5 第31章 + 第26章 — imdf Skills 子包: RedFox 4 + Vida 1 Skill 注册.

模块结构:
  * registry.py       — 注册 5 个 Skill (4 redfox + 1 vida)
  * compose.py        — P21 P2 P4 R2 N5: ``chain()`` + ``PipelineStep``
                        组合助手,让 clean / synth / label skills 能
                        顺序串起来 (``clean_pii_remove -> synth_translate_en`` 等)
  * __init__.py       — 暴露 registry 给 backend.imdf.skills.* 调用方

注: 沿用 P19 v5.1-B SkillSpec dataclass 风格,不强行继承 backend.skills.base.Skill
(因为这些 Skill 是函数式而非 class-based,且 RedFox 跨平台 fan-out 的
异步语义与 Skill ABC 的 execute(ctx) 签名有差异)。
"""
from __future__ import annotations

from .compose import PipelineStep, chain
from .registry import (
    EXPORT_CREATEML_SPEC,
    LABELING_EXPORT_SKILLS,
    LABEL_GEOMETRY_3D_SPEC,
    REDFOX_SKILLS,
    RedFoxSkillSpec,
    VIDA_PROACTIVE_ASSIST_SPEC,
    VIDA_SKILLS,
    VidaSkillSpec,
    get_labeling_export_skill,
    get_redfox_skill,
    get_vida_skill,
    list_labeling_export_skills,
    list_redfox_skills,
    list_vida_skills,
)

__all__ = [
    # P21 P2 P4 R2 N5 — skill composition helper
    "PipelineStep",
    "chain",
    # RedFox + Vida registry
    "RedFoxSkillSpec",
    "REDFOX_SKILLS",
    "get_redfox_skill",
    "list_redfox_skills",
    "VidaSkillSpec",
    "VIDA_SKILLS",
    "VIDA_PROACTIVE_ASSIST_SPEC",
    "get_vida_skill",
    "list_vida_skills",
    "EXPORT_CREATEML_SPEC",
    "LABEL_GEOMETRY_3D_SPEC",
    "LABELING_EXPORT_SKILLS",
    "list_labeling_export_skills",
    "get_labeling_export_skill",
]