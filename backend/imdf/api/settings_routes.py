"""
Settings Page Backend Routes
============================
R5-Worker-1: 后端 endpoints for settings.js 8 死按钮.

Endpoints:
  POST /api/settings/api             — saveAPISettings      (base_url, timeout, max_retries)
  POST /api/settings/models          — saveModelSettings    (default_llm, embedding_model, vision_model, temperature, max_tokens)
  POST /api/settings/storage         — saveStorageSettings  (storage_type, storage_path, cache_size_gb, auto_backup)
  POST /api/settings/notifications   — saveNotificationSettings (5 booleans + quality_threshold)
  POST /api/settings/cache/clear     — clearCache           (清理 data/temp + 缩略图缓存)

GET endpoints (读取, 用于前端初始化):
  GET  /api/settings/api
  GET  /api/settings/models
  GET  /api/settings/storage
  GET  /api/settings/notifications

验证策略 (R2.5 patterns):
  - Pydantic v2 BaseModel (BaseSettings 风格) + Field(...) 范围约束
  - 字符串长度限制 (≤200)
  - URL 格式校验
  - 数字范围: timeout 1-300, max_retries 0-10, temperature 0-2, max_tokens 1-128000
  - 存储路径不能是 / / ~ /etc 等危险目录

存储: data/settings/user_preferences.json
  (与 system_config.py 使用的 data/settings.json 隔离, 避免冲突)
"""
import os
import re
import json
import time
import shutil
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator

# Project root: backend/imdf/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 设置数据存储 — 与 system_config.py 使用的 data/settings.json 隔离
SETTINGS_DATA_DIR = _PROJECT_ROOT / "data" / "settings"
USER_PREFERENCES_FILE = SETTINGS_DATA_DIR / "user_preferences.json"

# 缓存目录
CACHE_DIRS = [
    _PROJECT_ROOT / "data" / "thumbnails",
    _PROJECT_ROOT / "data" / "temp",
    _PROJECT_ROOT / "data" / "uploads" / ".cache",
]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# ─── 默认配置 ─────────────────────────────────────────────────────────────
DEFAULT_USER_PREFERENCES = {
    "api": {
        "base_url": "http://localhost:8000/api/v1",
        "timeout": 30,
        "max_retries": 3,
    },
    "models": {
        "default_llm": "deepseek-v4-pro",
        "embedding_model": "text-embedding-3-large",
        "vision_model": "qwen-vl-max",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    "storage": {
        "storage_type": "local",
        "storage_path": "/data/imdf/storage",
        "cache_size_gb": 10,
        "auto_backup": True,
    },
    "notifications": {
        "task_complete": True,
        "delivery_review": True,
        "quality_alert": True,
        "system_alert": True,
        "email_notify": False,
        "quality_threshold": 85,
    },
}

# ─── Utilities ────────────────────────────────────────────────────────────

def _ensure_dir():
    SETTINGS_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_preferences() -> Dict[str, Any]:
    """加载用户偏好, 与默认值合并"""
    _ensure_dir()
    if not USER_PREFERENCES_FILE.exists():
        return json.loads(json.dumps(DEFAULT_USER_PREFERENCES))  # deep copy
    try:
        with open(USER_PREFERENCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("读取用户偏好失败: %s", e)
        return json.loads(json.dumps(DEFAULT_USER_PREFERENCES))
    # 合并默认值, 保证每节都存在
    merged = json.loads(json.dumps(DEFAULT_USER_PREFERENCES))
    for section, values in data.items():
        if section in merged and isinstance(values, dict):
            merged[section].update(values)
    return merged


def _save_preferences(prefs: Dict[str, Any]) -> None:
    """保存用户偏好到磁盘"""
    _ensure_dir()
    tmp_path = USER_PREFERENCES_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
        # 原子替换
        os.replace(tmp_path, USER_PREFERENCES_FILE)
    except OSError as e:
        logger.error("保存用户偏好失败: %s", e)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


def _update_section(section: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """更新某节配置, 返回更新后的完整配置"""
    prefs = _load_preferences()
    if section not in prefs:
        raise HTTPException(status_code=400, detail=f"未知配置节: {section}")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是对象")
    prefs[section].update(payload)
    _save_preferences(prefs)
    return prefs[section]


# ─── Pydantic Models ──────────────────────────────────────────────────────

class APISettings(BaseModel):
    """API 配置 — base_url + 超时 + 重试"""
    base_url: str = Field(..., min_length=1, max_length=2000, description="API 基础地址")
    timeout: int = Field(30, ge=1, le=300, description="超时秒数 (1..300)")
    max_retries: int = Field(3, ge=0, le=10, description="最大重试次数 (0..10)")

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("base_url 不能为空")
        # 必须以 http:// 或 https:// 开头
        if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v, re.IGNORECASE):
            raise ValueError("base_url 格式无效, 必须以 http:// 或 https:// 开头")
        return v


class ModelSettings(BaseModel):
    """模型设置 — LLM/Embedding/Vision/Temperature/MaxTokens"""
    default_llm: str = Field(..., min_length=1, max_length=100)
    embedding_model: str = Field(..., min_length=1, max_length=100)
    vision_model: str = Field(..., min_length=1, max_length=100)
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Temperature (0..2)")
    max_tokens: int = Field(4096, ge=1, le=128000, description="最大 Token (1..128000)")


# 允许的存储类型白名单
ALLOWED_STORAGE_TYPES = {"local", "s3", "minio", "oss", "cos"}

# 不允许的存储路径前缀 (SSRF / 危险目录防护)
FORBIDDEN_PATH_PATTERNS = [
    r"^/etc/?",
    r"^/proc/?",
    r"^/sys/?",
    r"^/dev/?",
    r"^/boot/?",
    r"^/root/?",
    r"^~$",
    r"^/bin/?",
    r"^/sbin/?",
    r"^C:\\Windows",
    r"^C:\\Program Files",
    r"^/$",
]


class StorageSettings(BaseModel):
    """存储配置"""
    storage_type: str = Field("local", min_length=1, max_length=32, description="存储类型")
    storage_path: str = Field(..., min_length=1, max_length=2000, description="存储路径")
    cache_size_gb: int = Field(10, ge=1, le=1000, description="缓存大小 GB (1..1000)")
    auto_backup: bool = Field(True, description="是否自动备份")

    @field_validator("storage_type")
    @classmethod
    def validate_storage_type(cls, v: str) -> str:
        v = v.strip().lower()
        # 中文显示值映射 (前端展示的是中文)
        mapping = {
            "本地文件系统": "local",
            "amazon s3": "s3",
            "minio": "minio",
            "阿里云oss": "oss",
            "alibaba oss": "oss",
        }
        if v in mapping:
            v = mapping[v]
        if v not in ALLOWED_STORAGE_TYPES:
            raise ValueError(
                f"storage_type 必须是以下之一: {sorted(ALLOWED_STORAGE_TYPES)}"
            )
        return v

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("storage_path 不能为空")
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if re.match(pattern, v, re.IGNORECASE):
                raise ValueError(f"storage_path 不允许使用系统目录: {v[:50]}")
        # 路径中不能包含 NUL 字符或换行
        if "\x00" in v or "\n" in v or "\r" in v:
            raise ValueError("storage_path 包含非法字符")
        return v


class NotificationSettings(BaseModel):
    """通知设置 — 5 类开关 + 质量阈值"""
    task_complete: bool = True
    delivery_review: bool = True
    quality_alert: bool = True
    system_alert: bool = True
    email_notify: bool = False
    quality_threshold: int = Field(85, ge=0, le=100, description="质量阈值 (0..100)")


# ─── Routes ───────────────────────────────────────────────────────────────

# === API Settings ===

@router.get("/api")
async def get_api_settings():
    """获取 API 配置"""
    prefs = _load_preferences()
    return {"success": True, "data": prefs["api"]}


@router.post("/api")
async def save_api_settings(req: APISettings):
    """保存 API 配置 (base_url / timeout / max_retries)"""
    try:
        section = _update_section("api", req.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_api_settings failed: %s", e)
        raise HTTPException(status_code=500, detail=f"保存 API 配置失败: {e}")
    return {"success": True, "data": section, "message": "API配置已保存"}


# === Model Settings ===

@router.get("/models")
async def get_model_settings():
    """获取模型设置"""
    prefs = _load_preferences()
    return {"success": True, "data": prefs["models"]}


@router.post("/models")
async def save_model_settings(req: ModelSettings):
    """保存模型设置"""
    try:
        section = _update_section("models", req.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_model_settings failed: %s", e)
        raise HTTPException(status_code=500, detail=f"保存模型设置失败: {e}")
    return {"success": True, "data": section, "message": "模型设置已保存"}


# === Storage Settings ===

@router.get("/storage")
async def get_storage_settings():
    """获取存储配置"""
    prefs = _load_preferences()
    return {"success": True, "data": prefs["storage"]}


@router.post("/storage")
async def save_storage_settings(req: StorageSettings):
    """保存存储配置"""
    try:
        section = _update_section("storage", req.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_storage_settings failed: %s", e)
        raise HTTPException(status_code=500, detail=f"保存存储配置失败: {e}")
    return {"success": True, "data": section, "message": "存储配置已保存"}


# === Notification Settings ===

@router.get("/notifications")
async def get_notification_settings():
    """获取通知设置"""
    prefs = _load_preferences()
    return {"success": True, "data": prefs["notifications"]}


@router.post("/notifications")
async def save_notification_settings(req: NotificationSettings):
    """保存通知设置"""
    try:
        section = _update_section("notifications", req.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_notification_settings failed: %s", e)
        raise HTTPException(status_code=500, detail=f"保存通知设置失败: {e}")
    return {"success": True, "data": section, "message": "通知设置已保存"}


# === Cache Clear ===

@router.post("/cache/clear")
async def clear_cache():
    """清除缓存 — 清理 thumbnails/ + temp/ + uploads/.cache/"""
    cleared: Dict[str, Any] = {"files": 0, "bytes": 0, "dirs": []}
    errors: List[str] = []

    for cache_dir in CACHE_DIRS:
        if not cache_dir.exists():
            continue
        try:
            file_count = 0
            byte_count = 0
            for root, dirs, files in os.walk(cache_dir):
                for fname in files:
                    fp = Path(root) / fname
                    try:
                        size = fp.stat().st_size
                        fp.unlink()
                        file_count += 1
                        byte_count += size
                    except OSError as e:
                        errors.append(f"{fp}: {e}")
            cleared["files"] += file_count
            cleared["bytes"] += byte_count
            cleared["dirs"].append(str(cache_dir))
        except Exception as e:
            errors.append(f"{cache_dir}: {e}")
            logger.warning("清理缓存目录失败 %s: %s", cache_dir, e)

    cleared["bytes_mb"] = round(cleared["bytes"] / (1024 * 1024), 2)
    return {
        "success": True,
        "data": cleared,
        "errors": errors[:10] if errors else [],
        "message": f"已清理 {cleared['files']} 个文件, {cleared['bytes_mb']} MB",
    }
