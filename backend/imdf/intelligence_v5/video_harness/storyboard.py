"""智影 V5 — 智能分镜 + 模型路由 + 视频 Harness"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .character_designer import Character, Scene, Prop, CharacterDesigner
from .project_card import ProjectCard, ProjectType, auto_generate_card

logger = logging.getLogger(__name__)


class ShotType(str, Enum):
    """镜头类型"""
    WIDE = "wide"               # 远景
    MEDIUM = "medium"           # 中景
    CLOSE_UP = "close_up"       # 特写
    EXTREME_CLOSE_UP = "extreme_close_up"  # 大特写
    OVER_SHOULDER = "over_shoulder"  # 过肩
    POV = "pov"                 # 第一人称
    AERIAL = "aerial"           # 航拍
    TWO_SHOT = "two_shot"       # 双人
    GROUP = "group"             # 群像
    INSERT = "insert"           # 插入镜头 (特写细节)
    ESTABLISHING = "establishing"  # 建立镜头


class CameraMovement(str, Enum):
    """运镜"""
    STATIC = "static"           # 固定
    PAN = "pan"                 # 摇
    TILT = "tilt"               # 俯仰
    DOLLY = "dolly"             # 推拉
    TRACK = "track"             # 横移
    ZOOM_IN = "zoom_in"         # 推
    ZOOM_OUT = "zoom_out"       # 拉
    CRANE = "crane"             # 摇臂
    HANDHELD = "handheld"       # 手持
    STEADICAM = "steadicam"     # 稳定器
    WHIP_PAN = "whip_pan"       # 甩镜


@dataclass
class Shot:
    """单个镜头 — 剧大虾/Pavo 风格"""

    order: int = 0
    shot_id: str = field(default_factory=lambda: f"sh-{uuid.uuid4().hex[:8]}")
    description: str = ""  # 镜头描述
    duration_sec: float = 3.0
    shot_type: ShotType = ShotType.MEDIUM
    camera_movement: CameraMovement = CameraMovement.STATIC
    character_ids: List[str] = field(default_factory=list)  # 涉及角色
    scene_id: str = ""           # 场景
    prop_ids: List[str] = field(default_factory=list)      # 道具
    dialogue: str = ""          # 对白
    action: str = ""            # 动作描述
    emotion: str = ""           # 情绪
    composition: str = ""       # 构图 (e.g., "rule of thirds", "center")
    # 提示词
    image_prompt: str = ""      # 用于图像生成
    video_prompt: str = ""      # 用于视频生成
    audio_prompt: str = ""      # 音频/对白
    # 状态
    status: str = "draft"  # draft / image_ready / video_ready / completed
    image_url: str = ""
    video_url: str = ""
    feedback: str = ""          # 评审反馈
    iteration: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "order": self.order,
            "description": self.description,
            "duration_sec": self.duration_sec,
            "shot_type": self.shot_type.value,
            "camera_movement": self.camera_movement.value,
            "character_ids": self.character_ids,
            "scene_id": self.scene_id,
            "prop_ids": self.prop_ids,
            "dialogue": self.dialogue,
            "action": self.action,
            "emotion": self.emotion,
            "composition": self.composition,
            "image_prompt": self.image_prompt,
            "video_prompt": self.video_prompt,
            "audio_prompt": self.audio_prompt,
            "status": self.status,
            "image_url": self.image_url,
            "video_url": self.video_url,
            "feedback": self.feedback,
            "iteration": self.iteration,
        }


@dataclass
class Storyboard:
    """分镜集 — 一组分镜"""

    name: str
    storyboard_id: str = field(default_factory=lambda: f"sb-{uuid.uuid4().hex[:8]}")
    project_id: str = ""
    card_id: str = ""
    shots: List[Shot] = field(default_factory=list)
    total_duration_sec: float = 0.0
    status: str = "draft"  # draft / approved / generating / completed
    feedback: str = ""
    iteration: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0

    def add_shot(self, shot: Shot):
        shot.order = len(self.shots) + 1
        shot.created_at = time.time()
        self.shots.append(shot)
        self.total_duration_sec += shot.duration_sec
        self.updated_at = time.time()

    def get_shot(self, shot_id: str) -> Optional[Shot]:
        for s in self.shots:
            if s.shot_id == shot_id:
                return s
        return None

    def regenerate_shot(self, shot_id: str, new_prompt: str) -> bool:
        """局部返工 — 不重做整组 (Pavo 关键设计)"""
        shot = self.get_shot(shot_id)
        if not shot:
            return False
        shot.video_prompt = new_prompt
        shot.status = "draft"
        shot.iteration += 1
        shot.updated_at = time.time()
        self.iteration += 1
        self.updated_at = time.time()
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "storyboard_id": self.storyboard_id,
            "name": self.name,
            "project_id": self.project_id,
            "card_id": self.card_id,
            "shot_count": len(self.shots),
            "total_duration_sec": self.total_duration_sec,
            "status": self.status,
            "iteration": self.iteration,
            "shots": [s.to_dict() for s in self.shots],
        }


class StoryboardEngine:
    """分镜引擎 — 从 ProjectCard 自动拆镜"""

    def __init__(self):
        self.storyboards: Dict[str, Storyboard] = {}

    def generate_from_card(
        self,
        card: ProjectCard,
        characters: List[Character],
        scenes: List[Scene],
        props: List[Prop],
    ) -> Storyboard:
        """从需求卡片生成初始分镜"""
        sb = Storyboard(
            name=f"{card.title} 分镜",
            card_id=card.card_id,
            project_id=card.card_id,
            created_at=time.time(),
        )
        # 根据 storyboard_mode 决定分镜数
        mode_to_count = {
            "3_shot": 3,
            "5_shot": 5,
            "8_shot": 8,
            "auto": max(3, card.duration_sec // 10),
            "detailed": max(8, card.duration_sec // 5),
        }
        shot_count = mode_to_count.get(card.storyboard_mode, 5)
        shot_duration = card.duration_sec / shot_count

        # 分配角色到镜头
        protagonist = next((c for c in characters if c.role == "protagonist"), characters[0] if characters else None)
        antagonist = next((c for c in characters if c.role == "antagonist"), None)
        main_scene = scenes[0] if scenes else None

        # 分镜模板 — 按项目类型
        for i in range(shot_count):
            shot = Shot(
                description=self._generate_shot_description(card, i, shot_count, protagonist),
                duration_sec=shot_duration,
                shot_type=self._choose_shot_type(card, i, shot_count),
                camera_movement=self._choose_movement(card, i, shot_count),
                scene_id=main_scene.scene_id if main_scene else "",
                character_ids=[protagonist.character_id] if protagonist else [],
                prop_ids=[],
                dialogue=self._generate_dialogue(card, i, shot_count),
                action=self._generate_action(card, i, shot_count),
                emotion=self._choose_emotion(card, i, shot_count),
                image_prompt=self._build_image_prompt(card, i, shot_count, protagonist, main_scene),
                video_prompt=self._build_video_prompt(card, i, shot_count, protagonist, main_scene),
            )
            sb.add_shot(shot)

        self.storyboards[sb.storyboard_id] = sb
        return sb

    def _generate_shot_description(self, card: ProjectCard, idx: int, total: int, protagonist: Optional[Character]) -> str:
        phase = idx / max(total - 1, 1)
        if phase < 0.2:
            return f"开场: {card.synopsis[:80]}"
        if phase < 0.5:
            return f"发展: {protagonist.name if protagonist else '主角'} 行动推进"
        if phase < 0.8:
            return f"高潮: 冲突/转折"
        return f"结尾: 收束 + 余韵"

    def _choose_shot_type(self, card: ProjectCard, idx: int, total: int) -> ShotType:
        phase = idx / max(total - 1, 1)
        if phase == 0 or phase == 1:
            return ShotType.WIDE
        if 0.4 < phase < 0.6:
            return ShotType.CLOSE_UP
        if phase < 0.3:
            return ShotType.ESTABLISHING
        return ShotType.MEDIUM

    def _choose_movement(self, card: ProjectCard, idx: int, total: int) -> CameraMovement:
        phase = idx / max(total - 1, 1)
        if phase == 0:
            return CameraMovement.ZOOM_OUT
        if phase == 1:
            return CameraMovement.DOLLY
        if 0.3 < phase < 0.7:
            return CameraMovement.ZOOM_IN
        return CameraMovement.STATIC

    def _generate_dialogue(self, card: ProjectCard, idx: int, total: int) -> str:
        if card.project_type == ProjectType.AD:
            if idx == 0:
                return ""
            if idx == total - 1:
                return f"买 {card.title} 就对了!"
            return ""
        if card.project_type == ProjectType.SHORT_DRAMA:
            dialogues = [
                "这到底是怎么回事?",
                "我一定要查清楚!",
                "等等, 让我再想想...",
                "原来如此!",
                "接下来, 该我出手了。",
                "故事, 还在继续...",
            ]
            return dialogues[idx % len(dialogues)]
        return ""

    def _generate_action(self, card: ProjectCard, idx: int, total: int) -> str:
        if card.project_type == ProjectType.AD:
            return f"展示 {card.title} 的核心卖点"
        return f"镜头 {idx+1}: 推进剧情"

    def _choose_emotion(self, card: ProjectCard, idx: int, total: int) -> str:
        phase = idx / max(total - 1, 1)
        if card.mood:
            return card.mood
        if phase < 0.5:
            return "紧张" if card.project_type != ProjectType.AD else "期待"
        return "释放"

    def _build_image_prompt(
        self,
        card: ProjectCard,
        idx: int,
        total: int,
        protagonist: Optional[Character],
        scene: Optional[Scene],
    ) -> str:
        parts = [card.visual_style, card.synopsis[:100]]
        if protagonist:
            parts.append(protagonist.appearance or protagonist.description)
        if scene:
            parts.append(scene.description)
        parts.append(f"shot {idx+1}/{total}")
        return ", ".join(parts)

    def _build_video_prompt(
        self,
        card: ProjectCard,
        idx: int,
        total: int,
        protagonist: Optional[Character],
        scene: Optional[Scene],
    ) -> str:
        return self._build_image_prompt(card, idx, total, protagonist, scene) + ", 流畅运镜, 高质量"

    def regenerate(
        self,
        storyboard_id: str,
        shot_id: str,
        feedback: str = "",
        new_prompt: str = "",
    ) -> Optional[Shot]:
        """局部返工"""
        sb = self.storyboards.get(storyboard_id)
        if not sb:
            return None
        shot = sb.get_shot(shot_id)
        if not shot:
            return None
        if feedback:
            shot.feedback = feedback
        if new_prompt:
            shot.video_prompt = new_prompt
        shot.status = "draft"
        shot.iteration += 1
        shot.updated_at = time.time()
        sb.iteration += 1
        sb.updated_at = time.time()
        return shot


# ===== 模型路由 =====
class ModelCapability(str, Enum):
    """模型能力"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    EMBEDDING = "embedding"


@dataclass
class ModelInfo:
    """模型信息"""

    name: str
    model_id: str
    provider: str  # "Agnes" | "OpenAI" | "StableDiffusion" | ...
    capabilities: List[ModelCapability]
    quality_score: float = 0.7  # 0-1
    speed_score: float = 0.5   # 0-1 (1=最快)
    cost_per_call: float = 0.0
    max_resolution: str = ""  # e.g., "4K" | "1080P"
    max_duration_sec: int = 0  # 视频/音频
    supports_reference: bool = False  # 多参考图
    supports_audio_sync: bool = False  # 音画同步
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingDecision:
    """路由决策"""

    selected_model: ModelInfo
    reasoning: str
    estimated_quality: float
    estimated_cost: float
    alternatives: List[ModelInfo] = field(default_factory=list)
    confidence: float = 0.0


class ModelRouter:
    """智能模型路由 — 根据任务难度/要求/成本自动选模型"""

    def __init__(self):
        self.models: Dict[str, ModelInfo] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认模型 (来自 Pavo + 剧大虾)"""
        defaults = [
            # Agnes 自研 (免费)
            ModelInfo(
                name="Agnes-2.0-Flash",
                model_id="agnes-2.0-flash",
                provider="Agnes",
                capabilities=[ModelCapability.TEXT],
                quality_score=0.75,
                speed_score=0.95,
                cost_per_call=0.0,
                metadata={"context_window": 1_000_000, "free": True},
            ),
            ModelInfo(
                name="Agnes-Image-2.1-Flash",
                model_id="agnes-image-2.1-flash",
                provider="Agnes",
                capabilities=[ModelCapability.IMAGE],
                quality_score=0.8,
                speed_score=0.85,
                cost_per_call=0.0,
                max_resolution="4K",
                supports_reference=True,
                metadata={"free": True},
            ),
            ModelInfo(
                name="Agnes-Video-2.0",
                model_id="agnes-video-2.0",
                provider="Agnes",
                capabilities=[ModelCapability.VIDEO],
                quality_score=0.7,
                speed_score=0.6,
                cost_per_call=0.0,
                max_duration_sec=15,
                max_resolution="1080P",
                supports_audio_sync=True,
                metadata={"free": True},
            ),
            ModelInfo(
                name="Agnes-Video-2.5-preview",
                model_id="agnes-video-2.5-preview",
                provider="Agnes",
                capabilities=[ModelCapability.VIDEO],
                quality_score=0.85,
                speed_score=0.7,
                cost_per_call=0.0,
                max_duration_sec=15,
                max_resolution="4K",
                supports_reference=True,
                supports_audio_sync=True,
                metadata={"free": True, "preview": True},
            ),
            # 商业 (高质量)
            ModelInfo(
                name="Seedance-2.0",
                model_id="seedance-2.0",
                provider="Bytedance",
                capabilities=[ModelCapability.VIDEO],
                quality_score=0.92,
                speed_score=0.4,
                cost_per_call=0.5,
                max_duration_sec=10,
                max_resolution="4K",
                supports_reference=True,
                supports_audio_sync=True,
                metadata={"premium": True},
            ),
            ModelInfo(
                name="NanoBanana-2",
                model_id="nanobanana-2",
                provider="Google",
                capabilities=[ModelCapability.IMAGE],
                quality_score=0.95,
                speed_score=0.6,
                cost_per_call=0.2,
                max_resolution="4K",
                supports_reference=True,
                metadata={"premium": True},
            ),
            ModelInfo(
                name="GPT-Image-2",
                model_id="gpt-image-2",
                provider="OpenAI",
                capabilities=[ModelCapability.IMAGE],
                quality_score=0.93,
                speed_score=0.55,
                cost_per_call=0.25,
                max_resolution="4K",
                metadata={"premium": True},
            ),
            ModelInfo(
                name="HappyHorse-1.1",
                model_id="happyhorse-1.1",
                provider="HappyHorse",
                capabilities=[ModelCapability.VIDEO],
                quality_score=0.85,
                speed_score=0.5,
                cost_per_call=0.3,
                max_duration_sec=8,
                metadata={"premium": True},
            ),
        ]
        for m in defaults:
            self.models[m.model_id] = m

    def register(self, model: ModelInfo):
        self.models[model.model_id] = model

    def list_models(
        self,
        capability: Optional[ModelCapability] = None,
        free_only: bool = False,
        premium_only: bool = False,
    ) -> List[ModelInfo]:
        candidates = list(self.models.values())
        if capability:
            candidates = [m for m in candidates if capability in m.capabilities]
        if free_only:
            candidates = [m for m in candidates if m.metadata.get("free", False)]
        if premium_only:
            candidates = [m for m in candidates if m.metadata.get("premium", False)]
        return candidates

    def route(
        self,
        capability: ModelCapability,
        difficulty: str = "medium",  # simple/medium/hard/extreme
        max_cost: float = 999,
        require_reference: bool = False,
        require_audio_sync: bool = False,
        prefer_free: bool = True,
    ) -> RoutingDecision:
        """智能路由"""
        candidates = self.list_models(capability=capability)
        if not candidates:
            raise ValueError(f"No model for capability: {capability}")
        # 过滤
        if require_reference:
            candidates = [m for m in candidates if m.supports_reference]
        if require_audio_sync:
            candidates = [m for m in candidates if m.supports_audio_sync]
        if max_cost < 999:
            candidates = [m for m in candidates if m.cost_per_call <= max_cost]
        if not candidates:
            candidates = list(self.models.values())  # fallback
        # 评分
        scored: List[tuple] = []
        difficulty_weight = {"simple": 0.3, "medium": 0.5, "hard": 0.7, "extreme": 0.9}.get(difficulty, 0.5)
        for m in candidates:
            score = 0.0
            # 质量分 (按难度加权)
            score += m.quality_score * 0.5 * (0.5 + difficulty_weight)
            # 速度分
            score += m.speed_score * 0.2
            # 成本分 (越便宜越好)
            if m.cost_per_call == 0:
                score += 0.3
            else:
                score += max(0, 0.3 - m.cost_per_call)
            # 优先免费
            if prefer_free and m.metadata.get("free", False):
                score += 0.1
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return RoutingDecision(
            selected_model=best,
            reasoning=f"难度 {difficulty}, 候选 {len(candidates)}, 评分 {scored[0][0]:.3f}",
            estimated_quality=best.quality_score,
            estimated_cost=best.cost_per_call,
            alternatives=[m for _, m in scored[1:4]],
            confidence=min(scored[0][0] - scored[1][0] if len(scored) > 1 else 0.5, 1.0),
        )

    def get_stats(self) -> Dict[str, Any]:
        by_cap = {}
        for m in self.models.values():
            for c in m.capabilities:
                by_cap[c.value] = by_cap.get(c.value, 0) + 1
        return {
            "total_models": len(self.models),
            "by_capability": by_cap,
            "free_models": sum(1 for m in self.models.values() if m.metadata.get("free", False)),
            "premium_models": sum(1 for m in self.models.values() if m.metadata.get("premium", False)),
        }


# ===== Video Harness 主体 =====
class HarnessPhase(str, Enum):
    """Harness 阶段 — Pavo 流程"""
    CARD = "card"              # 需求卡片
    CHARACTERS = "characters"  # 角色/场景/道具
    STORYBOARD = "storyboard"  # 分镜
    IMAGES = "images"          # 图像生成
    VIDEOS = "videos"          # 视频生成
    AUDIO = "audio"            # 音频/对白
    COMPOSE = "compose"        # 合成
    REVIEW = "review"          # 评审


@dataclass
class HarnessStep:
    """Harness 步骤"""
    phase: HarnessPhase
    name: str
    status: str = "pending"  # pending / in_progress / completed / failed
    started_at: float = 0.0
    completed_at: float = 0.0
    output: Any = None
    error: str = ""
    feedback: str = ""


@dataclass
class VideoProject:
    """视频项目 — 完整生命周期"""

    card: ProjectCard
    project_id: str = field(default_factory=lambda: f"vp-{uuid.uuid4().hex[:10]}")
    characters: List[Character] = field(default_factory=list)
    scenes: List[Scene] = field(default_factory=list)
    props: List[Prop] = field(default_factory=list)
    storyboard: Optional[Storyboard] = None
    steps: List[HarnessStep] = field(default_factory=list)
    final_video_url: str = ""
    duration_sec: float = 0.0
    status: str = "draft"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.card.title,
            "project_type": self.card.project_type.value,
            "status": self.status,
            "character_count": len(self.characters),
            "scene_count": len(self.scenes),
            "prop_count": len(self.props),
            "shot_count": len(self.storyboard.shots) if self.storyboard else 0,
            "final_video_url": self.final_video_url,
            "duration_sec": self.duration_sec,
            "step_count": len(self.steps),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class VideoHarness:
    """视频 Harness — Pavo 流程编排"""

    def __init__(self):
        self.projects: Dict[str, VideoProject] = {}
        self.character_designer = CharacterDesigner()
        self.storyboard_engine = StoryboardEngine()
        self.model_router = ModelRouter()

    def create_project(self, user_prompt: str) -> VideoProject:
        """从一句话创建项目"""
        card = auto_generate_card(user_prompt)
        card.confirm()  # auto-confirm 简化 (真实环境先确认)
        project = VideoProject(
            card=card,
            created_at=time.time(),
            updated_at=time.time(),
            status="card_confirmed",
        )
        self.projects[project.project_id] = project
        return project

    def design_characters(
        self,
        project_id: str,
        characters: List[Dict[str, Any]],
        scenes: Optional[List[Dict[str, Any]]] = None,
        props: Optional[List[Dict[str, Any]]] = None,
    ) -> VideoProject:
        """设计角色/场景/道具"""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"project not found: {project_id}")
        # 添加角色
        for c in characters:
            ch = self.character_designer.add_character(
                name=c.get("name", "未命名"),
                role=c.get("role", "supporting"),
                description=c.get("description", ""),
                appearance=c.get("appearance", ""),
                personality=c.get("personality", ""),
                age=c.get("age", ""),
                gender=c.get("gender", ""),
                project_id=project_id,
                reference_image_prompt=c.get("reference_prompt", ""),
            )
            project.characters.append(ch)
        # 场景
        for s in scenes or []:
            sc = self.character_designer.add_scene(
                name=s.get("name", "未命名场景"),
                description=s.get("description", ""),
                location_type=s.get("location_type", ""),
                lighting=s.get("lighting", ""),
                time_of_day=s.get("time_of_day", ""),
                project_id=project_id,
            )
            project.scenes.append(sc)
        # 道具
        for p in props or []:
            pp = self.character_designer.add_prop(
                name=p.get("name", ""),
                description=p.get("description", ""),
                category=p.get("category", "object"),
                project_id=project_id,
            )
            project.props.append(pp)
        self._record_step(project, HarnessPhase.CHARACTERS, "设计角色/场景/道具", "completed")
        project.status = "characters_designed"
        project.updated_at = time.time()
        return project

    def generate_storyboard(self, project_id: str) -> Storyboard:
        """生成分镜"""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"project not found: {project_id}")
        sb = self.storyboard_engine.generate_from_card(
            project.card,
            project.characters,
            project.scenes,
            project.props,
        )
        project.storyboard = sb
        self._record_step(project, HarnessPhase.STORYBOARD, "分镜生成", "completed")
        project.status = "storyboard_ready"
        project.updated_at = time.time()
        return sb

    def regenerate_shot(
        self,
        project_id: str,
        shot_id: str,
        new_prompt: str = "",
        feedback: str = "",
    ) -> Optional[Shot]:
        """局部返工 — Pavo 关键设计"""
        project = self.projects.get(project_id)
        if not project or not project.storyboard:
            return None
        return self.storyboard_engine.regenerate(
            project.storyboard.storyboard_id,
            shot_id,
            feedback=feedback,
            new_prompt=new_prompt,
        )

    def _record_step(self, project: VideoProject, phase: HarnessPhase, name: str, status: str):
        step = HarnessStep(
            phase=phase,
            name=name,
            status=status,
            started_at=time.time(),
            completed_at=time.time() if status in ("completed", "failed") else 0.0,
        )
        project.steps.append(step)

    def list_projects(self) -> List[VideoProject]:
        return list(self.projects.values())

    def get_project(self, project_id: str) -> Optional[VideoProject]:
        return self.projects.get(project_id)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_projects": len(self.projects),
            "characters": self.character_designer.get_stats()["characters"],
            "scenes": self.character_designer.get_stats()["scenes"],
            "props": self.character_designer.get_stats()["props"],
            "storyboards": len(self.storyboard_engine.storyboards),
            "models": self.model_router.get_stats(),
        }


video_harness = VideoHarness()
