"""智影 V5 — UserProfile / Agent Profile (Hermes setup --portal 模型)"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """用户画像 — Hermes profile.md / style.md 兼容"""

    user_id: str
    profile_id: str = field(default_factory=lambda: f"up-{uuid.uuid4().hex[:10]}")
    # 基础
    username: str = ""
    display_name: str = ""
    email: str = ""
    avatar: str = ""

    # 身份
    identity: str = "我是一名工程师"  # 我是谁
    role: str = ""  # 当前角色
    industry: str = ""  # 行业

    # 偏好
    preferences: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)  # 禁忌

    # 风格
    tone: str = "professional"           # 语气
    length: str = "concise"               # 长度
    format: str = "structured"            # 格式
    language: str = "zh-CN"               # 语言
    use_emoji: bool = False

    # 工具
    favorite_tools: List[str] = field(default_factory=list)
    favorite_models: List[str] = field(default_factory=list)

    # 隐私
    data_retention_days: int = 365
    allow_external_sharing: bool = False

    # API keys (引用)
    api_keys: Dict[str, str] = field(default_factory=dict)  # {"openai": "sk-..."}

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "identity": self.identity,
            "role": self.role,
            "industry": self.industry,
            "preferences": self.preferences,
            "constraints": self.constraints,
            "forbidden": self.forbidden,
            "tone": self.tone,
            "length": self.length,
            "format": self.format,
            "language": self.language,
            "use_emoji": self.use_emoji,
            "favorite_tools": self.favorite_tools,
            "favorite_models": self.favorite_models,
            "data_retention_days": self.data_retention_days,
            "allow_external_sharing": self.allow_external_sharing,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def render_profile_md(self) -> str:
        """渲染为 profile.md"""
        lines = [
            f"# profile.md — {self.display_name or self.username or self.user_id}",
            "",
            f"> 自动生成: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.updated_at))}",
            "",
            f"## 我是谁",
            self.identity,
            "",
            f"**当前角色**: {self.role or '(未指定)'}",
            f"**行业**: {self.industry or '(未指定)'}",
            "",
            "## 偏好",
        ]
        for p in self.preferences:
            lines.append(f"- {p}")
        lines.extend(["", "## 约束"])
        for c in self.constraints:
            lines.append(f"- {c}")
        if self.forbidden:
            lines.extend(["", "## 禁忌"])
            for f in self.forbidden:
                lines.append(f"- {f}")
        lines.extend(
            [
                "",
                "## 风格",
                f"- **语气**: {self.tone}",
                f"- **长度**: {self.length}",
                f"- **格式**: {self.format}",
                f"- **语言**: {self.language}",
                f"- **Emoji**: {'是' if self.use_emoji else '否'}",
                "",
            ]
        )
        return "\n".join(lines)

    def render_style_md(self) -> str:
        """渲染为 style.md"""
        lines = [
            f"# style.md",
            "",
            f"> 自动生成: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.updated_at))}",
            "",
            f"- **tone**: {self.tone}",
            f"- **length**: {self.length}",
            f"- **format**: {self.format}",
            f"- **language**: {self.language}",
            f"- **use_emoji**: {self.use_emoji}",
            "",
            "## 风格示例",
            "",
            "### 输入",
            "> 请帮我写一份用户调研报告",
            "",
            "### 输出",
            f"按 {self.format} 格式, {self.length} 长度, {self.tone} 语气, 用 {self.language} 回答:",
            "",
            "...",
            "",
        ]
        return "\n".join(lines)


class ProfileManager:
    """Profile 管理 — Hermes setup --portal 模型"""

    def __init__(self):
        self.profiles: Dict[str, UserProfile] = {}

    def create(
        self,
        user_id: str,
        username: str = "",
        display_name: str = "",
        email: str = "",
        identity: str = "我是一名工程师",
        role: str = "",
        industry: str = "",
        tone: str = "professional",
        length: str = "concise",
        format: str = "structured",
        language: str = "zh-CN",
    ) -> UserProfile:
        p = UserProfile(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            email=email,
            identity=identity,
            role=role,
            industry=industry,
            tone=tone,
            length=length,
            format=format,
            language=language,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.profiles[user_id] = p
        return p

    def get(self, user_id: str) -> Optional[UserProfile]:
        return self.profiles.get(user_id)

    def update(self, user_id: str, **kwargs) -> Optional[UserProfile]:
        p = self.profiles.get(user_id)
        if not p:
            return None
        for k, v in kwargs.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.updated_at = time.time()
        return p

    def add_preference(self, user_id: str, pref: str) -> bool:
        p = self.profiles.get(user_id)
        if not p:
            return False
        if pref not in p.preferences:
            p.preferences.append(pref)
            p.updated_at = time.time()
        return True

    def add_constraint(self, user_id: str, constraint: str) -> bool:
        p = self.profiles.get(user_id)
        if not p:
            return False
        if constraint not in p.constraints:
            p.constraints.append(constraint)
            p.updated_at = time.time()
        return True

    def set_api_key(self, user_id: str, provider: str, key: str) -> bool:
        p = self.profiles.get(user_id)
        if not p:
            return False
        p.api_keys[provider] = key
        p.updated_at = time.time()
        return True

    def list(self) -> List[UserProfile]:
        return list(self.profiles.values())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_profiles": len(self.profiles),
            "by_language": {},
            "avg_preferences": sum(len(p.preferences) for p in self.profiles.values()) / max(len(self.profiles), 1),
        }


profile_manager = ProfileManager()
