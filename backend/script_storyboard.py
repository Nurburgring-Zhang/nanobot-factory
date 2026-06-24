#!/usr/bin/env python3
"""
Nanobot Factory - Script & Storyboard Generation Module
剧本生成与分镜模块

功能：
- 智能剧本解析
- 角色设定提取
- 场景设定分析
- 分镜提示词生成
- 提示词优化
- 剧本格式转换

基于Coze平台剧本生成分镜提示词的能力构建

@author MiniMax Agent
@date 2026-03-03
"""

import os
import json
import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class ScriptFormat(Enum):
    """剧本格式"""
    STANDARD = "standard"      # 标准剧本格式
    SHORT_DRAMA = "short_drama"  # 短剧格式
    ADVERTISEMENT = "ad"      # 广告剧本
    SOCIAL_MEDIA = "social"   # 社交媒体
    VIDEO = "video"           # 视频脚本


class VideoStyle(Enum):
    """视频风格"""
    CYBERPUNK = "赛博朋克"
    ANIME = "日系动漫"
    REALISTIC = "写实"
    MINIMALIST = "极简"
    CINEMATIC = "电影感"
    DOCUMENTARY = "纪录片"
    COMEDY = "喜剧"
    HORROR = "恐怖"


class ShotType(Enum):
    """镜头类型"""
    EXTREME_WIDE = "全景"       # Extreme Wide Shot (EWS)
    WIDE = "远景"             # Wide Shot (WS)
    MEDIUM_WIDE = "中远景"     # Medium Wide Shot (MWS)
    MEDIUM = "中景"           # Medium Shot (MS)
    MEDIUM_CLOSE_UP = "中近景"  # Medium Close Up (MCU)
    CLOSE_UP = "特写"          # Close Up (CU)
    EXTREME_CLOSE_UP = "大特写" # Extreme Close Up (ECU)
    OVER_SHOULDER = "过肩镜头"  # Over the Shoulder (OTS)
    POV = "主观镜头"           # Point of View


class CameraMovement(Enum):
    """运镜类型"""
    STATIC = "静止"
    PAN = "摇镜"
    TILT = "俯仰"
    DOLLY = "推轨"
    CRANE = "升降"
    ZOOM = "变焦"
    HANDHELD = "手持"
    STABILIZER = "稳定器"


@dataclass
class Character:
    """角色"""
    id: str
    name: str
    description: str
    appearance: str  # 外貌描述
    clothing: str    # 服装
    personality: str  # 性格
    traits: List[str] = field(default_factory=list)  # 特征标签


@dataclass
class Scene:
    """场景"""
    id: str
    name: str
    location: str  # 地点
    time_of_day: str  # 时间
    weather: str = "晴朗"
    lighting: str = ""  # 光线
    atmosphere: str = ""  # 氛围
    background: str = ""  # 背景描述
    props: List[str] = field(default_factory=list)  # 道具


@dataclass
class Shot:
    """分镜"""
    id: str
    scene_id: str
    shot_number: int
    shot_type: ShotType
    camera_movement: CameraMovement
    duration: float  # 秒
    description: str
    dialogue: str = ""
    action: str = ""
    visual_effects: List[str] = field(default_factory=list)
    audio: str = ""  # 音效/配乐
    prompt: str = ""  # AI生成提示词


@dataclass
class Script:
    """剧本"""
    id: str
    title: str
    format: ScriptFormat
    duration: float  # 总时长（秒）
    scenes: List[Scene] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)
    shots: List[Shot] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Storyboard:
    """分镜板"""
    script_id: str
    title: str
    shots: List[Shot]
    style: VideoStyle
    aspect_ratio: str = "16:9"  # 16:9, 9:16, 1:1
    total_duration: float
    prompts: Dict[str, str] = field(default_factory=dict)  # shot_id -> prompt
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# Core Generation
# =============================================================================

class ScriptParser:
    """剧本解析器"""

    # 剧本格式正则
    SCENE_PATTERN = r'((?:第[一二三四五六七八九十\d]+场?|Scene\s*\d+)[:：]?\s*(.+?)(?=(?:第[一二三四五六七八九十\d]+场?|Scene\s*\d+)|$)'
    CHARACTER_PATTERN = r'角色[：:]\s*(.+?)(?=\n|$)'
    DIALOGUE_PATTERN = r'([^：:]+)[：:]\s*(.+?)(?=\n|$)'

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def parse(self, script_text: str, format: ScriptFormat = ScriptFormat.STANDARD) -> Script:
        """解析剧本"""
        script = Script(
            id=hashlib.md5(script_text.encode()).hexdigest()[:16],
            title=self._extract_title(script_text),
            format=format,
            duration=0.0
        )

        # 提取场景
        script.scenes = self._extract_scenes(script_text)

        # 提取角色
        script.characters = self._extract_characters(script_text)

        # 生成角色视觉描述
        for character in script.characters:
            character.appearance = await self._generate_character_appearance(character.description)

        # 估算时长
        script.duration = len(script.scenes) * 10.0  # 每场景约10秒

        return script

    def _extract_title(self, text: str) -> str:
        """提取标题"""
        lines = text.strip().split('\n')
        for line in lines[:5]:
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:100]
        return "未命名剧本"

    def _extract_scenes(self, text: str) -> List[Scene]:
        """提取场景"""
        scenes = []
        lines = text.split('\n')

        current_scene = None
        scene_count = 0

        for line in lines:
            line = line.strip()

            # 检测场景标记
            if re.match(r'(?:第[一二三四五六七八九十\d]+场?|Scene\s*\d+)', line):
                if current_scene:
                    scenes.append(current_scene)

                scene_count += 1
                scene_name = re.sub(r'^(?:第[一二三四五六七八九十\d]+场?|Scene\s*\d+)\s*[:：]?\s*', '', line)
                current_scene = Scene(
                    id=f"scene_{scene_count}",
                    name=scene_name or f"场景{scene_count}",
                    location="",
                    time_of_day="日"
                )

            elif current_scene and line:
                # 解析场景描述
                if '地点' in line or '场景' in line:
                    current_scene.location = line.split('：')[-1].strip()
                elif '时间' in line or '时段' in line:
                    current_scene.time_of_day = line.split('：')[-1].strip()
                elif '天气' in line:
                    current_scene.weather = line.split('：')[-1].strip()
                elif '光线' in line:
                    current_scene.lighting = line.split('：')[-1].strip()

        if current_scene:
            scenes.append(current_scene)

        return scenes

    def _extract_characters(self, text: str) -> List[Character]:
        """提取角色"""
        characters = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()

            if '角色' in line and '：' in line:
                parts = line.split('：', 1)
                if len(parts) == 2:
                    char_name = parts[0].replace('角色', '').strip()
                    char_desc = parts[1].strip()

                    character = Character(
                        id=hashlib.md5(char_name.encode()).hexdigest()[:8],
                        name=char_name,
                        description=char_desc,
                        appearance="",
                        clothing="",
                        personality=""
                    )
                    characters.append(character)

        return characters

    async def _generate_character_appearance(self, description: str) -> str:
        """生成角色外观描述"""
        if self.llm_client:
            prompt = f"根据以下角色描述，生成适合AI图像生成的视觉描述（外貌、穿着）：\n{description}"
            result = await self.llm_client.generate(prompt)
            return result
        return description


class StoryboardGenerator:
    """分镜生成器"""

    # 运镜模板
    MOVEMENT_TEMPLATES = {
        "intro": "Slow Dolly Forward + Cinematic",  # 开场推进
        "action": "Handheld + Quick Cuts",        # 动作场景
        "dialogue": "Medium Shot + Slow Pan",      # 对话
        "emotion": "Close Up + Slow Zoom",        # 情绪
        "transition": "Crane Up/Down",             # 转场
        "outro": "Slow Fade + Wide Shot"          # 结尾
    }

    # 风格提示词模板
    STYLE_PROMPTS = {
        VideoStyle.CYBERPUNK: "赛博朋克风格，霓虹灯光，雨水反光，城市夜景，湿润街道，高对比度，"
                             "蓝紫色调，的未来城市背景，赛博朋克美学，",
        VideoStyle.ANIME: "日系动漫风格，柔和光线，精美画风，二次元，清新色调，动漫感，"
                         "柔和阴影，漫画分格，",
        VideoStyle.REALISTIC: "写实风格，高清摄影，自然光线，真实感，电影质感，"
                             "专业摄影，细节丰富，",
        VideoStyle.MINIMALIST: "极简风格，简洁构图，大量留白，干净背景，现代设计，"
                              "纯色背景，简约美学，",
        VideoStyle.CINEMATIC: "电影质感，宽银幕比例，专业灯光，电影感，"
                             "宽银幕镜头，戏剧性光线，电影级画质，"
    }

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def generate(
        self,
        script: Script,
        style: VideoStyle = VideoStyle.CINEMATIC,
        aspect_ratio: str = "16:9",
        duration_per_shot: float = 5.0
    ) -> Storyboard:
        """生成分镜"""
        storyboard = Storyboard(
            script_id=script.id,
            title=script.title,
            shots=[],
            style=style,
            aspect_ratio=aspect_ratio,
            total_duration=script.duration
        )

        # 为每个场景生成分镜
        shot_number = 0

        for scene in script.scenes:
            # 场景建立镜头
            shot_number += 1
            establishment_shot = await self._create_shot(
                scene=scene,
                shot_number=shot_number,
                shot_type=ShotType.WIDE,
                movement=CameraMovement.STATIC,
                duration=duration_per_shot,
                description=f"展示{scene.name}的全景",
                context="establishment"
            )
            storyboard.shots.append(establishment_shot)

            # 生成动作/对话镜头
            shot_number += 1
            action_shot = await self._create_shot(
                scene=scene,
                shot_number=shot_number,
                shot_type=ShotType.MEDIUM,
                movement=CameraMovement.DOLLY,
                duration=duration_per_shot,
                description=f"场景中的主要动作",
                context="action"
            )
            storyboard.shots.append(action_shot)

            # 情感/特写镜头（如果有角色）
            if scene.location:
                shot_number += 1
                emotion_shot = await self._create_shot(
                    scene=scene,
                    shot_number=shot_number,
                    shot_type=ShotType.CLOSE_UP,
                    movement=CameraMovement.ZOOM,
                    duration=duration_per_shot,
                    description=f"捕捉场景情绪",
                    context="emotion"
                )
                storyboard.shots.append(emotion_shot)

        # 更新总时长
        storyboard.total_duration = len(storyboard.shots) * duration_per_shot

        # 生成每个镜头的AI提示词
        storyboard.prompts = await self._generate_prompts(storyboard, style)

        return storyboard

    async def _create_shot(
        self,
        scene: Scene,
        shot_number: int,
        shot_type: ShotType,
        movement: CameraMovement,
        duration: float,
        description: str,
        context: str
    ) -> Shot:
        """创建单个分镜"""
        shot = Shot(
            id=f"shot_{shot_number}",
            scene_id=scene.id,
            shot_number=shot_number,
            shot_type=shot_type,
            camera_movement=movement,
            duration=duration,
            description=description,
            action=description
        )

        # 添加默认运镜
        if context in self.MOVEMENT_TEMPLATES:
            shot.visual_effects = [self.MOVEMENT_TEMPLATES[context]]

        return shot

    async def _generate_prompts(
        self,
        storyboard: Storyboard,
        style: VideoStyle
    ) -> Dict[str, str]:
        """生成分镜提示词"""
        prompts = {}
        style_prompt = self.STYLE_PROMPTS.get(style, "")

        for shot in storyboard.shots:
            # 构建基础提示词
            prompt_parts = []

            # 镜头类型
            prompt_parts.append(shot.shot_type.value)

            # 场景描述
            if shot.scene_id:
                scene = next((s for s in [] if s.id == shot.scene_id), None)
                if scene:
                    if scene.location:
                        prompt_parts.append(f"在{scene.location}")
                    if scene.time_of_day:
                        prompt_parts.append(f"{scene.time_of_day}的")

            # 动作描述
            if shot.action:
                prompt_parts.append(shot.action)

            # 运镜
            if shot.visual_effects:
                prompt_parts.extend(shot.visual_effects)

            # 添加风格
            prompt_parts.append(style_prompt)

            # 添加质量约束
            prompt_parts.extend([
                "高清画质",
                "画面稳定",
                "人体结构正常",
                "无变形"
            ])

            # 组合提示词
            prompt = "，".join(prompt_parts)

            # 如果有LLM，优化提示词
            if self.llm_client:
                prompt = await self._optimize_prompt(prompt, style)

            prompts[shot.id] = prompt

        return prompts

    async def _optimize_prompt(self, prompt: str, style: VideoStyle) -> str:
        """优化提示词"""
        if self.llm_client:
            enhanced_prompt = await self.llm_client.generate(
                f"优化以下AI视频生成提示词，使其更专业、更详细、更适合{style.value}风格：\n{prompt}"
            )
            return enhanced_prompt

        return prompt


class PromptOptimizer:
    """提示词优化器"""

    # Seedance 2.0 提示词模板
    SEEDANCE_TEMPLATE = """
{shot_type} {subject}，{action}，{movement}，{lighting}，{atmosphere}，{style}，{quality_constraints}
"""

    # 关键技巧
    TECHNIQUES = [
        "动作必须慢速连续",
        "运镜必须克制",
        "强制添加质量约束",
        "风格锚定明确"
    ]

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def optimize_for_video(
        self,
        prompt: str,
        duration: float = 5.0,
        style: Optional[VideoStyle] = None
    ) -> str:
        """优化为视频生成提示词"""
        # 添加动作描述
        optimized = f"缓慢的连续动作：{prompt}，"

        # 添加运镜
        optimized += "Smooth Dolly Forward + Cinematic，"

        # 添加风格
        if style:
            optimized += f"{style.value}，"

        # 添加质量约束
        optimized += "4K画质，画面稳定无闪烁，人体结构正常，无变形"

        # 如果有LLM，进一步优化
        if self.llm_client:
            optimized = await self.llm_client.generate(
                f"将以下提示词优化为专业的AI视频生成提示词：\n{optimized}"
            )

        return optimized

    async def optimize_for_image(
        self,
        prompt: str,
        style: Optional[VideoStyle] = None
    ) -> str:
        """优化为图像生成提示词"""
        # 添加质量描述
        optimized = f"高质量详细：{prompt}，"

        # 添加风格
        if style:
            style_map = {
                VideoStyle.CYBERPUNK: "赛博朋克风格，霓虹灯光，黑暗城市",
                VideoStyle.ANIME: "日系动漫风格，精致脸庞，柔和光线",
                VideoStyle.REALISTIC: "写实摄影风格，专业灯光，高清画质",
                VideoStyle.CINEMATIC: "电影质感，宽银幕，戏剧性光线"
            }
            optimized += style_map.get(style, style.value) + "，"

        # 添加质量约束
        optimized += " masterpiece, best quality, highly detailed, 8k"

        return optimized


# =============================================================================
# Main API
# =============================================================================

class ScriptStoryboardAPI:
    """剧本分镜API"""

    def __init__(self, llm_client=None):
        self.parser = ScriptParser(llm_client)
        self.generator = StoryboardGenerator(llm_client)
        self.optimizer = PromptOptimizer(llm_client)

    async def parse_script(
        self,
        script_text: str,
        format: ScriptFormat = ScriptFormat.STANDARD
    ) -> Dict:
        """解析剧本"""
        script = await self.parser.parse(script_text, format)
        return self._script_to_dict(script)

    async def generate_storyboard(
        self,
        script_text: str,
        style: str = "cinematic",
        aspect_ratio: str = "16:9",
        duration_per_shot: float = 5.0
    ) -> Dict:
        """生成分镜"""
        # 解析剧本
        format_map = {
            "short_drama": ScriptFormat.SHORT_DRAMA,
            "ad": ScriptFormat.ADVERTISEMENT,
            "social": ScriptFormat.SOCIAL_MEDIA,
            "video": ScriptFormat.VIDEO
        }
        script_format = format_map.get(format.lower(), ScriptFormat.STANDARD)

        script = await self.parser.parse(script_text, script_format)

        # 风格映射
        style_map = {
            "cyberpunk": VideoStyle.CYBERPUNK,
            "anime": VideoStyle.ANIME,
            "realistic": VideoStyle.REALISTIC,
            "minimalist": VideoStyle.MINIMALIST,
            "cinematic": VideoStyle.CINEMATIC
        }
        video_style = style_map.get(style.lower(), VideoStyle.CINEMATIC)

        # 生成分镜
        storyboard = await self.generator.generate(
            script,
            video_style,
            aspect_ratio,
            duration_per_shot
        )

        return self._storyboard_to_dict(storyboard)

    async def optimize_prompt(
        self,
        prompt: str,
        target: str = "video",
        style: Optional[str] = None
    ) -> str:
        """优化提示词"""
        style_obj = None
        if style:
            style_map = {
                "cyberpunk": VideoStyle.CYBERPUNK,
                "anime": VideoStyle.ANIME,
                "realistic": VideoStyle.REALISTIC,
                "cinematic": VideoStyle.CINEMATIC
            }
            style_obj = style_map.get(style.lower())

        if target == "video":
            return await self.optimizer.optimize_for_video(prompt, style=style_obj)
        else:
            return await self.optimizer.optimize_for_image(prompt, style_obj)

    def _script_to_dict(self, script: Script) -> Dict:
        """转换剧本为字典"""
        return {
            "id": script.id,
            "title": script.title,
            "format": script.format.value,
            "duration": script.duration,
            "characters": [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "appearance": c.appearance,
                    "clothing": c.clothing,
                    "personality": c.personality
                }
                for c in script.characters
            ],
            "scenes": [
                {
                    "id": s.id,
                    "name": s.name,
                    "location": s.location,
                    "time_of_day": s.time_of_day,
                    "weather": s.weather,
                    "lighting": s.lighting
                }
                for s in script.scenes
            ],
            "created_at": script.created_at
        }

    def _storyboard_to_dict(self, storyboard: Storyboard) -> Dict:
        """转换分镜为字典"""
        return {
            "script_id": storyboard.script_id,
            "title": storyboard.title,
            "style": storyboard.style.value,
            "aspect_ratio": storyboard.aspect_ratio,
            "total_duration": storyboard.total_duration,
            "shots": [
                {
                    "id": s.id,
                    "scene_id": s.scene_id,
                    "shot_number": s.shot_number,
                    "shot_type": s.shot_type.value,
                    "camera_movement": s.camera_movement.value,
                    "duration": s.duration,
                    "description": s.description,
                    "dialogue": s.dialogue,
                    "action": s.action,
                    "prompt": storyboard.prompts.get(s.id, "")
                }
                for s in storyboard.shots
            ],
            "prompts": storyboard.prompts,
            "created_at": storyboard.created_at
        }


# =============================================================================
# Global Instance
# =============================================================================

_script_storyboard_api: Optional[ScriptStoryboardAPI] = None


def get_script_storyboard_api(llm_client=None) -> ScriptStoryboardAPI:
    """获取剧本分镜API实例"""
    global _script_storyboard_api
    if _script_storyboard_api is None:
        _script_storyboard_api = ScriptStoryboardAPI(llm_client)
    return _script_storyboard_api
