"""智影 V5 — ProjectCard (需求卡片)

迁移自 Pavo 平台:
- 一句话需求 → 需求卡片 (标题/梗概/时长/画幅/拆分镜模式/视觉风格/补充说明)
- 让人确认后再继续
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProjectType(str, Enum):
    """项目类型 — Pavo + 剧大虾合并"""
    SHORT_DRAMA = "short_drama"        # 短剧
    AD = "ad"                          # 广告
    TUTORIAL = "tutorial"              # 教程
    MUSIC_VIDEO = "music_video"        # MV
    DOCUMENTARY = "documentary"        # 纪录片
    VLOG = "vlog"                      # 视频博客
    ANIMATION = "animation"            # 动画
    PRODUCT_DEMO = "product_demo"      # 产品演示
    CINEMATIC = "cinematic"            # 电影感短片
    COMEDY = "comedy"                  # 搞笑
    EMOTIONAL = "emotional"            # 情感
    TWIST = "twist"                    # 反转故事
    SPREAD = "spread"                  # 传播表达


class CardSection(str, Enum):
    """卡片段落"""
    TITLE = "title"                 # 标题
    SYNOPSIS = "synopsis"           # 梗概
    DURATION = "duration"           # 时长
    ASPECT_RATIO = "aspect_ratio"   # 画幅
    STORYBOARD_MODE = "storyboard_mode"  # 拆分镜模式
    VISUAL_STYLE = "visual_style"   # 视觉风格
    SUPPLEMENTARY = "supplementary"  # 补充说明


@dataclass
class ProjectCard:
    """需求卡片 — Pavo 风格的标准化需求卡"""

    title: str
    project_type: ProjectType = ProjectType.SHORT_DRAMA
    card_id: str = field(default_factory=lambda: f"pc-{uuid.uuid4().hex[:10]}")

    # 内容
    user_prompt: str = ""  # 用户原始输入
    synopsis: str = ""     # 1-2 句梗概
    duration_sec: int = 30  # 时长 (秒)
    aspect_ratio: str = "9:16"  # 9:16 / 16:9 / 1:1 / 4:3
    storyboard_mode: str = "auto"  # auto / 5_shot / 8_shot / detailed
    visual_style: str = ""  # "真人写实" / "日本动漫" / "3D CG" / "玄幻厚涂"
    supplementary: str = ""  # 补充说明

    # 风格子选项
    style_tags: List[str] = field(default_factory=list)  # ["暖色", "电影感", "武侠"]
    language: str = "zh-CN"
    target_audience: str = ""  # "年轻女性" / "科技爱好者"
    mood: str = ""  # "治愈" / "紧张" / "搞笑"

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    confirmed: bool = False  # 确认门
    confirmed_by: str = ""
    confirmed_at: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def confirm(self, by: str = ""):
        """用户确认"""
        self.confirmed = True
        self.confirmed_by = by
        self.confirmed_at = time.time()
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "title": self.title,
            "project_type": self.project_type.value,
            "user_prompt": self.user_prompt,
            "synopsis": self.synopsis,
            "duration_sec": self.duration_sec,
            "aspect_ratio": self.aspect_ratio,
            "storyboard_mode": self.storyboard_mode,
            "visual_style": self.visual_style,
            "supplementary": self.supplementary,
            "style_tags": self.style_tags,
            "language": self.language,
            "target_audience": self.target_audience,
            "mood": self.mood,
            "confirmed": self.confirmed,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def render_markdown(self) -> str:
        """渲染为 markdown"""
        lines = [
            f"# {self.title}",
            "",
            f"> {self.project_type.value} | {self.duration_sec}s | {self.aspect_ratio}",
            "",
            f"## 梗概",
            self.synopsis or "(待补充)",
            "",
            f"## 视觉风格",
            self.visual_style or "(待选)",
            "",
            f"## 拆分镜模式",
            self.storyboard_mode,
            "",
            f"## 补充说明",
            self.supplementary or "(无)",
            "",
            f"## 用户原始输入",
            f"> {self.user_prompt}",
            "",
        ]
        return "\n".join(lines)


def auto_generate_card(user_prompt: str) -> ProjectCard:
    """从用户一句话自动生成 ProjectCard (启发式)"""
    card = ProjectCard(
        title=user_prompt[:60],
        user_prompt=user_prompt,
        created_at=time.time(),
        updated_at=time.time(),
    )
    prompt_lower = user_prompt.lower()

    # 类型推断
    if any(kw in user_prompt for kw in ["广告", "ad", "宣传", "营销"]):
        card.project_type = ProjectType.AD
    elif any(kw in user_prompt for kw in ["教程", "教学", "tutorial"]):
        card.project_type = ProjectType.TUTORIAL
    elif any(kw in user_prompt for kw in ["动画", "anime", "cartoon", "动漫"]):
        card.project_type = ProjectType.ANIMATION
    elif any(kw in user_prompt for kw in ["记录", "documentary"]):
        card.project_type = ProjectType.DOCUMENTARY
    elif any(kw in user_prompt for kw in ["vlog", "日常", "日志"]):
        card.project_type = ProjectType.VLOG
    elif any(kw in user_prompt for kw in ["产品", "product", "展示"]):
        card.project_type = ProjectType.PRODUCT_DEMO
    elif any(kw in user_prompt for kw in ["搞笑", "comedy", "段子", "梗"]):
        card.project_type = ProjectType.COMEDY
    elif any(kw in user_prompt for kw in ["感情", "情感", "治愈", "温暖"]):
        card.project_type = ProjectType.EMOTIONAL
    elif any(kw in user_prompt for kw in ["反转", "twist", "神转折"]):
        card.project_type = ProjectType.TWIST
    else:
        card.project_type = ProjectType.SHORT_DRAMA

    # 画幅
    if "横屏" in user_prompt or "16:9" in user_prompt or "电脑" in user_prompt:
        card.aspect_ratio = "16:9"
    elif "方" in user_prompt or "1:1" in user_prompt:
        card.aspect_ratio = "1:1"
    else:
        card.aspect_ratio = "9:16"  # 默认竖屏

    # 时长
    import re
    m = re.search(r"(\d+)\s*秒", user_prompt)
    if m:
        card.duration_sec = int(m.group(1))
    else:
        m = re.search(r"(\d+)s\b", prompt_lower)
        if m:
            card.duration_sec = int(m.group(1))
        else:
            card.duration_sec = 30 if card.project_type in (ProjectType.AD,) else 60

    # 视觉风格 — 剧大虾 10 风格
    style_keywords = {
        "真人写实": ["真人", "写实", "realistic", "real"],
        "真人女频甜宠": ["女频", "甜宠", "言情"],
        "日本动漫": ["动漫", "anime", "卡通", "二次元"],
        "3D CG": ["3D", "CG", "三维"],
        "玄幻厚涂": ["玄幻", "厚涂", "仙侠", "古风"],
        "水墨": ["水墨", "国画", "古风"],
        "赛博朋克": ["赛博", "cyber", "霓虹", "未来"],
        "蒸汽朋克": ["蒸汽", "steampunk"],
        "暗黑": ["暗黑", "黑暗", "恐怖"],
        "治愈": ["治愈", "暖色", "温柔"],
    }
    for style, kws in style_keywords.items():
        if any(kw in user_prompt or kw in prompt_lower for kw in kws):
            card.visual_style = style
            card.style_tags.append(style)
            break
    if not card.visual_style:
        card.visual_style = "真人写实"
        card.style_tags.append("真人写实")

    # 风格标签
    for tag in ["暖色", "电影感", "武侠", "都市", "校园", "职场", "科幻", "魔幻", "末世", "重生", "穿越", "甜宠", "悬疑", "搞笑", "热血", "冒险", "校园", "霸道", "宫廷"]:
        if tag in user_prompt:
            card.style_tags.append(tag)

    # 情绪
    if "紧张" in user_prompt or "刺激" in user_prompt:
        card.mood = "紧张"
    elif "搞笑" in user_prompt or "幽默" in user_prompt:
        card.mood = "搞笑"
    elif "感动" in user_prompt or "治愈" in user_prompt:
        card.mood = "治愈"
    elif "神秘" in user_prompt:
        card.mood = "神秘"

    # 梗概 — 简单提取
    if "。" in user_prompt:
        card.synopsis = user_prompt.split("。")[0] + "。"
    else:
        card.synopsis = user_prompt

    # 拆分镜模式
    if card.duration_sec <= 15:
        card.storyboard_mode = "3_shot"
    elif card.duration_sec <= 30:
        card.storyboard_mode = "5_shot"
    elif card.duration_sec <= 60:
        card.storyboard_mode = "8_shot"
    else:
        card.storyboard_mode = "detailed"

    return card
