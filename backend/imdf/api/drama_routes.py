"""
F1.6: 短剧一键成片管线 — API Routes
=====================================
POST /api/drama/generate      → 一键生成短剧(返回分镜+预览)
GET  /api/drama/episode/{id}  → 获取已生成的剧集
GET  /api/drama/list           → 剧集列表
POST /api/drama/script         → AI辅助剧本生成
"""

import logging
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# 兼容直接 `python drama_routes.py` 与 canvas_web 加载两种入口
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engines.drama_engine import get_drama_engine  # noqa: E402
from api._common.validators import validate_id  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drama", tags=["drama-studio"])


# ─── Request Models ──────────────────────────────────────────────────────────

class DramaCharacterInput(BaseModel):
    name: str = ""
    description: str = ""
    appearance: str = ""


class DramaGenerateRequest(BaseModel):
    title: str = Field("未命名短剧", description="剧名")
    style: str = Field("modern", description="风格: modern/ancient/scifi/suspense/fantasy/romance/comedy/horror")
    script: str = Field("", description="剧情描述或完整剧本")
    characters: List[DramaCharacterInput] = Field(default_factory=list, description="角色列表")
    episodes: int = Field(1, ge=1, le=50, description="集数")
    duration_per_episode: int = Field(60, ge=10, le=600, description="每集目标时长(s)")
    shot_count: int = Field(14, ge=5, le=200, description="总镜头数")
    shot_duration: float = Field(5.0, ge=2.0, le=30.0, description="每镜头默认时长(s)")
    enable_tts: bool = Field(True, description="是否启用TTS旁白")


class DramaScriptRequest(BaseModel):
    title: str = Field("", description="剧名")
    style: str = Field("modern", description="风格")
    characters: List[DramaCharacterInput] = Field(default_factory=list)
    prompt: str = Field("", description="AI提示词")


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=Dict[str, Any])
async def generate_drama(req: DramaGenerateRequest):
    """
    一键生成完整短剧。

    示例请求:
        POST /api/drama/generate
        {
            "title": "灰烬里的星星",
            "style": "scifi",
            "script": "在一个被灰烬与算法统治的未来...",
            "characters": [
                {"name": "阿星", "description": "拥有情感的机器人", "appearance": "银发少年"}
            ],
            "shot_count": 14,
            "shot_duration": 5.0,
            "enable_tts": true
        }

    返回:
        {
            "success": true,
            "data": {
                "episode_id": "ep_0001",
                "title": "灰烬里的星星",
                "engine": "drama-engine-v2",
                "scenes": 7,
                "duration": 70.0,
                "shots": [ ... ],
                "phases": { ... },
                "quality_score": 85.7,
                "storyboard_preview": "..."
            }
        }
    """
    engine = get_drama_engine()

    try:
        characters_dict = [
            {"name": c.name, "description": c.description, "appearance": c.appearance}
            for c in req.characters
        ]

        result = await engine.generate_episode(
            title=req.title,
            style=req.style,
            script=req.script,
            characters=characters_dict,
            shot_count=req.shot_count,
            shot_duration=req.shot_duration,
            enable_tts=req.enable_tts,
            episodes_count=req.episodes,
            duration_per_episode=req.duration_per_episode,
        )
        return result

    except Exception as e:
        logger.error(f"Drama generation failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "data": None,
        }


@router.get("/episode/{episode_id}", response_model=Dict[str, Any])
async def get_episode(episode_id: str):
    """
    根据episode_id获取完整剧集数据。

    示例:
        GET /api/drama/episode/ep_0001
    """
    # R1-Worker-2: 用共享校验器防止 bad_params (e.g. 'OR 1=1') 触发崩溃。
    validate_id(episode_id, "episode_id")

    engine = get_drama_engine()
    episode = engine.get_episode(episode_id)

    if not episode:
        raise HTTPException(status_code=404, detail=f"剧集 {episode_id} 未找到")

    return {
        "success": True,
        "data": episode,
    }


@router.get("/list", response_model=Dict[str, Any])
async def list_episodes(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """
    获取所有已生成剧集的摘要列表。

    示例:
        GET /api/drama/list
    """
    engine = get_drama_engine()
    episodes = engine.list_episodes()
    if q:
        episodes = [e for e in episodes if q.lower() in str(e).lower()]
    total = len(episodes)
    if sort_by:
        episodes = sorted(
            episodes, key=lambda e: e.get(sort_by, "") if isinstance(e, dict) else "",
            reverse=(order == "desc"),
        )
    page = episodes[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/script", response_model=Dict[str, Any])
async def generate_script(req: DramaScriptRequest):
    """
    AI辅助剧本生成 — 根据标题/风格/角色自动生成剧本概要。

    示例:
        POST /api/drama/script
        {
            "title": "灰烬里的星星",
            "style": "scifi",
            "characters": [{"name": "阿星", "description": "机器人"}],
            "prompt": "请创作..."
        }
    """
    engine = get_drama_engine()

    try:
        # 使用模型网关生成剧本
        try:
            from engines.model_gateway import get_gateway
            gateway = get_gateway()

            chars_desc = ", ".join(
                f"{c.name}({c.description or '待定'})" for c in req.characters
            ) if req.characters else "未指定角色"

            ai_prompt = req.prompt or (
                f"请为一部短剧《{req.title}》创作完整的剧本概要。风格: {req.style}。角色: {chars_desc}。"
                f"请包含: 1)一句话梗概 2)角色详细介绍 3)三幕结构 4)关键场景描述 5)每场建议的镜头数和视觉风格。"
                f"用中文输出。"
            )

            resp = await gateway.chat(
                messages=[{"role": "user", "content": ai_prompt}],
                model="auto",
                temperature=0.8,
                max_tokens=3000,
            )

            if resp.success and resp.content:
                script_text = resp.content.strip()
                return {
                    "success": True,
                    "data": {
                        "script": script_text,
                        "model": resp.model,
                        "provider": resp.provider,
                    },
                }

        except Exception as e:
            logger.warning(f"Model gateway script gen failed: {e}")

        # Fallback: 生成模板剧本
        chars = req.characters if req.characters else [
            DramaCharacterInput(name="主角", description="勇敢"),
            DramaCharacterInput(name="配角", description="友善"),
        ]
        char_lines = "\n".join(
            f"- {c.name}: {c.description or '待定'}{'（' + c.appearance + '）' if c.appearance else ''}"
            for c in chars
        )

        style_names = {
            "modern": "现代都市", "ancient": "古装武侠", "scifi": "科幻未来",
            "suspense": "悬疑推理", "fantasy": "奇幻世界", "romance": "浪漫爱情",
            "comedy": "轻松喜剧", "horror": "惊悚恐怖",
        }
        style_cn = style_names.get(req.style, req.style)

        fallback_script = f"""# {req.title or '未命名短剧'}

## 一句话梗概
在一个{style_cn}的世界里，{chars[0].name}踏上了一段改变命运的旅程。

## 角色
{char_lines}

## 三幕结构
### 第一幕：开场 (25%)
建立世界观和角色关系。{chars[0].name}过着平凡的生活，直到一件意外事件打破了平静。

### 第二幕：冲突发展 (50%)
矛盾升级，{chars[0].name}面临严峻考验。结识盟友，遭遇对手，在两难中成长。

### 第三幕：高潮与结局 (25%)
决战时刻到来，{chars[0].name}做出关键选择。结局意味深长，留下思考空间。

## 关键场景
1. 开场场景 — 展示世界观
2. 激励事件 — 打破常态
3. 中间转折 — 不可回头
4. 低谷场景 — 全盘皆输感
5. 高潮场景 — 正面决战
6. 尾声 — 余韵悠长"""

        return {
            "success": True,
            "data": {
                "script": fallback_script,
                "model": "fallback-template",
                "provider": "local",
            },
        }

    except Exception as e:
        logger.error(f"Script generation failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }
