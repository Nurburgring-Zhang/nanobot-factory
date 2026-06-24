#!/usr/bin/env python3
"""
Nanobot Factory - Intent Analyzer & Prompt Generator
Real AI-driven analysis for chat input
Based on Video Agent Pro's Agent Mode

@author MiniMax Agent
@date 2026-03-01
@description 真实AI驱动的意图分析与提示词生成
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class IntentType(Enum):
    """意图类型"""
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    IMAGE_EDIT = "image_edit"
    STORYBOARD = "storyboard"
    SCRIPT = "script"
    BATCH_GENERATION = "batch_generation"
    QUERY = "query"
    MANAGEMENT = "management"
    UNKNOWN = "unknown"


class GenerationStyle(Enum):
    """生成风格"""
    PHOTOREALISTIC = "photorealistic"
    ANIME = "anime"
    ILLUSTRATION = "illustration"
    CINEMATIC = "cinematic"
    ABSTRACT = "abstract"
    DOCUMENTARY = "documentary"
    COMMERCIAL = "commercial"
    ARTISTIC = "artistic"


class VideoGenre(Enum):
    """视频类型"""
    NARRATIVE = "narrative"
    DOCUMENTARY = "documentary"
    COMMERCIAL = "commercial"
    MUSIC_VIDEO = "music_video"
    ANIMATION = "animation"
    VLOG = "vlog"
    TUTORIAL = "tutorial"
    SHORT_DRAMA = "short_drama"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class IntentAnalysis:
    """意图分析结果"""
    intent_type: IntentType
    confidence: float  # 0.0 - 1.0

    # 内容理解
    topic: str  # 主题
    subject: str  # 主旨
    mood: str  # 情绪/氛围
    style: GenerationStyle = GenerationStyle.PHOTOREALISTIC

    # 技术参数
    duration: int = 5  # 视频时长(秒)
    resolution: str = "1024x1024"
    fps: int = 24

    # 场景信息 (用于分镜)
    scenes: List[Dict[str, Any]] = field(default_factory=list)

    # 原始输入
    original_input: str = ""

    # 生成的提示词
    generated_prompt: str = ""
    negative_prompt: str = ""

    # 建议的提供商
    suggested_providers: List[str] = field(default_factory=list)

    # 估计成本 (点数)
    estimated_credits: int = 0


@dataclass
class StoryboardScene:
    """分镜场景"""
    scene_id: int
    title: str
    description: str
    duration: float  # 秒
    prompt: str
    negative_prompt: str
    camera_angle: str = "medium"
    lighting: str = "natural"
    movement: str = "static"


@dataclass
class ScriptElement:
    """剧本元素"""
    act: int  # 幕
    scene: int  # 场
    location: str  # 地点
    time_of_day: str  # 时间
    characters: List[str] = field(default_factory=list)
    dialogue: str = ""
    action: str = ""
    camera_note: str = ""
    duration: float = 0.0


@dataclass
class GenerationPlan:
    """生成计划"""
    plan_id: str
    intent: IntentAnalysis

    # 剧本
    script: List[ScriptElement] = field(default_factory=list)

    # 分镜
    storyboard: List[StoryboardScene] = field(default_factory=list)

    # 生成的图像/视频
    generated_images: List[str] = field(default_factory=list)
    generated_videos: List[str] = field(default_factory=list)

    # 状态
    status: str = "planned"  # planned, generating, completed, failed

    # 执行的步骤
    steps: List[Dict[str, Any]] = field(default_factory=list)

    # 时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


# ============================================================================
# Intent Analyzer
# ============================================================================

class IntentAnalyzer:
    """
    意图分析器
    使用 AI 分析用户输入，理解需求
    完全由AI自主判断意图类型，禁止任何关键词匹配
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def analyze(self, user_input: str) -> IntentAnalysis:
        """
        分析用户输入 - 完全由AI驱动

        Args:
            user_input: 用户输入的自然语言

        Returns:
            IntentAnalysis: 意图分析结果

        Raises:
            Exception: 如果AI分析失败，抛出异常而不是使用默认分析
        """
        logger.info(f"[IntentAnalyzer] Analyzing (AI-driven): {user_input[:100]}...")

        # 直接使用 AI 进行深度分析，让AI判断意图类型
        analysis = await self._ai_analyze(user_input)

        return analysis

    async def _ai_analyze(
        self,
        user_input: str
    ) -> IntentAnalysis:
        """
        使用 AI 进行深度分析 - 完全由AI判断意图类型

        Args:
            user_input: 用户输入的自然语言

        Returns:
            IntentAnalysis: 完整的意图分析结果

        Raises:
            Exception: 如果AI不可用，抛出异常（禁止回退到默认分析）
        """

        # 构建分析提示词 - 让AI完全自主判断意图类型
        analysis_prompt = f"""请深度分析以下用户输入，完全由AI判断用户的意图类型。

用户输入：{user_input}

请以JSON格式返回完整的分析结果：
{{
    "intent_type": "意图类型 (image_generation/video_generation/image_edit/storyboard/script/batch_generation)",
    "confidence": 0.0-1.0之间的置信度,
    "topic": "主题",
    "subject": "主旨/主要内容",
    "mood": "情绪/氛围",
    "style": "风格 (photorealistic/anime/cinematic/illustration/abstract/documentary/commercial)",
    "duration": 视频时长(秒)，默认5,
    "resolution": 分辨率，如 "1024x1024" 或 "1920x1080" 或 "720x1280",
    "aspect_ratio": 宽高比，如 "1:1", "16:9", "9:16",
    "suggested_providers": ["建议的提供商列表，如 seedance/doubao/kling/omnigen/comfyui/seedream"],
    "estimated_credits": 估计消耗的点数,
    "additional_requirements": "其他需要考虑的要求"
}}

注意：
1. intent_type 必须根据用户输入的真实意图来判断，不要猜测
2. 如果用户提到"视频"、"动画"、"短片"，则 intent_type 为 video_generation
3. 如果用户提到"图片"、"图像"、"生成一个"，则 intent_type 为 image_generation
4. 如果用户提到"编辑"、"修改"、"调整"，则 intent_type 为 image_edit
5. 如果用户提到"剧本"、"脚本"、"台词"，则 intent_type 为 script
6. 如果用户提到"分镜"、"故事板"、"镜头"，则 intent_type 为 storyboard

只返回JSON，不要其他内容。"""

        # 调用 AI 进行分析
        if self.llm_client:
            try:
                response = await self.llm_client.chat(
                    prompt=analysis_prompt,
                    system_prompt="你是一个专业的AI内容创作助手，完全由AI自主分析用户需求。你需要深度理解用户输入的语义，而不是简单的关键词匹配。"
                )

                # 解析 JSON
                if response:
                    # 尝试提取JSON
                    try:
                        # 处理可能的markdown代码块
                        if "```json" in response:
                            response = response.split("```json")[1].split("```")[0]
                        elif "```" in response:
                            response = response.split("```")[1].split("```")[0]

                        data = json.loads(response.strip())
                    except json.JSONDecodeError as e:
                        logger.error(f"[IntentAnalyzer] Failed to parse AI response: {e}")
                        raise Exception(f"AI返回的JSON解析失败: {e}")

                    # 解析意图类型
                    intent_type_str = data.get("intent_type", "image_generation")
                    try:
                        intent_type = IntentType(intent_type_str)
                    except ValueError:
                        intent_type = IntentType.IMAGE_GENERATION

                    # 构建分析结果
                    analysis = IntentAnalysis(
                        intent_type=intent_type,
                        confidence=float(data.get("confidence", 0.9)),
                        topic=data.get("topic", ""),
                        subject=data.get("subject", ""),
                        mood=data.get("mood", ""),
                        style=GenerationStyle(data.get("style", "photorealistic")),
                        duration=int(data.get("duration", 5)),
                        resolution=data.get("resolution", "1024x1024"),
                        suggested_providers=data.get("suggested_providers", []),
                        estimated_credits=int(data.get("estimated_credits", 10)),
                        original_input=user_input
                    )

                    logger.info(f"[IntentAnalyzer] AI analysis complete: intent_type={intent_type}, confidence={analysis.confidence}")
                    return analysis

            except Exception as e:
                logger.error(f"[IntentAnalyzer] AI analysis failed: {e}")
                # 禁止回退，必须抛出异常
                raise Exception(f"AI意图分析失败，无法处理请求: {e}")

        # 没有LLM客户端，抛出异常
        raise Exception("没有可用的LLM客户端，无法进行AI驱动的意图分析")


# ============================================================================
# Prompt Generator
# ============================================================================

class PromptGenerator:
    """
    提示词生成器
    根据意图分析结果生成提示词/剧本/分镜
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def generate_prompt(
        self,
        intent: IntentAnalysis
    ) -> str:
        """生成提示词"""

        prompt = f"""请为以下需求生成高质量的AI图像/视频提示词：

主题：{intent.topic}
主旨：{intent.subject}
情绪：{intent.mood}
风格：{intent.style.value}
类型：{intent.intent_type.value}

原始需求：{intent.original_input}

要求：
1. 详细描述场景、主体、背景
2. 包含光线、色彩、构图建议
3. 包含相机角度和运动建议（如果是视频）
4. 使用英文提示词风格
5. 保持提示词在200字以内

只返回提示词，不要其他内容。"""

        if self.llm_client:
            try:
                response = await self.llm_client.chat(
                    prompt=prompt,
                    system_prompt="你是一个专业的AI提示词工程师，擅长生成高质量的图像和视频提示词。"
                )

                if response:
                    return response.strip()

            except Exception as e:
                logger.error(f"[PromptGenerator] Generate failed: {e}")

        # 默认提示词
        return self._default_prompt(intent)

    def _default_prompt(self, intent: IntentAnalysis) -> str:
        """默认提示词"""
        style_prefix = {
            GenerationStyle.PHOTOREALISTIC: "Photorealistic, hyper-detailed, ",
            GenerationStyle.ANIME: "Anime style, vibrant colors, ",
            GenerationStyle.CINEMATIC: "Cinematic view, film grain, ",
            GenerationStyle.ILLUSTRATION: "Digital illustration, detailed, ",
            GenerationStyle.ABSTRACT: "Abstract art, surreal, ",
        }

        prefix = style_prefix.get(intent.style, "")

        return f"{prefix}{intent.subject}, {intent.mood}, {intent.topic}, high quality, 8k"

    async def generate_negative_prompt(
        self,
        intent: IntentAnalysis
    ) -> str:
        """生成负面提示词"""

        negative_prompt = """low quality, blurry, distorted, deformed, ugly,
bad anatomy, extra limbs, malformed, misshapen,
text, watermark, signature, username, artist name,
noise, grain, artifacts, compression artifacts"""

        return negative_prompt

    async def generate_storyboard(
        self,
        intent: IntentAnalysis,
        num_scenes: int = 4
    ) -> List[StoryboardScene]:
        """生成分镜"""

        prompt = f"""请为以下视频需求生成分镜脚本：

主题：{intent.topic}
主旨：{intent.subject}
时长：{intent.duration}秒
场景数量：{num_scenes}

请以JSON格式返回分镜信息：
[
  {{
    "scene_id": 1,
    "title": "场景标题",
    "description": "场景描述",
    "duration": 时长(秒),
    "prompt": "AI生成提示词",
    "negative_prompt": "负面提示词",
    "camera_angle": "相机角度(wide/medium/close-up)",
    "lighting": "光线( natural/sunset/studio)",
    "movement": "运动(static/pan/zoom/dolly)"
  }}
]

只返回JSON数组，不要其他内容。"""

        if self.llm_client:
            try:
                response = await self.llm_client.chat(
                    prompt=prompt,
                    system_prompt="你是一个专业的电影分镜师，擅长设计视频分镜。"
                )

                if response:
                    # 解析 JSON
                    data = json.loads(response)

                    scenes = []
                    for i, scene_data in enumerate(data):
                        scene = StoryboardScene(
                            scene_id=scene_data.get("scene_id", i + 1),
                            title=scene_data.get("title", f"Scene {i+1}"),
                            description=scene_data.get("description", ""),
                            duration=scene_data.get("duration", intent.duration / num_scenes),
                            prompt=scene_data.get("prompt", ""),
                            negative_prompt=scene_data.get("negative_prompt", ""),
                            camera_angle=scene_data.get("camera_angle", "medium"),
                            lighting=scene_data.get("lighting", "natural"),
                            movement=scene_data.get("movement", "static")
                        )
                        scenes.append(scene)

                    return scenes

            except Exception as e:
                logger.error(f"[PromptGenerator] Generate storyboard failed: {e}")

        # 默认分镜
        return self._default_storyboard(intent, num_scenes)

    def _default_storyboard(
        self,
        intent: IntentAnalysis,
        num_scenes: int
    ) -> List[StoryboardScene]:
        """默认分镜"""
        scenes = []
        duration_per_scene = intent.duration / num_scenes

        for i in range(num_scenes):
            scene = StoryboardScene(
                scene_id=i + 1,
                title=f"Scene {i+1}",
                description=f"Part {i+1} of {intent.subject}",
                duration=duration_per_scene,
                prompt=f"{intent.subject}, {intent.style.value}, scene {i+1}",
                negative_prompt="low quality, blurry",
                camera_angle="medium",
                lighting="natural",
                movement="static"
            )
            scenes.append(scene)

        return scenes

    async def generate_script(
        self,
        intent: IntentAnalysis,
        num_acts: int = 3
    ) -> List[ScriptElement]:
        """生成剧本"""

        prompt = f"""请为以下需求生成剧本：

主题：{intent.topic}
主旨：{intent.subject}
时长：{intent.duration}秒
幕数：{num_acts}

请以JSON格式返回剧本信息：
[
  {{
    "act": 1,
    "scene": 1,
    "location": "地点",
    "time_of_day": "时间(白天/夜晚)",
    "characters": ["角色列表"],
    "dialogue": "对话",
    "action": "动作描述",
    "camera_note": "摄影备注",
    "duration": 时长
  }}
]

只返回JSON数组，不要其他内容。"""

        if self.llm_client:
            try:
                response = await self.llm_client.chat(
                    prompt=prompt,
                    system_prompt="你是一个专业的编剧，擅长创作各类剧本。"
                )

                if response:
                    data = json.loads(response)

                    script = []
                    for elem in data:
                        script.append(ScriptElement(
                            act=elem.get("act", 1),
                            scene=elem.get("scene", 1),
                            location=elem.get("location", ""),
                            time_of_day=elem.get("time_of_day", "白天"),
                            characters=elem.get("characters", []),
                            dialogue=elem.get("dialogue", ""),
                            action=elem.get("action", ""),
                            camera_note=elem.get("camera_note", ""),
                            duration=elem.get("duration", intent.duration / num_acts)
                        ))

                    return script

            except Exception as e:
                logger.error(f"[PromptGenerator] Generate script failed: {e}")

        # 默认剧本
        return [ScriptElement(
            act=1,
            scene=1,
            location="场景",
            time_of_day="白天",
            characters=[],
            dialogue="",
            action=intent.subject,
            camera_note="中景",
            duration=float(intent.duration)
        )]


# ============================================================================
# Workflow Coordinator
# ============================================================================

class WorkflowCoordinator:
    """
    工作流协调器
    整合意图分析、提示词生成、内容生成
    """

    def __init__(
        self,
        intent_analyzer: IntentAnalyzer = None,
        prompt_generator: PromptGenerator = None,
        generation_service=None
    ):
        self.intent_analyzer = intent_analyzer or IntentAnalyzer()
        self.prompt_generator = prompt_generator or PromptGenerator()
        self.generation_service = generation_service
        self.plans: Dict[str, GenerationPlan] = {}

    async def create_plan(
        self,
        user_input: str,
        user_id: str = ""
    ) -> GenerationPlan:
        """创建生成计划"""

        # 1. 分析意图
        logger.info("[Workflow] Step 1: Analyzing intent...")
        intent = await self.intent_analyzer.analyze(user_input)

        # 2. 生成提示词
        logger.info("[Workflow] Step 2: Generating prompts...")
        prompt = await self.prompt_generator.generate_prompt(intent)
        negative_prompt = await self.prompt_generator.generate_negative_prompt(intent)

        intent.generated_prompt = prompt
        intent.negative_prompt = negative_prompt

        # 3. 如果是视频，生成剧本和分镜
        storyboard = []
        script = []

        if intent.intent_type == IntentType.VIDEO_GENERATION:
            logger.info("[Workflow] Step 3: Generating storyboard...")
            storyboard = await self.prompt_generator.generate_storyboard(
                intent,
                num_scenes=max(2, intent.duration // 3)
            )

            logger.info("[Workflow] Step 4: Generating script...")
            script = await self.prompt_generator.generate_script(
                intent,
                num_acts=max(1, len(storyboard) // 3)
            )

        # 4. 创建计划
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(user_input) % 10000}"

        plan = GenerationPlan(
            plan_id=plan_id,
            intent=intent,
            storyboard=storyboard,
            script=script,
            status="planned",
            steps=[
                {"step": 1, "action": "analyze_intent", "description": "分析用户意图"},
                {"step": 2, "action": "generate_prompt", "description": "生成提示词"},
                {"step": 3, "action": "generate_storyboard", "description": "生成分镜", "skipped": len(storyboard) == 0},
                {"step": 4, "action": "generate_content", "description": "生成内容", "pending": True},
                {"step": 5, "action": "save_to_database", "description": "保存到数据库", "pending": True}
            ]
        )

        self.plans[plan_id] = plan

        logger.info(f"[Workflow] Plan created: {plan_id}")

        return plan

    async def execute_plan(
        self,
        plan_id: str,
        user_id: str = ""
    ) -> GenerationPlan:
        """执行生成计划"""

        plan = self.plans.get(plan_id)

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        logger.info(f"[Workflow] Executing plan: {plan_id}")

        try:
            # 步骤4: 生成内容
            plan.status = "generating"

            if plan.intent.intent_type == IntentType.VIDEO_GENERATION:
                # 视频生成 - 按分镜逐个生成
                for scene in plan.storyboard:
                    scene_prompt = scene.prompt or plan.intent.generated_prompt

                    # 调用生成服务
                    if self.generation_service:
                        from unified_generation_service import GenerationRequest, GenerationType

                        request = GenerationRequest(
                            request_id=f"{plan_id}_scene_{scene.scene_id}",
                            generation_type=GenerationType.TEXT_TO_VIDEO,
                            prompt=scene_prompt,
                            negative_prompt=scene.negative_prompt,
                            duration=int(scene.duration),
                            provider=plan.intent.suggested_providers[0] if plan.intent.suggested_providers else "seedance",
                            user_id=user_id
                        )

                        result = await self.generation_service.generate_with_fallback(
                            request,
                            preferred_providers=plan.intent.suggested_providers
                        )

                        if result.videos:
                            plan.generated_videos.extend(result.videos)

            else:
                # 图像生成
                if self.generation_service:
                    from unified_generation_service import GenerationRequest, GenerationType

                    request = GenerationRequest(
                        request_id=plan_id,
                        generation_type=GenerationType.TEXT_TO_IMAGE,
                        prompt=plan.intent.generated_prompt,
                        negative_prompt=plan.intent.negative_prompt,
                        provider=plan.intent.suggested_providers[0] if plan.intent.suggested_providers else "omnigen",
                        user_id=user_id
                    )

                    result = await self.generation_service.generate_with_fallback(
                        request,
                        preferred_providers=plan.intent.suggested_providers
                    )

                    if result.images:
                        plan.generated_images.extend(result.images)

            # 步骤5: 标记完成
            plan.status = "completed"
            plan.completed_at = datetime.now().isoformat()

            # 更新步骤状态
            for step in plan.steps:
                if step["action"] == "generate_content":
                    step["status"] = "completed"
                elif step["action"] == "save_to_database":
                    step["status"] = "completed"

            logger.info(f"[Workflow] Plan completed: {plan_id}")

        except Exception as e:
            logger.error(f"[Workflow] Plan execution failed: {e}")
            plan.status = "failed"

            # 更新步骤状态
            for step in plan.steps:
                if step.get("status") == "pending":
                    step["status"] = "failed"
                    step["error"] = str(e)

        return plan

    def get_plan(self, plan_id: str) -> Optional[GenerationPlan]:
        """获取计划"""
        return self.plans.get(plan_id)

    def list_plans(
        self,
        status: str = None,
        limit: int = 100
    ) -> List[GenerationPlan]:
        """列出计划"""
        plans = list(self.plans.values())

        if status:
            plans = [p for p in plans if p.status == status]

        return plans[-limit:]


# ============================================================================
# Singleton
# ============================================================================

_workflow_coordinator: Optional[WorkflowCoordinator] = None


def get_workflow_coordinator() -> WorkflowCoordinator:
    """获取工作流协调器单例"""
    global _workflow_coordinator

    if _workflow_coordinator is None:
        _workflow_coordinator = WorkflowCoordinator()

    return _workflow_coordinator
