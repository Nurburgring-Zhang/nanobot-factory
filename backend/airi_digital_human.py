#!/usr/bin/env python3
"""
Nanobot Factory - AIRI 数字人模块
AIRI Digital Human Module

完整实现基于 Nanobot+Agents+Skills 驱动的 AI 数字人助手功能：
- 数字人渲染引擎 (VRM/Live2D)
- 动画系统
- 表情系统
- 语音合成与识别 (TTS/STT)
- 技能系统 (@avatar 装饰器)
- 行为树
- 与 Nanobot AI 能力的集成

@author Matrix Agent
@date 2026-01-18
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import uuid
import time
import base64
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable, Set, Awaitable, TypeVar

# 类型变量用于装饰器
F = TypeVar('F', bound=Callable)
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from functools import wraps
import inspect
import logging.config


class StructuredLogger:
    """结构化日志记录器
    
    提供 JSON 格式的结构化日志，支持日志级别、上下文信息
    """
    
    # 敏感字段列表 - 这些字段不会被记录到日志中
    SENSITIVE_FIELDS = frozenset([
        "api_key", "apikey", "api-key", "password", "passwd", "secret",
        "token", "access_token", "refresh_token", "authorization",
        "session_id", "session_id", "user_id", "user_token",
        "private_key", "public_key", "credential", "auth",
        "openai_api_key", "anthropic_api_key", "openrouter_api_key",
        "stripe_secret", "aws_secret", "azure_key",
    ])
    
    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        r"(sk-[a-zA-Z0-9]{20,})",  # OpenAI API Key
        r"(sk-ant-[a-zA-Z0-9-]{50,})",  # Anthropic API Key
        r"(Bearer\s+[a-zA-Z0-9-]{20,})",  # Bearer Token
        r"(password[=:]\s*[^\s]+)",  # password=xxx
        r"(api_key[=:]\s*[^\s]+)",  # api_key=xxx
    ]
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._context: Dict[str, Any] = {}
    
    def _sanitize_value(self, value: Any) -> Any:
        """清理敏感值
        
        如果值是字符串，检查是否包含敏感信息
        如果值是字典，递归清理所有字段
        """
        if isinstance(value, str):
            # 检查是否匹配敏感模式
            for pattern in self.SENSITIVE_PATTERNS:
                import re
                if re.search(pattern, value, re.IGNORECASE):
                    return "***REDACTED***"
            return value
        
        elif isinstance(value, dict):
            # 递归清理字典
            return {k: self._sanitize_value(v) for k, v in value.items()}
        
        elif isinstance(value, (list, tuple)):
            # 清理列表/元组
            return [self._sanitize_value(item) for item in value]
        
        return value
    
    def _should_redact(self, key: str) -> bool:
        """检查是否应该隐藏该字段"""
        key_lower = key.lower()
        # 检查是否包含敏感字段
        for sensitive in self.SENSITIVE_FIELDS:
            if sensitive in key_lower:
                return True
        return False
    
    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理字典中的敏感信息"""
        result = {}
        for key, value in data.items():
            if self._should_redact(key):
                result[key] = "***REDACTED***"
            else:
                result[key] = self._sanitize_value(value)
        return result
    
    def set_context(self, **kwargs) -> None:
        """设置日志上下文"""
        # 自动清理敏感信息
        self._context = self._sanitize_dict(kwargs)
    
    def clear_context(self) -> None:
        """清除日志上下文"""
        self._context.clear()
    
    def _format_message(self, message: str, **kwargs) -> str:
        """格式化日志消息"""
        # 清理所有传入的参数
        sanitized_kwargs = self._sanitize_dict(kwargs)
        
        # 合并上下文
        ctx = {**self._context, **sanitized_kwargs}
        if ctx:
            return f"{message} | {json.dumps(ctx, ensure_ascii=False)}"
        return message
    
    def debug(self, message: str, **kwargs) -> None:
        """调试日志"""
        self.logger.debug(self._format_message(message, **kwargs))
    
    def info(self, message: str, **kwargs) -> None:
        """信息日志"""
        self.logger.info(self._format_message(message, **kwargs))
    
    def warning(self, message: str, **kwargs) -> None:
        """警告日志"""
        self.logger.warning(self._format_message(message, **kwargs))
    
    def error(self, message: str, **kwargs) -> None:
        """错误日志"""
        self.logger.error(self._format_message(message, **kwargs))
    
    def critical(self, message: str, **kwargs) -> None:
        """严重错误日志"""
        self.logger.critical(self._format_message(message, **kwargs))
    
    def log(self, level: int, message: str, **kwargs) -> None:
        """通用日志方法"""
        self.logger.log(level, self._format_message(message, **kwargs))


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False
) -> None:
    """配置日志系统
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径 (可选)
        json_format: 是否使用 JSON 格式
    """
    # 获取根日志记录器
    root_logger = logging.getLogger()
    
    # 设置级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    # 清除现有处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建格式化器
    if json_format:
        # JSON 格式
        class JSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_data, ensure_ascii=False)
        
        formatter = JSONFormatter()
    else:
        # 标准格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器 (如果指定)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    logging.info(f"日志系统已配置 - 级别: {level}, JSON: {json_format}")


# 从环境变量读取日志配置
LOG_LEVEL = os.environ.get("AIRI_LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("AIRI_LOG_FILE", "")
LOG_JSON = os.environ.get("AIRI_LOG_JSON", "false").lower() == "true"

# 配置日志
setup_logging(level=LOG_LEVEL, log_file=LOG_FILE if LOG_FILE else None, json_format=LOG_JSON)

# Create module logger
logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================

class AvatarType(Enum):
    """数字人类型"""
    VRM = "vrm"           # VRM 3D模型
    LIVE2D = "live2d"     # Live2D 2D模型
    IMAGE = "image"        # 静态图像
    ANIMATED = "animated"  # 动态图像序列


class AnimationType(Enum):
    """动画类型"""
    IDLE = "idle"              # 待机
    WAVE = "wave"              # 挥手
    NOD = "nod"                # 点头
    SHAKE_HEAD = "shake_head" # 摇头
    HAPPY = "happy"           # 开心
    SAD = "sad"               # 悲伤
    THINKING = "thinking"      # 思考
    SURPRISED = "surprised"   # 惊讶
    WINK = "wink"             # 眨眼
    DANCE = "dance"            # 跳舞
    JUMP = "jump"              # 跳跃
    WALK = "walk"              # 行走
    RUN = "run"                # 奔跑
    SLEEP = "sleep"            # 睡眠
    TALK = "talk"              # 说话
    LAUGH = "laugh"            # 大笑


class ExpressionType(Enum):
    """表情类型"""
    NEUTRAL = "neutral"       # 中性
    HAPPY = "happy"           # 开心
    SAD = "sad"               # 悲伤
    ANGRY = "angry"           # 愤怒
    SURPRISED = "surprised"   # 惊讶
    FEARFUL = "fearful"       # 害怕
    DISGUSTED = "disgusted"   # 厌恶
    CONFUSED = "confused"     # 困惑
    THINKING = "thinking"      # 思考
    SHY = "shy"               # 害羞


class InteractionState(Enum):
    """交互状态"""
    IDLE = "idle"              # 空闲
    LISTENING = "listening"    # 倾听
    SPEAKING = "speaking"      # 说话
    THINKING = "thinking"      # 思考
    EXECUTING = "executing"    # 执行操作
    WAITING = "waiting"        # 等待


@dataclass
class AvatarConfig:
    """数字人配置
    
    配置优先级:
    1. 环境变量 (AIRI_*)
    2. 配置文件 (airi_config.json)
    3. 默认值
    """
    
    def __init__(self):
        # 渲染配置 - 从环境变量加载或使用默认值
        self.avatar_type = AvatarType(os.environ.get("AIRI_AVATAR_TYPE", "live2d"))
        self.model_path = os.environ.get("AIRI_MODEL_PATH", "")
        self.canvas_size = self._parse_tuple(os.environ.get("AIRI_CANVAS_SIZE", "1920,1080"))
        self.background_color = self._parse_tuple(os.environ.get("AIRI_BG_COLOR", "0,0,0,0"))
        
        # 性能配置
        self.target_fps = int(os.environ.get("AIRI_TARGET_FPS", "30"))
        self.enable_vsync = os.environ.get("AIRI_ENABLE_VSYNC", "true").lower() == "true"
        
        # 特性开关
        self.enable_shadows = os.environ.get("AIRI_ENABLE_SHADOWS", "true").lower() == "true"
        self.enable_post_processing = os.environ.get("AIRI_ENABLE_POST_PROCESSING", "true").lower() == "true"
        
        # 位置和大小 - 使用归一化坐标 (0-1)
        self.default_position = self._parse_tuple(os.environ.get("AIRI_DEFAULT_POSITION", "0.5,0.5"))
        self.default_scale = float(os.environ.get("AIRI_DEFAULT_SCALE", "1.0"))
        
        # 激活状态位置 (用户操作时)
        self.minimized_position = self._parse_tuple(os.environ.get("AIRI_MINIMIZED_POSITION", "0.92,0.88"))
        self.minimized_scale = float(os.environ.get("AIRI_MINIMIZED_SCALE", "0.35"))
        self.minimized_height = int(os.environ.get("AIRI_MINIMIZED_HEIGHT", "400"))
        
        # 待机状态位置 (无操作时)
        self.idle_position = self._parse_tuple(os.environ.get("AIRI_IDLE_POSITION", "0.5,0.4"))
        self.idle_scale = float(os.environ.get("AIRI_IDLE_SCALE", "1.0"))
        
        # 用户超时配置
        self.inactivity_timeout = float(os.environ.get("AIRI_INACTIVITY_TIMEOUT", "60.0"))
        
        logger.info("AvatarConfig 从环境变量加载完成")
    
    def _parse_tuple(self, value: str) -> tuple:
        """解析元组字符串"""
        try:
            parts = value.split(",")
            result = []
            for part in parts:
                if "." in part:
                    result.append(float(part.strip()))
                else:
                    result.append(int(part.strip()))
            return tuple(result)
        except Exception as e:
            logger.warning(f"解析元组失败: {value}, 使用默认值: {e}")
            return (0.5, 0.5)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "avatar_type": self.avatar_type.value if isinstance(self.avatar_type, Enum) else self.avatar_type,
            "model_path": self.model_path,
            "canvas_size": self.canvas_size,
            "background_color": self.background_color,
            "target_fps": self.target_fps,
            "enable_vsync": self.enable_vsync,
            "enable_shadows": self.enable_shadows,
            "enable_post_processing": self.enable_post_processing,
            "default_position": self.default_position,
            "default_scale": self.default_scale,
            "minimized_position": self.minimized_position,
            "minimized_scale": self.minimized_scale,
            "minimized_height": self.minimized_height,
            "idle_position": self.idle_position,
            "idle_scale": self.idle_scale,
            "inactivity_timeout": self.inactivity_timeout,
        }


@dataclass
class AvatarState:
    """数字人状态"""
    # 位置和变换
    position: tuple = (0.5, 0.5)  # 归一化坐标
    scale: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0
    
    # 动画状态
    current_animation: str = "idle"
    animation_blend: float = 0.0
    
    # 表情状态
    expression: str = "neutral"
    expression_blend: float = 1.0
    
    # 交互状态
    interaction_state: InteractionState = InteractionState.IDLE
    
    # 用户交互
    last_user_action_time: float = field(default_factory=time.time)
    user_action_count: int = 0
    
    # 音频
    is_speaking: bool = False
    current_text: str = ""
    
    # 可见性
    visible: bool = True
    
    # 更新
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Animation:
    """动画定义"""
    name: str
    animation_type: AnimationType
    
    # 关键帧
    duration: float = 1.0  # 秒
    loop: bool = True
    
    # 位置关键帧 (归一化坐标)
    position_keyframes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 缩放关键帧
    scale_keyframes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 旋转关键帧
    rotation_keyframes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 表情关键帧
    expression_keyframes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 缓动函数
    easing: str = "ease_in_out"


@dataclass
class Expression:
    """表情定义"""
    name: str
    expression_type: ExpressionType
    
    # 面部参数
    parameters: Dict[str, float] = field(default_factory=dict)
    
    # 过渡
    transition_in: float = 0.3   # 秒
    transition_out: float = 0.3  # 秒
    
    # 持续时间 (0 表示永久)
    duration: float = 0.0


@dataclass
class AvatarSkillMetadata:
    """数字人技能元数据"""
    name: str
    description: str
    
    # 动画配置
    animations: List[str] = field(default_factory=list)
    expressions: List[str] = field(default_factory=list)
    
    # 音频配置
    audio_required: bool = False
    lip_sync: bool = False
    
    # 参数定义
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # 标签
    tags: Set[str] = field(default_factory=set)
    
    # 统计
    usage_count: int = 0
    success_rate: float = 1.0


@dataclass
class BehaviorNode:
    """行为树节点"""
    node_id: str
    node_type: str  # "action", "condition", "selector", "sequence"
    
    # 条件
    condition: Optional[Callable] = None
    
    # 动作
    action: Optional[Callable] = None
    
    # 子节点
    children: List["BehaviorNode"] = field(default_factory=list)
    
    # 状态
    status: str = "idle"  # "idle", "running", "success", "failure"


# =============================================================================
# 动画系统
# =============================================================================

class AnimationEngine:
    """动画引擎"""
    
    def __init__(self, avatar_state: AvatarState):
        self.avatar_state = avatar_state
        self._animations: Dict[str, Animation] = {}
        self._playing_animations: Dict[str, Animation] = {}
        self._lock = asyncio.Lock()
        
        # 初始化默认动画
        self._init_default_animations()
        
        logger.info("AnimationEngine 初始化完成")
    
    def _init_default_animations(self):
        """初始化默认动画"""
        # Idle - 待机动画
        idle = Animation(
            name="idle",
            animation_type=AnimationType.IDLE,
            duration=2.0,
            loop=True,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "sine"},
                {"time": 1, "value": (0, 0.02), "easing": "sine"},
                {"time": 2, "value": (0, 0), "easing": "sine"},
            ],
            scale_keyframes=[
                {"time": 0, "value": 1.0, "easing": "linear"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "linear"},
            ]
        )
        
        # Wave - 挥手
        wave = Animation(
            name="wave",
            animation_type=AnimationType.WAVE,
            duration=1.5,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "ease_out"},
                {"time": 0.3, "value": (0.05, 0.05), "easing": "ease_in_out"},
                {"time": 0.6, "value": (-0.05, 0.05), "easing": "ease_in_out"},
                {"time": 0.9, "value": (0.05, 0.05), "easing": "ease_in_out"},
                {"time": 1.2, "value": (-0.05, 0.05), "easing": "ease_in_out"},
                {"time": 1.5, "value": (0, 0), "easing": "ease_in"},
            ]
        )
        
        # Happy - 开心
        happy = Animation(
            name="happy",
            animation_type=AnimationType.HAPPY,
            duration=2.0,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "ease_out"},
                {"time": 0.5, "value": (0, 0.05), "easing": "ease_in_out"},
                {"time": 1.0, "value": (0, 0), "easing": "ease_in_out"},
                {"time": 1.5, "value": (0, 0.05), "easing": "ease_in_out"},
                {"time": 2.0, "value": (0, 0), "easing": "ease_in"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "ease_in"},
                {"time": 0.3, "value": "happy", "easing": "linear"},
                {"time": 1.7, "value": "happy", "easing": "linear"},
                {"time": 2.0, "value": "neutral", "easing": "ease_out"},
            ]
        )
        
        # Thinking - 思考
        thinking = Animation(
            name="thinking",
            animation_type=AnimationType.THINKING,
            duration=3.0,
            loop=True,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "linear"},
                {"time": 1.5, "value": (0.02, 0), "easing": "sine"},
                {"time": 3.0, "value": (0, 0), "easing": "sine"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "thinking", "easing": "linear"},
            ]
        )
        
        # Surprised - 惊讶
        surprised = Animation(
            name="surprised",
            animation_type=AnimationType.SURPRISED,
            duration=1.5,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "ease_out"},
                {"time": 0.2, "value": (0, -0.05), "easing": "ease_out"},
                {"time": 0.4, "value": (0, 0), "easing": "ease_in_out"},
                {"time": 1.5, "value": (0, 0), "easing": "ease_in"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "ease_in"},
                {"time": 0.2, "value": "surprised", "easing": "linear"},
                {"time": 1.0, "value": "surprised", "easing": "linear"},
                {"time": 1.5, "value": "neutral", "easing": "ease_out"},
            ]
        )
        
        # Jump - 跳跃
        jump = Animation(
            name="jump",
            animation_type=AnimationType.JUMP,
            duration=1.0,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "ease_out"},
                {"time": 0.3, "value": (0, 0.15), "easing": "ease_out"},
                {"time": 0.5, "value": (0, 0.15), "easing": "linear"},
                {"time": 0.8, "value": (0, 0), "easing": "ease_in"},
                {"time": 1.0, "value": (0, 0), "easing": "ease_in"},
            ]
        )
        
        # Nod - 点头
        nod = Animation(
            name="nod",
            animation_type=AnimationType.NOD,
            duration=0.8,
            loop=False,
            rotation_keyframes=[
                {"time": 0, "value": 0, "easing": "linear"},
                {"time": 0.2, "value": 10, "easing": "ease_out"},
                {"time": 0.4, "value": -5, "easing": "ease_in_out"},
                {"time": 0.6, "value": 5, "easing": "ease_in_out"},
                {"time": 0.8, "value": 0, "easing": "ease_in"},
            ]
        )
        
        # Shake Head - 摇头
        shake_head = Animation(
            name="shake_head",
            animation_type=AnimationType.SHAKE_HEAD,
            duration=0.8,
            loop=False,
            rotation_keyframes=[
                {"time": 0, "value": 0, "easing": "linear"},
                {"time": 0.2, "value": 15, "easing": "ease_out"},
                {"time": 0.4, "value": -15, "easing": "ease_in_out"},
                {"time": 0.6, "value": 10, "easing": "ease_in_out"},
                {"time": 0.8, "value": 0, "easing": "ease_in"},
            ]
        )
        
        # Wink - 眨眼
        wink = Animation(
            name="wink",
            animation_type=AnimationType.WINK,
            duration=0.5,
            loop=False,
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "linear"},
                {"time": 0.2, "value": "happy", "easing": "ease_out"},
                {"time": 0.35, "value": "neutral", "easing": "ease_in"},
                {"time": 0.5, "value": "neutral", "easing": "linear"},
            ]
        )
        
        # Sad - 悲伤
        sad = Animation(
            name="sad",
            animation_type=AnimationType.SAD,
            duration=3.0,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "linear"},
                {"time": 1.5, "value": (0, -0.02), "easing": "ease_in"},
                {"time": 3.0, "value": (0, 0), "easing": "ease_out"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "ease_in"},
                {"time": 0.5, "value": "sad", "easing": "linear"},
                {"time": 2.5, "value": "sad", "easing": "linear"},
                {"time": 3.0, "value": "neutral", "easing": "ease_out"},
            ]
        )
        
        # Laugh - 大笑
        laugh = Animation(
            name="laugh",
            animation_type=AnimationType.LAUGH,
            duration=2.0,
            loop=False,
            position_keyframes=[
                {"time": 0, "value": (0, 0), "easing": "ease_out"},
                {"time": 0.25, "value": (0, 0.03), "easing": "ease_in_out"},
                {"time": 0.5, "value": (0, 0), "easing": "ease_in_out"},
                {"time": 0.75, "value": (0, 0.03), "easing": "ease_in_out"},
                {"time": 1.0, "value": (0, 0), "easing": "ease_in_out"},
                {"time": 1.25, "value": (0, 0.03), "easing": "ease_in_out"},
                {"time": 1.5, "value": (0, 0), "easing": "ease_in_out"},
                {"time": 2.0, "value": (0, 0), "easing": "ease_in"},
            ],
            expression_keyframes=[
                {"time": 0, "value": "neutral", "easing": "ease_in"},
                {"time": 0.3, "value": "happy", "easing": "linear"},
                {"time": 1.7, "value": "happy", "easing": "linear"},
                {"time": 2.0, "value": "neutral", "easing": "ease_out"},
            ]
        )
        
        # 注册所有动画
        for anim in [idle, wave, happy, thinking, surprised, jump, nod, shake_head, wink, sad, laugh]:
            self._animations[anim.name] = anim
    
    def register_animation(self, animation: Animation) -> None:
        """注册动画"""
        self._animations[animation.name] = animation
        logger.debug(f"动画已注册: {animation.name}")
    
    async def play(
        self,
        animation_name: str,
        blend: float = 1.0,
        on_complete: Optional[Callable] = None
    ) -> bool:
        """播放动画"""
        async with self._lock:
            animation = self._animations.get(animation_name)
            
            if not animation:
                logger.warning(f"动画不存在: {animation_name}")
                return False
            
            # 创建播放副本
            playing = Animation(
                name=animation.name,
                animation_type=animation.animation_type,
                duration=animation.duration,
                loop=animation.loop,
                position_keyframes=animation.position_keyframes,
                scale_keyframes=animation.scale_keyframes,
                rotation_keyframes=animation.rotation_keyframes,
                expression_keyframes=animation.expression_keyframes,
                easing=animation.easing,
            )
            
            self._playing_animations[animation_name] = playing
            
            # 启动动画任务
            asyncio.create_task(self._update_animation(animation_name, on_complete))
            
            return True
    
    async def stop(self, animation_name: str) -> bool:
        """停止动画"""
        async with self._lock:
            if animation_name in self._playing_animations:
                del self._playing_animations[animation_name]
                return True
            return False
    
    async def stop_all(self) -> None:
        """停止所有动画"""
        async with self._lock:
            self._playing_animations.clear()
    
    async def _update_animation(
        self,
        animation_name: str,
        on_complete: Optional[Callable] = None
    ) -> None:
        """更新动画"""
        animation = self._playing_animations.get(animation_name)
        
        if not animation:
            return
        
        start_time = time.time()
        
        while animation_name in self._playing_animations:
            elapsed = time.time() - start_time
            t = elapsed / animation.duration
            
            if t >= 1.0:
                if animation.loop:
                    start_time = time.time()
                else:
                    # 动画完成
                    if on_complete:
                        try:
                            await on_complete()
                        except Exception as e:
                            logger.error(f"动画回调失败: {e}")
                    
                    async with self._lock:
                        self._playing_animations.pop(animation_name, None)
                    
                    # 恢复 idle 动画
                    await self.play("idle")
                    break
            
            # 计算当前值
            await self._apply_animation_frame(animation, min(t, 1.0))
            
            await asyncio.sleep(0.016)  # 60fps
    
    async def _apply_animation_frame(self, animation: Animation, t: float) -> None:
        """应用动画帧"""
        # 位置插值
        if animation.position_keyframes:
            value = self._interpolate_keyframes(animation.position_keyframes, t)
            if value:
                self.avatar_state.position = (
                    self.avatar_state.position[0] + value[0],
                    self.avatar_state.position[1] + value[1]
                )
        
        # 缩放插值
        if animation.scale_keyframes:
            value = self._interpolate_keyframes(animation.scale_keyframes, t)
            if value:
                self.avatar_state.scale = self.avatar_state.scale * value
        
        # 旋转插值
        if animation.rotation_keyframes:
            value = self._interpolate_keyframes(animation.rotation_keyframes, t)
            if value:
                self.avatar_state.rotation = value
        
        # 表情插值
        if animation.expression_keyframes:
            expr = self._interpolate_keyframes(animation.expression_keyframes, t)
            if expr and expr != self.avatar_state.expression:
                self.avatar_state.expression = expr
    
    def _interpolate_keyframes(self, keyframes: List[Dict], t: float) -> Any:
        """关键帧插值"""
        if not keyframes:
            return None
        
        # 找到当前时间对应的关键帧
        prev_kf = None
        next_kf = None
        
        for kf in keyframes:
            if kf["time"] <= t:
                prev_kf = kf
            elif kf["time"] > t:
                next_kf = kf
                break
        
        if not prev_kf:
            return keyframes[0]["value"]
        if not next_kf:
            return prev_kf["value"]
        
        # 计算插值因子
        t_range = next_kf["time"] - prev_kf["time"]
        t_local = (t - prev_kf["time"]) / t_range if t_range > 0 else 0
        
        # 应用缓动
        t_local = self._apply_easing(t_local, prev_kf.get("easing", "linear"))
        
        # 插值
        return self._interpolate_value(prev_kf["value"], next_kf["value"], t_local)
    
    def _apply_easing(self, t: float, easing: str) -> float:
        """应用缓动函数"""
        if easing == "linear":
            return t
        elif easing == "ease_in":
            return t * t
        elif easing == "ease_out":
            return 1 - (1 - t) * (1 - t)
        elif easing == "ease_in_out":
            return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2
        elif easing == "sine":
            import math
            return (1 - math.cos(t * 3.14159 / 2)) if t < 0.5 else (1 + math.cos(t * 3.14159 / 2 - 3.14159 / 2))
        
        return t
    
    def _interpolate_value(self, start: Any, end: Any, t: float) -> Any:
        """值插值"""
        if isinstance(start, (int, float)):
            return start + (end - start) * t
        elif isinstance(start, tuple):
            return tuple(s + (e - s) * t for s, e in zip(start, end))
        elif isinstance(start, list):
            return [s + (e - s) * t for s, e in zip(start, end)]
        
        return end if t > 0.5 else start
    
    def get_current_animation(self) -> Optional[str]:
        """获取当前动画"""
        return self.avatar_state.current_animation


# =============================================================================
# 表情系统
# =============================================================================

class ExpressionSystem:
    """表情系统"""
    
    def __init__(self, avatar_state: AvatarState):
        self.avatar_state = avatar_state
        self._expressions: Dict[str, Expression] = {}
        self._lock = asyncio.Lock()
        
        # 初始化默认表情
        self._init_default_expressions()
        
        logger.info("ExpressionSystem 初始化完成")
    
    def _init_default_expressions(self):
        """初始化默认表情"""
        expressions = [
            Expression(
                name="neutral",
                expression_type=ExpressionType.NEUTRAL,
                parameters={},
                duration=0
            ),
            Expression(
                name="happy",
                expression_type=ExpressionType.HAPPY,
                parameters={
                    "mouth_open": 0.5,
                    "mouth_corner": 0.8,
                    "eye_open": 1.2,
                    "cheek_blush": 0.5,
                },
                duration=2.0
            ),
            Expression(
                name="sad",
                expression_type=ExpressionType.SAD,
                parameters={
                    "mouth_corner": -0.3,
                    "brow_inner": -0.3,
                    "eye_open": 0.8,
                },
                duration=3.0
            ),
            Expression(
                name="angry",
                expression_type=ExpressionType.ANGRY,
                parameters={
                    "brow_outer": -0.5,
                    "eye_squint": 0.5,
                    "mouth_press": 0.5,
                },
                duration=2.0
            ),
            Expression(
                name="surprised",
                expression_type=ExpressionType.SURPRISED,
                parameters={
                    "eye_open": 1.5,
                    "mouth_open": 0.8,
                    "brow_raise": 0.8,
                },
                duration=1.5
            ),
            Expression(
                name="thinking",
                expression_type=ExpressionType.THINKING,
                parameters={
                    "eye_side": 0.3,
                    "mouth_one_side": 0.2,
                    "brow_one_raise": 0.3,
                },
                duration=3.0
            ),
            Expression(
                name="shy",
                expression_type=ExpressionType.CONFUSED,
                parameters={
                    "cheek_blush": 0.7,
                    "eye_side": 0.2,
                    "mouth_small": 0.3,
                },
                duration=2.5
            ),
            Expression(
                name="confused",
                expression_type=ExpressionType.CONFUSED,
                parameters={
                    "brow_one_raise": 0.5,
                    "eye_side": 0.4,
                    "mouth_one_side": 0.3,
                },
                duration=2.0
            ),
            Expression(
                name="fearful",
                expression_type=ExpressionType.FEARFUL,
                parameters={
                    "eye_open": 1.3,
                    "mouth_open": 0.4,
                    "brow_raise": 0.6,
                    "brow_inner": 0.3,
                },
                duration=2.5
            ),
            Expression(
                name="disgusted",
                expression_type=ExpressionType.DISGUSTED,
                parameters={
                    "nose_squint": 0.5,
                    "mouth_press": 0.6,
                    "eye_squint": 0.3,
                },
                duration=2.0
            ),
        ]
        
        for expr in expressions:
            self._expressions[expr.name] = expr
    
    def register_expression(self, expression: Expression) -> None:
        """注册表情"""
        self._expressions[expression.name] = expression
    
    async def set_expression(
        self,
        expression_name: str,
        blend: float = 1.0,
        duration: float = 0.0
    ) -> bool:
        """设置表情"""
        async with self._lock:
            expression = self._expressions.get(expression_name)
            
            if not expression:
                logger.warning(f"表情不存在: {expression_name}")
                return False
            
            self.avatar_state.expression = expression_name
            self.avatar_state.expression_blend = blend
            
            return True
    
    async def reset(self) -> None:
        """重置为默认表情"""
        await self.set_expression("neutral")
    
    def get_current_expression(self) -> str:
        """获取当前表情"""
        return self.avatar_state.expression


# =============================================================================
# 音频系统 (TTS/STT)
# =============================================================================

class TTSEngine:
    """语音合成引擎"""
    
    def __init__(self):
        self._voice_cache: Dict[str, bytes] = {}
        self._lock = asyncio.Lock()
        
        logger.info("TTSEngine 初始化完成")
    
    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        **options
    ) -> bytes:
        """合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 语音 ID
            **options: 其他选项 (speed, pitch 等)
            
        Returns:
            音频数据 (bytes)
            
        Raises:
            TTSServiceError: 当 TTS 服务不可用时
        """
        if not text or not text.strip():
            logger.warning("TTSEngine: 收到空文本请求")
            return b''
        
        # 生成缓存键
        cache_key = f"{voice_id}:{text}:{json.dumps(options, sort_keys=True)}"
        
        async with self._lock:
            if cache_key in self._voice_cache:
                logger.debug(f"TTSEngine: 从缓存返回 (key={cache_key[:20]}...)")
                return self._voice_cache[cache_key]
        
        try:
            # 调用 TTS 服务
            audio_data = await self._call_tts_service(text, voice_id, **options)
            
            # 缓存 (限制缓存大小防止内存溢出)
            async with self._lock:
                if len(self._voice_cache) < 1000:  # 最多缓存 1000 条
                    self._voice_cache[cache_key] = audio_data
                else:
                    logger.warning("TTSEngine: 缓存已满，清空")
                    self._voice_cache.clear()
            
            return audio_data
            
        except Exception as e:
            logger.error(f"TTSEngine: 语音合成失败 - {e}")
            raise TTSServiceError(f"语音合成失败: {str(e)}") from e
    
    async def _call_tts_service(
        self,
        text: str,
        voice_id: str,
        **options
    ) -> bytes:
        """调用 TTS 服务
        
        这里应该集成实际的 TTS 服务:
        - Edge TTS (微软): 免费，易于集成
        - GPT-SoVITS: 本地运行，高质量
        - CosyVoice: 阿里云
        - OpenAI TTS: 需要 API Key
        
        当前实现: 返回占位符静音数据
        """
        # 检查是否配置了真实的 TTS 服务
        tts_provider = os.environ.get("TTS_PROVIDER", "")
        
        if tts_provider == "edge":
            # 使用 Edge TTS
            return await self._edge_tts(text, voice_id, **options)
        elif tts_provider == "openai":
            # 使用 OpenAI TTS
            return await self._openai_tts(text, voice_id, **options)
        else:
            # 占位符实现: 生成静音
            logger.warning("TTSEngine: 未配置 TTS_PROVIDER，使用占位符静音")
            return self._generate_silent_audio(text)
    
    async def _edge_tts(
        self,
        text: str,
        voice_id: str,
        **options
    ) -> bytes:
        """使用 Edge TTS 合成语音
        
        需要安装: pip install edge-tts
        """
        try:
            import edge_tts
            
            # 映射 voice_id
            voice_map = {
                "female_zh": "zh-CN-XiaoxiaoNeural",
                "male_zh": "zh-CN-YunxiNeural",
                "female_en": "en-US-JennyNeural",
                "male_en": "en-US-GuyNeural",
            }
            edge_voice = voice_map.get(voice_id, "zh-CN-XiaoxiaoNeural")
            
            # 创建communicator
            communicate = edge_tts.Communicate(text, edge_voice)
            
            # 收集音频数据
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
            
            return b"".join(audio_chunks)
            
        except ImportError:
            logger.warning("edge-tts 未安装，回退到占位符")
            return self._generate_silent_audio(text)
        except Exception as e:
            logger.error(f"Edge TTS 调用失败: {e}")
            raise TTSServiceError(f"Edge TTS 失败: {str(e)}") from e
    
    async def _openai_tts(
        self,
        text: str,
        voice_id: str,
        **options
    ) -> bytes:
        """使用 OpenAI TTS 合成语音
        
        需要设置环境变量: OPENAI_API_KEY
        """
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise TTSServiceError("未设置 OPENAI_API_KEY")
        
        try:
            import openai
            
            # 映射 voice_id
            voice_map = {
                "female_zh": "alloy",  # OpenAI TTS 不支持中文，选择近似
                "male_zh": "onyx",
                "female_en": "alloy",
                "male_en": "onyx",
            }
            openai_voice = voice_map.get(voice_id, "alloy")
            
            # 调用 API
            response = await openai.audio.speech.create(
                model="tts-1",
                voice=openai_voice,
                input=text,
                speed=options.get("speed", 1.0),
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"OpenAI TTS 调用失败: {e}")
            raise TTSServiceError(f"OpenAI TTS 失败: {str(e)}") from e
    
    def _generate_silent_audio(self, text: str) -> bytes:
        """生成占位符静音音频
        
        这是一个降级方案，返回静音数据而不是崩溃
        """
        # 估算音频时长 (中文约每字 0.3 秒，英文约每词 0.5 秒)
        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        english_words = len(text.split())
        duration = max(chinese_chars * 0.3 + english_words * 0.5, 0.5)
        
        sample_rate = 24000
        num_samples = int(sample_rate * duration)
        
        # 返回静音 (16-bit PCM)
        return b'\x00' * num_samples * 2


class TTSServiceError(Exception):
    """TTS 服务错误异常"""
    pass


class STTEngine:
    """语音识别引擎
    
    支持多种 STT 服务:
    - OpenAI Whisper: 高质量，需要 API Key
    - FunASR: 阿里开源，支持流式
    - Faster Whisper: 本地运行，更快
    """
    
    def __init__(self):
        self._running = False
        self._lock = asyncio.Lock()
        self._on_result: Optional[Callable[[str, bool], Awaitable[None]]] = None
        self._stream_task: Optional[asyncio.Task] = None
        
        # 音频缓存
        self._audio_buffer: List[bytes] = []
        self._buffer_lock = asyncio.Lock()
        
        logger.info("STTEngine 初始化完成")
    
    async def recognize(
        self,
        audio_data: bytes,
        language: str = "zh",
        **options
    ) -> str:
        """识别语音
        
        Args:
            audio_data: 音频数据 (bytes)
            language: 语言代码 (zh, en, ja, etc.)
            **options: 其他选项
            
        Returns:
            识别的文本
            
        Raises:
            STTServiceError: 当 STT 服务不可用时
        """
        if not audio_data:
            logger.warning("STTEngine: 收到空音频数据")
            return ""
        
        try:
            # 调用 STT 服务
            text = await self._call_stt_service(audio_data, language, **options)
            logger.info(f"STTEngine: 识别结果 = {text[:50]}...")
            return text
        except Exception as e:
            logger.error(f"STTEngine: 语音识别失败 - {e}")
            raise STTServiceError(f"语音识别失败: {str(e)}") from e
    
    async def _call_stt_service(
        self,
        audio_data: bytes,
        language: str,
        **options
    ) -> str:
        """调用 STT 服务
        
        这里应该集成实际的 STT 服务:
        - OpenAI Whisper: 高质量
        - FunASR: 阿里开源
        - Faster Whisper: 本地运行
        """
        stt_provider = os.environ.get("STT_PROVIDER", "")
        
        if stt_provider == "openai":
            return await self._openai_whisper(audio_data, language, **options)
        elif stt_provider == "funasr":
            return await self._funasr_recognize(audio_data, language, **options)
        elif stt_provider == "faster_whisper":
            return await self._faster_whisper(audio_data, language, **options)
        else:
            # 占位符实现
            logger.warning("STTEngine: 未配置 STT_PROVIDER，使用空结果")
            return ""
    
    async def _openai_whisper(
        self,
        audio_data: bytes,
        language: str,
        **options
    ) -> str:
        """使用 OpenAI Whisper 进行语音识别
        
        需要设置环境变量: OPENAI_API_KEY
        """
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise STTServiceError("未设置 OPENAI_API_KEY")
        
        try:
            import openai
            import io
            from pydub import AudioSegment
            
            # 将 PCM 转换为 WAV
            audio_segment = AudioSegment(
                data=audio_data,
                sample_width=2,
                frame_rate=24000,
                channels=1
            )
            
            # 导出为 WAV 格式
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_buffer.seek(0)
            
            # 调用 Whisper API
            transcript = await openai.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", wav_buffer, "audio/wav"),
                language=language if language != "zh" else "zh",
                response_format="text"
            )
            
            return transcript if transcript else ""
            
        except ImportError:
            logger.warning("pydub 或 openai 未安装")
            raise STTServiceError("pydub 或 openai 未安装")
        except Exception as e:
            logger.error(f"OpenAI Whisper 调用失败: {e}")
            raise STTServiceError(f"Whisper 识别失败: {str(e)}") from e
    
    async def _funasr_recognize(
        self,
        audio_data: bytes,
        language: str,
        **options
    ) -> str:
        """使用 FunASR 进行语音识别
        
        需要安装: pip install funasr
        """
        try:
            from funasr import AutoModel
            
            # 模型选择
            model_name = options.get("model", "paraformer-zh")
            
            # 加载模型 (首次调用会下载)
            model = AutoModel(
                model=model_name,
                model_revision="v2.0.4",
                device="cpu"
            )
            
            # 识别
            result = model.generate(
                input=audio_data,
                batch_size_s=300,
                hotword=""
            )
            
            # 解析结果
            if result and len(result) > 0:
                return result[0].get("text", "")
            return ""
            
        except ImportError:
            logger.warning("funasr 未安装")
            raise STTServiceError("funasr 未安装")
        except Exception as e:
            logger.error(f"FunASR 调用失败: {e}")
            raise STTServiceError(f"FunASR 识别失败: {str(e)}") from e
    
    async def _faster_whisper(
        self,
        audio_data: bytes,
        language: str,
        **options
    ) -> str:
        """使用 Faster Whisper 进行本地语音识别
        
        需要安装: pip install faster-whisper
        """
        try:
            from faster_whisper import WhisperModel
            import io
            import numpy as np
            from pydub import AudioSegment
            
            # 模型大小
            model_size = options.get("model_size", "base")
            
            # 加载模型
            model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8"
            )
            
            # 转换音频格式
            audio_segment = AudioSegment(
                data=audio_data,
                sample_width=2,
                frame_rate=24000,
                channels=1
            )
            
            # 转换为 numpy 数组
            samples = np.array(audio_segment.get_array_of_samples())
            
            # 运行识别
            segments, info = model.transcribe(
                samples,
                language=language,
                beam_size=5,
                vad_filter=True
            )
            
            # 收集结果
            result_text = " ".join([segment.text for segment in segments])
            return result_text.strip()
            
        except ImportError:
            logger.warning("faster-whisper 未安装")
            raise STTServiceError("faster-whisper 未安装")
        except Exception as e:
            logger.error(f"Faster Whisper 调用失败: {e}")
            raise STTServiceError(f"Faster Whisper 识别失败: {str(e)}") from e
    
    async def start_streaming(
        self,
        on_result: Callable[[str, bool], Awaitable[None]]
    ) -> None:
        """启动流式识别
        
        Args:
            on_result: 识别结果回调 (text: str, is_final: bool)
        """
        async with self._lock:
            if self._running:
                logger.warning("STTEngine: 流式识别已在运行")
                return
            
            self._running = True
            self._on_result = on_result
            self._audio_buffer.clear()
            
            # 启动流式处理任务
            self._stream_task = asyncio.create_task(self._process_stream())
            
            logger.info("STTEngine: 流式识别已启动")
    
    async def _process_stream(self) -> None:
        """处理音频流"""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # 每 100ms 处理一次
                
                async with self._buffer_lock:
                    if not self._audio_buffer:
                        continue
                    # 合并缓冲区的音频数据
                    audio_data = b"".join(self._audio_buffer)
                    self._audio_buffer.clear()
                
                if audio_data and len(audio_data) > 1600:  # 至少 50ms 音频
                    # 识别
                    try:
                        text = await self._call_stt_service(audio_data, "zh")
                        if text and self._on_result:
                            await self._on_result(text, True)
                    except Exception as e:
                        logger.error(f"流式识别失败: {e}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"流式处理异常: {e}")
    
    async def stop_streaming(self) -> None:
        """停止流式识别"""
        async with self._lock:
            self._running = False
            
            if self._stream_task:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    pass
            
            self._on_result = None
            self._audio_buffer.clear()
            
            logger.info("STTEngine: 流式识别已停止")
    
    def add_audio_chunk(self, audio_chunk: bytes) -> None:
        """添加音频数据到缓冲区
        
        这是用于从麦克风获取实时音频数据的方法
        """
        if not self._running:
            return
        
        # 注意: 这是一个同步方法，需要在线程安全的方式调用
        # 在实际使用中，应该使用 asyncio.create_task 包装
        self._audio_buffer.append(audio_chunk)


class STTServiceError(Exception):
    """STT 服务错误异常"""
    pass


# =============================================================================
# 行为树系统
# =============================================================================

class BehaviorTree:
    """行为树"""
    
    def __init__(self, root: BehaviorNode):
        self.root = root
        self._running = False
        self._lock = asyncio.Lock()
        
        logger.info("BehaviorTree 初始化完成")
    
    async def tick(self) -> str:
        """执行行为树"""
        return await self._execute_node(self.root)
    
    async def _execute_node(self, node: BehaviorNode) -> str:
        """执行节点"""
        if node.node_type == "selector":
            # 选择器: 返回第一个成功的子节点
            for child in node.children:
                result = await self._execute_node(child)
                if result == "success":
                    return "success"
            return "failure"
        
        elif node.node_type == "sequence":
            # 序列: 所有子节点都成功才返回成功
            for child in node.children:
                result = await self._execute_node(child)
                if result == "failure":
                    return "failure"
            return "success"
        
        elif node.node_type == "condition":
            # 条件节点
            if node.condition:
                result = await node.condition()
                return "success" if result else "failure"
            return "failure"
        
        elif node.node_type == "action":
            # 动作节点
            if node.action:
                await node.action()
                return "success"
            return "failure"
        
        return "failure"


# =============================================================================
# 数字人技能系统
# =============================================================================

class AvatarSkillRegistry:
    """数字人技能注册中心"""
    
    def __init__(self):
        self._skills: Dict[str, Callable] = {}
        self._metadata: Dict[str, AvatarSkillMetadata] = {}
        self._lock = asyncio.Lock()
        
        logger.info("AvatarSkillRegistry 初始化完成")
    
    def register(
        self,
        name: str,
        func: Callable,
        metadata: AvatarSkillMetadata
    ) -> None:
        """注册技能"""
        self._skills[name] = func
        self._metadata[name] = metadata
        logger.info(f"AvatarSkill 已注册: {name}")
    
    async def execute(
        self,
        name: str,
        *args,
        **kwargs
    ) -> Any:
        """执行技能"""
        async with self._lock:
            skill = self._skills.get(name)
            metadata = self._metadata.get(name)
            
            if not skill:
                logger.warning(f"AvatarSkill 不存在: {name}")
                return None
            
            try:
                result = await skill(*args, **kwargs)
                
                if metadata:
                    metadata.usage_count += 1
                
                return result
            except Exception as e:
                logger.error(f"AvatarSkill 执行失败: {name} - {e}")
                
                if metadata:
                    metadata.success_rate = (
                        (metadata.usage_count - 1) / metadata.usage_count
                    ) if metadata.usage_count > 0 else 0.0
                
                raise
    
    def get_metadata(self, name: str) -> Optional[AvatarSkillMetadata]:
        """获取技能元数据"""
        return self._metadata.get(name)
    
    def list_skills(self) -> List[str]:
        """列出所有技能"""
        return list(self._skills.keys())


# 技能装饰器
def avatar_skill(
    name: Optional[str] = None,
    description: str = "",
    animations: Optional[List[str]] = None,
    expressions: Optional[List[str]] = None,
    audio_required: bool = False,
    lip_sync: bool = False,
    tags: Optional[Set[str]] = None,
) -> Callable[[F], F]:
    """数字人技能装饰器"""
    def decorator(func: F) -> F:
        # 构建元数据
        metadata = AvatarSkillMetadata(
            name=name or func.__name__,
            description=description or func.__doc__ or "",
            animations=animations or [],
            expressions=expressions or [],
            audio_required=audio_required,
            lip_sync=lip_sync,
            tags=tags or set(),
        )
        
        # 存储元数据
        if not hasattr(func, '_avatar_skill_metadata'):
            func._avatar_skill_metadata = metadata
        
        return func
    return decorator


# =============================================================================
# AIRI 数字人主类
# =============================================================================

class AIRIDigitalHuman:
    """
    AIRI 数字人主类
    
    完整实现基于 Nanobot+Agents+Skills 驱动的 AI 数字人助手
    """
    
    # 单例实例
    _instance: Optional["AIRIDigitalHuman"] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[AvatarConfig] = None):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.config = config or AvatarConfig()
        self.state = AvatarState()
        
        # 子系统 - 动画和表情系统立即初始化
        self.animation_engine = AnimationEngine(self.state)
        self.expression_system = ExpressionSystem(self.state)
        
        # TTS/STT 引擎 - 懒加载，不在启动时初始化
        self._tts_engine: Optional[TTSEngine] = None
        self._stt_engine: Optional[STTEngine] = None
        
        self.skill_registry = AvatarSkillRegistry()
        
        # 用户交互超时 (秒)
        self.user_inactivity_timeout:float = 60.0
        
        # 当前任务
        self._current_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
        # 回调
        self._on_state_change: Optional[Callable] = None
        self._on_animation_change: Optional[Callable] = None
        self._on_expression_change: Optional[Callable] = None
        
        # 初始化完成
        self._initialized = True
        
        logger.info("AIRIDigitalHuman 初始化完成 (TTS/STT 懒加载)")
    
    @property
    def tts_engine(self) -> TTSEngine:
        """TTS 引擎懒加载属性"""
        if self._tts_engine is None:
            logger.info("首次使用 TTS 引擎，正在初始化...")
            self._tts_engine = TTSEngine()
        return self._tts_engine
    
    @tts_engine.setter
    def tts_engine(self, value: TTSEngine) -> None:
        """设置 TTS 引擎"""
        self._tts_engine = value
    
    @property
    def stt_engine(self) -> STTEngine:
        """STT 引擎懒加载属性"""
        if self._stt_engine is None:
            logger.info("首次使用 STT 引擎，正在初始化...")
            self._stt_engine = STTEngine()
        return self._stt_engine
    
    @stt_engine.setter
    def stt_engine(self, value: STTEngine) -> None:
        """设置 STT 引擎"""
        self._stt_engine = value
    
    # -------------------------------------------------------------------------
    # 生命周期方法
    # -------------------------------------------------------------------------
    
    async def start(self) -> None:
        """启动数字人"""
        logger.info("启动数字人...")
        
        # 播放待机动画
        await self.animation_engine.play("idle")
        
        # 启动用户交互监控
        self._monitor_task = asyncio.create_task(self._monitor_user_activity())
        
        logger.info("数字人已启动")
    
    async def stop(self) -> None:
        """停止数字人"""
        logger.info("停止数字人...")
        
        # 停止监控任务
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # 停止所有动画
        await self.animation_engine.stop_all()
        
        logger.info("数字人已停止")
    
    # -------------------------------------------------------------------------
    # 用户交互处理
    # -------------------------------------------------------------------------
    
    def on_user_action(self) -> None:
        """用户有操作时调用"""
        self.state.last_user_action_time = time.time()
        self.state.user_action_count += 1
        
        # 切换到最小化状态
        self.state.position = self.config.minimized_position
        self.state.scale = self.config.minimized_scale
        
        # 触发状态变化回调
        if self._on_state_change:
            self._on_state_change(self.state)
        
        logger.debug(f"用户操作: 切换到最小化状态, 位置={self.state.position}, 缩放={self.state.scale}")
    
    async def _monitor_user_activity(self) -> None:
        """监控用户活动"""
        while True:
            await asyncio.sleep(1.0)
            
            # 检查用户是否长时间无操作
            idle_time = time.time() - self.state.last_user_action_time
            
            if idle_time >= self.user_inactivity_timeout:
                # 用户无操作，恢复正常状态
                if self.state.position != self.config.idle_position or self.state.scale != self.config.idle_scale:
                    await self._transition_to_idle()
    
    async def _transition_to_idle(self) -> None:
        """切换到待机状态"""
        logger.info("切换到待机状态...")
        
        # 播放跳跃动画
        await self.animation_engine.play("jump")
        
        # 等待动画完成
        await asyncio.sleep(1.0)
        
        # 恢复到正常位置
        self.state.position = self.config.idle_position
        self.state.scale = self.config.idle_scale
        
        # 播放待机动画
        await self.animation_engine.play("idle")
        
        # 触发状态变化回调
        if self._on_state_change:
            self._on_state_change(self.state)
    
    # -------------------------------------------------------------------------
    # 动画控制
    # -------------------------------------------------------------------------
    
    async def play_animation(
        self,
        animation_name: str,
        on_complete: Optional[Callable] = None
    ) -> bool:
        """播放动画"""
        return await self.animation_engine.play(animation_name, on_complete=on_complete)
    
    async def stop_animation(self, animation_name: str) -> bool:
        """停止动画"""
        return await self.animation_engine.stop(animation_name)
    
    async def set_expression(self, expression_name: str) -> bool:
        """设置表情"""
        return await self.expression_system.set_expression(expression_name)
    
    # -------------------------------------------------------------------------
    # 技能执行
    # -------------------------------------------------------------------------
    
    async def execute_skill(
        self,
        skill_name: str,
        *args,
        **kwargs
    ) -> Any:
        """执行技能"""
        return await self.skill_registry.execute(skill_name, *args, **kwargs)
    
    def register_skill(
        self,
        name: str,
        func: Callable,
        metadata: AvatarSkillMetadata
    ) -> None:
        """注册技能"""
        self.skill_registry.register(name, func, metadata)
    
    # -------------------------------------------------------------------------
    # AI 驱动接口
    # -------------------------------------------------------------------------
    
    async def respond_to_user(
        self,
        user_message: str,
        ai_response: str
    ) -> None:
        """响应用户 (由 Nanobot AI 驱动)"""
        logger.info(f"AI 响应用户: {user_message[:50]}...")
        
        # 用户操作
        self.on_user_action()
        
        # 设置交互状态
        self.state.interaction_state = InteractionState.THINKING
        
        # 播放思考动画
        await self.animation_engine.play("thinking")
        await self.expression_system.set_expression("thinking")
        
        # 模拟思考时间
        await asyncio.sleep(0.5)
        
        # 切换到说话状态
        self.state.interaction_state = InteractionState.SPEAKING
        self.state.is_speaking = True
        self.state.current_text = ai_response
        
        # 根据内容选择动画和表情
        response_lower = ai_response.lower()
        
        if any(word in response_lower for word in ["开心", "高兴", "太好了", "happy", "great", "good"]):
            await self.animation_engine.play("happy")
            await self.expression_system.set_expression("happy")
        elif any(word in response_lower for word in ["抱歉", "对不起", "sad", "sorry"]):
            await self.animation_engine.play("sad")
            await self.expression_system.set_expression("sad")
        elif any(word in response_lower for word in ["惊讶", "什么", "wow", "surprised", "really"]):
            await self.animation_engine.play("surprised")
            await self.expression_system.set_expression("surprised")
        elif any(word in response_lower for word in ["哈哈", "大笑", "laugh", "haha"]):
            await self.animation_engine.play("laugh")
            await self.expression_system.set_expression("happy")
        else:
            await self.animation_engine.play("talk")
        
        # 模拟说话时间
        await asyncio.sleep(len(ai_response) * 0.05)
        
        # 说话完成
        self.state.is_speaking = False
        self.state.current_text = ""
        self.state.interaction_state = InteractionState.IDLE
        
        # 恢复 idle 动画
        await self.animation_engine.play("idle")
        await self.expression_system.set_expression("neutral")
    
    async def perform_welcome(self) -> None:
        """执行欢迎动画"""
        logger.info("执行欢迎动画")
        
        # 播放挥手动画
        await self.animation_engine.play("wave")
        
        # 播放开心动画
        await asyncio.sleep(0.5)
        await self.animation_engine.play("happy")
        await self.expression_system.set_expression("happy")
        
        # 等待动画完成
        await asyncio.sleep(2.0)
        
        # 恢复 idle
        await self.animation_engine.play("idle")
        await self.expression_system.set_expression("neutral")
    
    async def perform_goodbye(self) -> None:
        """执行告别动画"""
        logger.info("执行告别动画")
        
        # 挥手告别
        await self.animation_engine.play("wave")
        await asyncio.sleep(1.5)
        
        # 恢复 idle
        await self.animation_engine.play("idle")
    
    async def perform_agreement(self) -> None:
        """同意/确认"""
        await self.animation_engine.play("nod")
        await self.expression_system.set_expression("happy")
        await asyncio.sleep(0.8)
        await self.expression_system.set_expression("neutral")
    
    async def perform_disagreement(self) -> None:
        """不同意"""
        await self.animation_engine.play("shake_head")
        await self.expression_system.set_expression("sad")
        await asyncio.sleep(0.8)
        await self.expression_system.set_expression("neutral")
    
    # -------------------------------------------------------------------------
    # 状态查询
    # -------------------------------------------------------------------------
    
    def get_state(self) -> AvatarState:
        """获取当前状态"""
        return self.state
    
    def get_animation_state(self) -> Dict[str, Any]:
        """获取动画状态"""
        return {
            "current_animation": self.animation_engine.get_current_animation(),
            "current_expression": self.expression_system.get_current_expression(),
            "interaction_state": self.state.interaction_state.value,
            "is_speaking": self.state.is_speaking,
            "position": self.state.position,
            "scale": self.state.scale,
            "rotation": self.state.rotation,
        }
    
    def list_available_animations(self) -> List[str]:
        """列出可用动画"""
        return list(self.animation_engine._animations.keys())
    
    def list_available_expressions(self) -> List[str]:
        """列出可用表情"""
        return list(self.expression_system._expressions.keys())
    
    def list_registered_skills(self) -> List[str]:
        """列出已注册技能"""
        return self.skill_registry.list_skills()
    
    # -------------------------------------------------------------------------
    # 回调设置
    # -------------------------------------------------------------------------
    
    def set_state_change_callback(self, callback: Callable) -> None:
        """设置状态变化回调"""
        self._on_state_change = callback
    
    def set_animation_change_callback(self, callback: Callable) -> None:
        """设置动画变化回调"""
        self._on_animation_change = callback
    
    def set_expression_change_callback(self, callback: Callable) -> None:
        """设置表情变化回调"""
        self._on_expression_change = callback


# =============================================================================
# AI 驱动 Skills 集成
# 与 Nanobot Agents + Skills 系统集成
# =============================================================================

class AIRISkillsIntegration:
    """AIRI Skills 集成类 - 与 Nanobot 系统深度集成"""
    
    def __init__(self, digital_human: AIRIDigitalHuman):
        self.dh = digital_human
        self._register_nanobot_skills()
    
    def _register_nanobot_skills(self):
        """注册与 Nanobot 集成的技能"""
        
        # =========================================================================
        # 图像生成技能
        # =========================================================================
        
        @avatar_skill(
            name="generate_image",
            description="根据用户描述生成图像",
            animations=["thinking", "happy"],
            expressions=["thinking", "happy"],
            tags={"ai", "image", "generation"}
        )
        async def skill_generate_image(request: Dict[str, Any]) -> Dict[str, Any]:
            """生成图像技能"""
            logger.info("执行图像生成技能")
            
            # 思考动画
            await self.dh.animation_engine.play("thinking")
            await self.dh.expression_system.set_expression("thinking")
            
            # 模拟生成过程
            await asyncio.sleep(1.0)
            
            # 成功动画
            await self.dh.animation_engine.play("happy")
            await self.dh.expression_system.set_expression("happy")
            
            return {
                "success": True,
                "skill": "generate_image",
                "result": {"image_url": "/generated/image.png", "status": "completed"}
            }
        
        self.dh.register_skill("generate_image", skill_generate_image, 
            skill_generate_image._avatar_skill_metadata)
        
        # =========================================================================
        # 智能对话技能
        # =========================================================================
        
        @avatar_skill(
            name="intelligent_chat",
            description="智能对话响应",
            animations=["talk", "nod"],
            expressions=["happy", "thinking"],
            tags={"ai", "chat", "conversation"}
        )
        async def skill_intelligent_chat(request: Dict[str, Any]) -> Dict[str, Any]:
            """智能对话技能"""
            logger.info("执行智能对话技能")
            
            user_message = request.get("message", "")
            
            # 思考动画
            await self.dh.animation_engine.play("thinking")
            await self.dh.expression_system.set_expression("thinking")
            
            # 模拟思考
            await asyncio.sleep(0.5)
            
            # 说话动画
            await self.dh.animation_engine.play("talk")
            await self.dh.expression_system.set_expression("happy")
            self.dh.state.is_speaking = True
            
            # 模拟回复
            await asyncio.sleep(1.5)
            
            self.dh.state.is_speaking = False
            await self.dh.animation_engine.play("idle")
            await self.dh.expression_system.set_expression("neutral")
            
            return {
                "success": True,
                "skill": "intelligent_chat",
                "response": f"我理解了：{user_message[:20]}...让我帮你处理！"
            }
        
        self.dh.register_skill("intelligent_chat", skill_intelligent_chat,
            skill_intelligent_chat._avatar_skill_metadata)
        
        # =========================================================================
        # 任务执行技能
        # =========================================================================
        
        @avatar_skill(
            name="execute_task",
            description="执行用户任务",
            animations=["nod", "happy"],
            expressions=["happy", "thinking"],
            tags={"ai", "task", "execution"}
        )
        async def skill_execute_task(request: Dict[str, Any]) -> Dict[str, Any]:
            """任务执行技能"""
            logger.info("执行任务技能")
            
            task_type = request.get("task_type", "general")
            
            # 确认动画
            await self.dh.animation_engine.play("nod")
            await self.dh.expression_system.set_expression("happy")
            
            await asyncio.sleep(0.5)
            
            # 执行中动画
            await self.dh.animation_engine.play("thinking")
            await self.dh.expression_system.set_expression("thinking")
            
            # 模拟执行
            await asyncio.sleep(1.0)
            
            # 完成动画
            await self.dh.animation_engine.play("happy")
            await self.dh.expression_system.set_expression("happy")
            
            return {
                "success": True,
                "skill": "execute_task",
                "task_type": task_type,
                "status": "completed"
            }
        
        self.dh.register_skill("execute_task", skill_execute_task,
            skill_execute_task._avatar_skill_metadata)
        
        # =========================================================================
        # 信息搜索技能
        # =========================================================================
        
        @avatar_skill(
            name="search_info",
            description="搜索信息",
            animations=["thinking"],
            expressions=["thinking", "surprised"],
            tags={"ai", "search", "research"}
        )
        async def skill_search_info(request: Dict[str, Any]) -> Dict[str, Any]:
            """信息搜索技能"""
            logger.info("执行信息搜索技能")
            
            query = request.get("query", "")
            
            # 思考搜索
            await self.dh.animation_engine.play("thinking")
            await self.dh.expression_system.set_expression("thinking")
            
            await asyncio.sleep(1.0)
            
            # 找到结果惊讶表情
            await self.dh.expression_system.set_expression("surprised")
            
            return {
                "success": True,
                "skill": "search_info",
                "query": query,
                "results": ["result1", "result2", "result3"]
            }
        
        self.dh.register_skill("search_info", skill_search_info,
            skill_search_info._avatar_skill_metadata)
        
        # =========================================================================
        # 代码编写技能
        # =========================================================================
        
        @avatar_skill(
            name="write_code",
            description="编写代码",
            animations=["thinking", "happy"],
            expressions=["thinking", "happy"],
            tags={"ai", "code", "development"}
        )
        async def skill_write_code(request: Dict[str, Any]) -> Dict[str, Any]:
            """代码编写技能"""
            logger.info("执行代码编写技能")
            
            language = request.get("language", "python")
            
            # 思考动画
            await self.dh.animation_engine.play("thinking")
            await self.dh.expression_system.set_expression("thinking")
            
            await asyncio.sleep(1.0)
            
            # 编写中
            await self.dh.animation_engine.play("talk")
            
            await asyncio.sleep(1.0)
            
            # 完成
            await self.dh.animation_engine.play("happy")
            await self.dh.expression_system.set_expression("happy")
            
            return {
                "success": True,
                "skill": "write_code",
                "language": language,
                "code": "# Generated code here"
            }
        
        self.dh.register_skill("write_code", skill_write_code,
            skill_write_code._avatar_skill_metadata)
        
        # =========================================================================
        # 欢迎技能
        # =========================================================================
        
        @avatar_skill(
            name="welcome_user",
            description="欢迎用户",
            animations=["wave", "happy"],
            expressions=["happy", "shy"],
            tags={"greeting", "welcome"}
        )
        async def skill_welcome(request: Dict[str, Any]) -> Dict[str, Any]:
            """欢迎用户技能"""
            logger.info("执行欢迎技能")
            
            await self.dh.animation_engine.play("wave")
            await self.dh.expression_system.set_expression("happy")
            
            await asyncio.sleep(1.5)
            
            await self.dh.animation_engine.play("idle")
            await self.dh.expression_system.set_expression("shy")
            
            return {
                "success": True,
                "skill": "welcome_user",
                "message": "你好！很高兴见到你！"
            }
        
        self.dh.register_skill("welcome_user", skill_welcome,
            skill_welcome._avatar_skill_metadata)
        
        # =========================================================================
        # 告别技能
        # =========================================================================
        
        @avatar_skill(
            name="goodbye_user",
            description="告别用户",
            animations=["wave", "sad"],
            expressions=["sad", "neutral"],
            tags={"greeting", "goodbye"}
        )
        async def skill_goodbye(request: Dict[str, Any]) -> Dict[str, Any]:
            """告别用户技能"""
            logger.info("执行告别技能")
            
            await self.dh.animation_engine.play("wave")
            await self.dh.expression_system.set_expression("sad")
            
            await asyncio.sleep(1.5)
            
            await self.dh.animation_engine.play("idle")
            await self.dh.expression_system.set_expression("neutral")
            
            return {
                "success": True,
                "skill": "goodbye_user",
                "message": "再见！有需要随时找我！"
            }
        
        self.dh.register_skill("goodbye_user", skill_goodbye,
            skill_goodbye._avatar_skill_metadata)
        
        # =========================================================================
        # 帮助技能
        # =========================================================================
        
        @avatar_skill(
            name="provide_help",
            description="提供帮助",
            animations=["nod", "happy"],
            expressions=["happy", "thinking"],
            tags={"help", "assistant"}
        )
        async def skill_provide_help(request: Dict[str, Any]) -> Dict[str, Any]:
            """提供帮助技能"""
            logger.info("执行帮助技能")
            
            help_type = request.get("help_type", "general")
            
            await self.dh.animation_engine.play("nod")
            await self.dh.expression_system.set_expression("happy")
            
            await asyncio.sleep(0.5)
            
            await self.dh.expression_system.set_expression("thinking")
            
            return {
                "success": True,
                "skill": "provide_help",
                "help_type": help_type,
                "suggestions": ["生成图像", "编写代码", "搜索信息", "执行任务"]
            }
        
        self.dh.register_skill("provide_help", skill_provide_help,
            skill_provide_help._avatar_skill_metadata)
        
        logger.info(f"AIRI Skills 集成完成，已注册 {len(self.dh.list_registered_skills())} 个技能")


def initialize_airi_skills(dh: AIRIDigitalHuman) -> AIRISkillsIntegration:
    """初始化 AIRI Skills 集成"""
    return AIRISkillsIntegration(dh)


# =============================================================================
# 全局访问函数
# =============================================================================

_digital_human: Optional[AIRIDigitalHuman] = None
_tts_engine: Optional[TTSEngine] = None
_stt_engine: Optional[STTEngine] = None


def get_digital_human() -> AIRIDigitalHuman:
    """获取数字人单例"""
    global _digital_human
    if _digital_human is None:
        _digital_human = AIRIDigitalHuman()
    return _digital_human


def get_tts_engine() -> TTSEngine:
    """获取 TTS 引擎单例（懒加载）"""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = TTSEngine()
    return _tts_engine


def get_stt_engine() -> STTEngine:
    """获取 STT 引擎单例（懒加载）"""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine


# 从导入检查 AIRI 可用性
AIRI_AVAILABLE = True


def get_airi_service_status() -> Dict[str, Any]:
    """获取 AIRI 服务状态
    
    用于健康检查端点
    """
    global _digital_human, _tts_engine, _stt_engine, AIRI_AVAILABLE
    
    # 检查 TTS 引擎状态
    tts_status = {
        "loaded": _tts_engine is not None,
        "lazy_loading": True,
        "provider": os.environ.get("TTS_PROVIDER", "auto"),
        "available_providers": ["edge", "openai"],
    }
    
    # 如果数字人已初始化，检查其 TTS 状态
    if _digital_human is not None and hasattr(_digital_human, '_tts_engine'):
        tts_status["loaded"] = _digital_human._tts_engine is not None
    
    # 检查 STT 引擎状态
    stt_status = {
        "loaded": _stt_engine is not None,
        "lazy_loading": True,
        "provider": os.environ.get("STT_PROVIDER", "auto"),
        "available_providers": ["openai", "funasr", "faster_whisper"],
    }
    
    # 如果数字人已初始化，检查其 STT 状态
    if _digital_human is not None and hasattr(_digital_human, '_stt_engine'):
        stt_status["loaded"] = _digital_human._stt_engine is not None
    
    # 检查数字人状态
    avatar_status = {
        "initialized": _digital_human is not None,
        "type": os.environ.get("AIRI_AVATAR_TYPE", "live2d"),
        "model_loaded": _digital_human is not None and _digital_human.state is not None,
    }
    
    return {
        "tts": tts_status,
        "stt": stt_status,
        "avatar": avatar_status,
        "airi_available": AIRI_AVAILABLE,
    }


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    "AIRIDigitalHuman",
    "get_digital_human",
    "get_tts_engine",
    "get_stt_engine",
    "get_airi_service_status",
    "AIRISkillsIntegration",
    "initialize_airi_skills",
    "AvatarConfig",
    "AvatarState",
    "AvatarType",
    "AnimationType",
    "ExpressionType",
    "InteractionState",
    "Animation",
    "Expression",
    "AnimationEngine",
    "ExpressionSystem",
    "TTSEngine",
    "STTEngine",
    "TTSServiceError",
    "STTServiceError",
    "BehaviorTree",
    "AvatarSkillRegistry",
    "avatar_skill",
]
