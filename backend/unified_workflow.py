#!/usr/bin/env python3
"""
Nanobot Factory - Unified Content Production Workflow
统一内容生产工作流

核心工作流程：
用户输入 → Nanobot分析 → AI理解 → 提示词/剧本生成 → AIGC生成 → 数据库存储

支持：
- 全网信息检索（World Monitor）
- 智能内容分析
- 剧本/分镜生成
- 提示词优化
- 多平台AIGC生成（Seedream5.0/Seedance2.0/Nano Banana/豆包/可灵/ComfyUI）
- 自动数据管理

@author MiniMax Agent
@date 2026-03-03
"""

import os
import json
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

from world_monitor import WorldMonitorAPI, get_world_monitor
from agent_reach import AgentReachAPI, get_agent_reach, AgentReachConfig
from script_storyboard import (
    ScriptStoryboardAPI,
    get_script_storyboard_api,
    ScriptFormat,
    VideoStyle
)
from aigc import AIGCProvider, GenerationRequest, GeneratorType

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class WorkflowStatus(Enum):
    """工作流状态"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    PRODUCING = "producing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentType(Enum):
    """内容类型"""
    IMAGE = "image"
    VIDEO = "video"
    ARTICLE = "article"
    PODCAST = "podcast"
    SOCIAL_POST = "social_post"
    STORYBOARD = "storyboard"


@dataclass
class WorkflowRequest:
    """工作流请求"""
    user_input: str
    content_type: ContentType = ContentType.IMAGE
    style: str = "cinematic"
    aspect_ratio: str = "16:9"
    duration: float = 5.0
    provider: str = "auto"  # auto, seedream, seedance, nanobanana, doubao, kling, comfyui
    keywords: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """工作流结果"""
    workflow_id: str
    status: WorkflowStatus
    user_input: str
    analysis: Dict[str, Any] = field(default_factory=dict)
    script: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, Any] = field(default_factory=dict)
    generated_assets: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


# =============================================================================
# Nanobot Controller
# =============================================================================

class NanobotController:
    """
    Nanobot控制器 - 核心AI驱动引擎

    负责：
    1. 理解用户输入
    2. 协调各个模块
    3. 执行内容生产工作流
    """

    def __init__(
        self,
        llm_client=None,
        world_monitor: Optional[WorldMonitorAPI] = None,
        agent_reach: Optional[AgentReachAPI] = None,
        script_storyboard: Optional[ScriptStoryboardAPI] = None,
        aigc_provider: Optional[AIGCProvider] = None
    ):
        self.llm_client = llm_client
        self.world_monitor = world_monitor or get_world_monitor()
        self.agent_reach = agent_reach or get_agent_reach()
        self.script_storyboard = script_storyboard or get_script_storyboard_api(llm_client)
        self.aigc_provider = aigc_provider or AIGCProvider()

    async def analyze_input(self, user_input: str) -> Dict[str, Any]:
        """
        分析用户输入

        理解用户的意图、需求、上下文
        """
        analysis = {
            "original_input": user_input,
            "intent": "",
            "topic": "",
            "keywords": [],
            "style": "cinematic",
            "content_type": "image",
            "suggested_prompt": "",
            "requires_research": False,
            "requires_script": False
        }

        # 简单的关键词匹配分析
        # 在实际使用中，这里会调用LLM进行深度理解
        input_lower = user_input.lower()

        # 检测内容类型
        if any(kw in input_lower for kw in ["视频", "video", "生成视频", "做视频"]):
            analysis["content_type"] = "video"
            analysis["requires_script"] = True
        elif any(kw in input_lower for kw in ["文章", "文章", "写文章", "博客"]):
            analysis["content_type"] = "article"
        elif any(kw in input_lower for kw in ["播客", "podcast", "语音", "朗读"]):
            analysis["content_type"] = "podcast"
        else:
            analysis["content_type"] = "image"

        # 检测是否需要研究
        if any(kw in input_lower for kw in ["热点", "趋势", "最新", "新闻", "分析"]):
            analysis["requires_research"] = True

        # 检测风格
        style_keywords = {
            "cyberpunk": ["赛博朋克", "cyberpunk", "未来"],
            "anime": ["动漫", "二次元", "anime", "日系"],
            "realistic": ["写实", "真实", "realistic"],
            "cinematic": ["电影", "cinematic", "大片"],
            "minimalist": ["极简", "简约", "minimal"]
        }

        for style, keywords in style_keywords.items():
            if any(kw in input_lower for kw in keywords):
                analysis["style"] = style
                break

        # 提取关键词
        words = user_input.replace("生成", "").replace("制作", "").replace("创建", "").strip()
        analysis["keywords"] = words.split()[:10]
        analysis["topic"] = words[:50]

        # 生成建议提示词
        if analysis["content_type"] == "image":
            analysis["suggested_prompt"] = f"{words}, {analysis['style']}风格, 高质量"
        elif analysis["content_type"] == "video":
            analysis["suggested_prompt"] = f"{words}, {analysis['style']}风格, 缓慢连续动作"

        return analysis

    async def research(self, topic: str) -> Dict[str, Any]:
        """
        研究主题

        使用World Monitor和Agent-Reach收集相关信息
        """
        research_data = {
            "topic": topic,
            "news": [],
            "hot_topics": [],
            "world_brief": {},
            "web_content": []
        }

        try:
            # 获取相关新闻
            news = await self.world_monitor.get_news(topic, limit=10)
            research_data["news"] = news

            # 获取热点话题
            hot_topics = await self.world_monitor.get_hot_topics(limit=10)
            research_data["hot_topics"] = hot_topics

            # 获取世界简报
            brief = await self.world_monitor.get_world_brief()
            research_data["world_brief"] = brief

        except Exception as e:
            logger.error(f"Research error: {e}")

        # 补充网页搜索
        try:
            search_result = await self.agent_reach.search(topic)
            research_data["web_content"] = search_result.get("results", [])[:5]
        except Exception as e:
            logger.warning(f"Web search error: {e}")

        return research_data

    async def generate_script(
        self,
        topic: str,
        style: str = "cinematic",
        content_type: str = "video"
    ) -> Dict[str, Any]:
        """生成剧本/分镜"""
        # 构建剧本文本
        if content_type == "video":
            script_text = f"""
第1场：开场
角色：主角
地点：{topic}相关场景
时间：日

{topic}的核心内容展示

第2场：细节
角色：主角
地点：室内/室外
时间：日

深入展示{topic}的细节和特点

第3场：结尾
角色：主角
地点：相关场景
时间：黄昏

总结和展望
"""
        else:
            script_text = topic

        # 生成分镜
        try:
            storyboard = await self.script_storyboard.generate_storyboard(
                script_text=script_text,
                style=style,
                aspect_ratio="16:9" if content_type == "video" else "1:1",
                duration_per_shot=5.0
            )
            return storyboard
        except Exception as e:
            logger.error(f"Script generation error: {e}")
            return {"error": str(e)}

    async def generate_prompts(
        self,
        topic: str,
        style: str = "cinematic",
        content_type: str = "image"
    ) -> Dict[str, Any]:
        """生成提示词"""
        prompts = {}

        if content_type == "image":
            # 图像提示词
            prompt = await self.script_storyboard.optimize_prompt(
                prompt=topic,
                target="image",
                style=style
            )
            prompts["main"] = prompt
            prompts["variations"] = [
                prompt + "，不同角度",
                prompt + "，特写",
                prompt + "，远景"
            ]

        elif content_type == "video":
            # 视频提示词
            prompt = await self.script_storyboard.optimize_prompt(
                prompt=topic,
                target="video",
                style=style
            )
            prompts["main"] = prompt

            # 生成多镜头提示词
            shots = []
            for i in range(5):
                shot_prompt = f"镜头{i+1}：{prompt}，{['远景', '中景', '近景', '特写', '全景'][i]}"
                shots.append(shot_prompt)

            prompts["shots"] = shots

        return prompts

    async def produce_content(
        self,
        prompts: Dict[str, Any],
        provider: str = "auto",
        content_type: str = "image",
        **kwargs
    ) -> List[Dict[str, Any]]:
        """生成内容"""
        assets = []

        # 确定使用的生成器
        provider_map = {
            "seedream": GeneratorType.SEEDREAM5,
            "seedance": GeneratorType.SEEDANCE2,
            "nanobanana": GeneratorType.NANOBANANA,
            "doubao": GeneratorType.DOUBAO,
            "kling": GeneratorType.KLING,
            "comfyui": GeneratorType.COMFYUI,
            "jimeng": GeneratorType.JIMENG
        }

        generator = provider_map.get(provider, GeneratorType.COMFYUI)

        try:
            if content_type == "video" and "shots" in prompts:
                # 批量生成视频帧
                for i, shot_prompt in enumerate(prompts["shots"]):
                    request = GenerationRequest(
                        prompt=shot_prompt,
                        generation_type="video" if content_type == "video" else "image",
                        **kwargs
                    )

                    result = await self.aigc_provider.generate(request)
                    assets.append({
                        "shot_number": i + 1,
                        "prompt": shot_prompt,
                        "result": result,
                        "status": result.status
                    })
            else:
                # 单次生成
                request = GenerationRequest(
                    prompt=prompts.get("main", ""),
                    generation_type="image" if content_type == "image" else "video",
                    **kwargs
                )

                result = await self.aigc_provider.generate(request)
                assets.append({
                    "prompt": prompts.get("main", ""),
                    "result": result,
                    "status": result.status
                })

        except Exception as e:
            logger.error(f"Content generation error: {e}")
            assets.append({"error": str(e)})

        return assets


# =============================================================================
# Main Workflow
# =============================================================================

class ContentProductionWorkflow:
    """
    内容生产工作流

    完整的自动化内容生产管线：
    1. 接收用户输入
    2. Nanobot分析理解
    3. 智能研究（可选）
    4. 生成剧本/分镜（可选）
    5. 优化提示词
    6. 调用AIGC生成
    7. 保存到数据库
    """

    def __init__(self, nanobot_controller: Optional[NanobotController] = None):
        self.nanobot = nanobot_controller or NanobotController()

    async def execute(self, request: WorkflowRequest) -> WorkflowResult:
        """
        执行工作流
        """
        workflow_id = str(uuid.uuid4())[:16]
        result = WorkflowResult(
            workflow_id=workflow_id,
            status=WorkflowStatus.PENDING,
            user_input=request.user_input
        )

        try:
            # 步骤1：分析输入
            result.status = WorkflowStatus.ANALYZING
            analysis = await self.nanobot.analyze_input(request.user_input)
            result.analysis = analysis

            # 步骤2：研究（如果需要）
            if analysis.get("requires_research") or analysis.get("requires_script"):
                research = await self.nanobot.research(analysis.get("topic", ""))
                result.analysis["research"] = research

            # 步骤3：生成剧本/分镜（如果是视频）
            if request.content_type == ContentType.VIDEO:
                script = await self.nanobot.generate_script(
                    topic=analysis.get("topic", ""),
                    style=request.style,
                    content_type="video"
                )
                result.script = script

            # 步骤4：生成提示词
            prompts = await self.nanobot.generate_prompts(
                topic=analysis.get("topic", ""),
                style=request.style,
                content_type=request.content_type.value
            )
            result.prompts = prompts

            # 步骤5：生成内容
            result.status = WorkflowStatus.PRODUCING
            assets = await self.nanobot.produce_content(
                prompts=prompts,
                provider=request.provider,
                content_type=request.content_type.value,
                width=1920 if request.aspect_ratio == "16:9" else 1080,
                height=1080 if request.aspect_ratio == "16:9" else 1920,
                duration=int(request.duration)
            )
            result.generated_assets = assets

            # 步骤6：完成
            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now().isoformat()

        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.error = str(e)
            logger.error(f"Workflow error: {e}")

        return result

    async def execute_simple(self, user_input: str, **kwargs) -> WorkflowResult:
        """
        简单执行（快速生成）
        """
        # 构建请求
        request = WorkflowRequest(
            user_input=user_input,
            content_type=ContentType(kwargs.get("content_type", "image")),
            style=kwargs.get("style", "cinematic"),
            provider=kwargs.get("provider", "auto"),
            **kwargs
        )

        return await self.execute(request)


# =============================================================================
# API Interface
# =============================================================================

class ProductionWorkflowAPI:
    """生产工作流API"""

    def __init__(self):
        self.workflow = ContentProductionWorkflow()

    async def produce(self, request: WorkflowRequest) -> Dict:
        """执行生产"""
        result = await self.workflow.execute(request)
        return self._result_to_dict(result)

    async def produce_simple(
        self,
        user_input: str,
        content_type: str = "image",
        style: str = "cinematic",
        provider: str = "auto"
    ) -> Dict:
        """简单生产"""
        result = await self.workflow.execute_simple(
            user_input=user_input,
            content_type=content_type,
            style=style,
            provider=provider
        )
        return self._result_to_dict(result)

    async def analyze(self, user_input: str) -> Dict:
        """分析输入"""
        controller = NanobotController()
        analysis = await controller.analyze_input(user_input)
        return analysis

    async def research(self, topic: str) -> Dict:
        """研究主题"""
        world_monitor = get_world_monitor()
        return await world_monitor.get_news(topic, limit=20)

    async def generate_script(
        self,
        topic: str,
        style: str = "cinematic"
    ) -> Dict:
        """生成剧本"""
        api = get_script_storyboard_api()
        return await api.generate_storyboard(topic, style=style)

    async def optimize_prompt(
        self,
        prompt: str,
        target: str = "image",
        style: str = "cinematic"
    ) -> str:
        """优化提示词"""
        api = get_script_storyboard_api()
        return await api.optimize_prompt(prompt, target=target, style=style)

    def _result_to_dict(self, result: WorkflowResult) -> Dict:
        """转换结果为字典"""
        return {
            "workflow_id": result.workflow_id,
            "status": result.status.value,
            "user_input": result.user_input,
            "analysis": result.analysis,
            "script": result.script,
            "prompts": result.prompts,
            "generated_assets": result.generated_assets,
            "error": result.error,
            "created_at": result.created_at,
            "completed_at": result.completed_at
        }


# =============================================================================
# Global Instance
# =============================================================================

_production_workflow_api: Optional[ProductionWorkflowAPI] = None


def get_production_workflow() -> ProductionWorkflowAPI:
    """获取生产工作流API"""
    global _production_workflow_api
    if _production_workflow_api is None:
        _production_workflow_api = ProductionWorkflowAPI()
    return _production_workflow_api
