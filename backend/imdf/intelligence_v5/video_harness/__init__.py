"""智影 V5 — Video Harness 子包: 短剧创作 (Pavo + 剧大虾)

迁移自 Pavo 平台 + 剧大虾:
- 一句话 → 需求卡片 → 角色/场景/道具 → 分镜 → 视频 → 成片
- 多 Agent 协作 (理解创意 / 生成剧情 / 拆分镜 / 选模型)
- Harness 调度 (局部返工不重做)
- 智能模型路由 (根据任务难度匹配)
- 短剧 Harness (剧情短片功能)
"""
from .project_card import ProjectCard, ProjectType, CardSection
from .character_designer import CharacterDesigner, Character, Scene, Prop
from .storyboard import (
    StoryboardEngine,
    Storyboard,
    Shot,
    ShotType,
    CameraMovement,
    ModelRouter,
    ModelInfo,
    ModelCapability,
    RoutingDecision,
    VideoHarness,
    HarnessStep,
    HarnessPhase,
    VideoProject,
    video_harness,
)

__all__ = [
    "ProjectCard",
    "ProjectType",
    "CardSection",
    "CharacterDesigner",
    "Character",
    "Scene",
    "Prop",
    "StoryboardEngine",
    "Storyboard",
    "Shot",
    "ShotType",
    "CameraMovement",
    "ModelRouter",
    "ModelInfo",
    "ModelCapability",
    "RoutingDecision",
    "VideoHarness",
    "HarnessStep",
    "HarnessPhase",
    "VideoProject",
    "video_harness",
]
