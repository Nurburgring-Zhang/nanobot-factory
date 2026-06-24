#!/usr/bin/env python3
"""
AIRI Digital Human API Router — 注册到 canvas_web (port 8900) 的 FastAPI 子路由
==========================================================================

提供 2 个端点(原仅在 server_nanobot.py:8898 注册, IMDF 主应用未挂载):

  GET  /digital-human/models   — 可用模型清单 (airi_v3 / wav2lip_hd / sadtalker / muse_talk / live_portrait)
  POST /digital-human/generate — 提交数字人生成任务, 返回 job_id + eta_seconds

实现策略:
- 优先调用 backend/airi_digital_human.py 中的 AIRIDigitalHuman 类(若 backend 在 sys.path 上)
- 失败时回落到与 server_nanobot.py 完全一致的 stub 响应, 保持 8900 ↔ 8898 行为对等

修复:
  R0-Worker-2, 2026-06-18 — 把 server_nanobot.py 数字人端点挂到 IMDF 主入口, 解决 404
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("airi_digital_human")

# ─── 让 backend/airi_digital_human.py 可被发现 ──────────────────────────────
# 路径解析: backend/imdf/engines/airi_digital_human.py
#   .parent       = backend/imdf/engines/
#   .parent.parent = backend/imdf/
#   .parent.parent.parent = backend/        ← 我们要的就是这个
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if _BACKEND_DIR.is_dir() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ─── 可选: 接入 AIRI 数字人主类(避免循环依赖 / 启动失败) ────────────────────
AIRI_AVAILABLE = False
_get_digital_human = None  # type: ignore[assignment]
_get_airi_service_status = None  # type: ignore[assignment]
try:
    import airi_digital_human as _airi_mod  # type: ignore[import-not-found]

    AIRI_AVAILABLE = getattr(_airi_mod, "AIRI_AVAILABLE", True)
    _get_digital_human = getattr(_airi_mod, "get_digital_human", None)
    _get_airi_service_status = getattr(_airi_mod, "get_airi_service_status", None)
    logger.info("airi_digital_human.py 已链接 AIRI 核心模块 (AIRI_AVAILABLE=%s)", AIRI_AVAILABLE)
except Exception as _exc:  # noqa: BLE001
    logger.warning("无法 import backend/airi_digital_human: %s — 回落 stub 响应", _exc)

# ─── 模型注册表(与 server_nanobot.py 保持一致) ─────────────────────────────
_DEFAULT_MODELS: List[Dict[str, Any]] = [
    {"id": "airi_v3",       "name": "AIRI v3",          "type": "live2d",  "description": "Nanobot 主推, 表情/唇形/手势联动"},
    {"id": "wav2lip_hd",    "name": "Wav2Lip HD",       "type": "audio2vid","description": "高保真唇形同步, 适合口播场景"},
    {"id": "sadtalker",     "name": "SadTalker",        "type": "audio2vid","description": "音频驱动面部表情, 适合情感交互"},
    {"id": "muse_talk",     "name": "MuseTalk",         "type": "audio2vid","description": "实时低延迟, 适合直播/客服"},
    {"id": "live_portrait", "name": "LivePortrait",     "type": "motion",   "description": "动作迁移, 把参考动作叠加到目标人像"},
]

_ETA_BY_MODEL: Dict[str, int] = {
    "airi_v3":       120,
    "wav2lip_hd":     60,
    "sadtalker":      90,
    "muse_talk":      45,
    "live_portrait":  75,
}

_VALID_MODEL_IDS = {m["id"] for m in _DEFAULT_MODELS}


# ─── Pydantic 请求体 ────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    """POST /digital-human/generate 请求体

    字段全部可选, 缺省即按默认模型 + 空 prompt 提交, 保持与 server_nanobot.py 的 stub 行为一致。
    """
    model: Optional[str] = Field(None, description="模型 id, 默认 airi_v3")
    prompt: Optional[str] = Field(None, description="生成提示词/口播文本")
    audio_url: Optional[str] = Field(None, description="驱动音频 URL")
    image_url: Optional[str] = Field(None, description="目标人像 URL")
    duration: Optional[float] = Field(None, ge=0.0, le=600.0, description="视频时长上限(秒)")
    extra: Optional[Dict[str, Any]] = Field(None, description="透传参数")


# ─── Router ────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/digital-human", tags=["digital-human"])


def _ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def _fail(error: str, status_code: int = 200) -> Dict[str, Any]:
    """统一错误响应 — 业务错误走 200+success:false(与 server_nanobot.py 一致),
    真正的 4xx 由 raise HTTPException 抛出。
    """
    return {"success": False, "error": str(error), "data": None}


@router.get("/models")
async def list_digital_human_models() -> Dict[str, Any]:
    """列出可用数字人模型。

    实现:
      1. 优先返回 AIRI 主类的状态(若已初始化)
      2. 回落 _DEFAULT_MODELS
    始终返回 200 + success:true。
    """
    try:
        models: List[Dict[str, Any]] = list(_DEFAULT_MODELS)

        # 尝试从 AIRI 主类拿运行期状态, 增强返回
        if AIRI_AVAILABLE and _get_airi_service_status is not None:
            try:
                status = _get_airi_service_status()  # type: ignore[misc]
                if isinstance(status, dict):
                    return _ok({
                        "models": models,
                        "count": len(models),
                        "airi_available": AIRI_AVAILABLE,
                        "service_status": status,
                        "default_model": os.environ.get("AIRI_DEFAULT_MODEL", "airi_v3"),
                    })
            except Exception as _exc:  # noqa: BLE001
                logger.warning("get_airi_service_status 失败: %s — 回落默认列表", _exc)

        return _ok({
            "models": models,
            "count": len(models),
            "airi_available": AIRI_AVAILABLE,
            "default_model": os.environ.get("AIRI_DEFAULT_MODEL", "airi_v3"),
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_digital_human_models 异常: %s", exc)
        return _fail(str(exc))


@router.post("/generate")
async def generate_digital_human(request: GenerateRequest) -> Dict[str, Any]:
    """提交数字人生成任务。

    实现:
      1. 校验 model id(未知 → 400)
      2. 调用 AIRI 主类(enqueue_run / submit 之类)若可用, 否则回落到 stub job_id
      3. 始终返回 200 + success:true (任务成功提交)/ 400 (参数错误)
    """
    try:
        # 1. model 校验
        model_id = request.model or os.environ.get("AIRI_DEFAULT_MODEL", "airi_v3")
        if model_id not in _VALID_MODEL_IDS:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": f"未知模型 id: {model_id!r}, 合法值: {sorted(_VALID_MODEL_IDS)}",
                },
            )

        # 2. 尝试调用 AIRI 主类
        job_id: Optional[str] = None
        if AIRI_AVAILABLE and _get_digital_human is not None:
            try:
                dh = _get_digital_human()  # type: ignore[misc]
                # 数字人主类提供 enqueue / submit 之类的方法则调用; 否则 fallback
                submit = getattr(dh, "submit_generate_job", None) or getattr(dh, "enqueue", None)
                if callable(submit):
                    job_id = submit(  # type: ignore[call-arg]
                        model=model_id,
                        prompt=request.prompt,
                        audio_url=request.audio_url,
                        image_url=request.image_url,
                        duration=request.duration,
                        extra=request.extra,
                    )
            except Exception as _exc:  # noqa: BLE001
                logger.warning("AIRI submit_generate_job 失败: %s — 回落 stub job_id", _exc)

        # 3. 回落 stub job_id(与 server_nanobot.py 行为一致)
        if not job_id:
            payload = f"{model_id}|{request.prompt}|{request.audio_url}|{request.image_url}|{time.time()}"
            job_id = f"dh_{hashlib.md5(payload.encode('utf-8')).hexdigest()[:8]}_{uuid.uuid4().hex[:6]}"

        eta_seconds = _ETA_BY_MODEL.get(model_id, 120)

        return _ok({
            "job_id": job_id,
            "model": model_id,
            "eta_seconds": eta_seconds,
            "status": "queued",
            "submitted_at": int(time.time()),
            "airi_available": AIRI_AVAILABLE,
        })
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_digital_human 异常: %s", exc)
        return _fail(str(exc))


# ─── 健康检查端点(可选) ─────────────────────────────────────────────────────
@router.get("/status")
async def digital_human_status() -> Dict[str, Any]:
    """数字人服务状态 — 供前端心跳"""
    try:
        if AIRI_AVAILABLE and _get_airi_service_status is not None:
            try:
                status = _get_airi_service_status()  # type: ignore[misc]
                return _ok({"airi_available": True, "service_status": status})
            except Exception as exc:  # noqa: BLE001
                logger.warning("get_airi_service_status 失败: %s", exc)
        return _ok({"airi_available": False, "service_status": None})
    except Exception as exc:  # noqa: BLE001
        logger.exception("digital_human_status 异常: %s", exc)
        return _fail(str(exc))


__all__ = ["router", "AIRI_AVAILABLE"]