"""
External AI Provider Router — 复刻 Penguin Canvas routes/externalProviders.js
================================================================================
测试 Provider 连接 / LLM / 图像 / 视频 生成调用
"""
import os
import re
import json
import hashlib
import time
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.global_config import OUTPUT_DIR, MIME_BY_EXT, PORT, SETTINGS_FILE
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imdf/provider", tags=["external_providers"])

# ─── 常量 ───────────────────────────────────────────────────────────────────
GENERATION_TIMEOUT = 60 * 60 * 1000  # 1 hour
SUPPORTED_KINDS = ("llm", "image", "video")


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderRequest(BaseModel):
    provider_id: Optional[str] = None
    provider: Optional[Dict] = None
    dry_run: bool = False
    timeout_ms: Optional[int] = None


class GenerateRequest(BaseModel):
    provider_id: Optional[str] = None
    provider: Optional[Dict] = None
    timeout_ms: Optional[int] = None
    # 额外字段透传给 adapter


# ═══════════════════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════════════════

def _load_settings() -> Dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return {}


def _sanitize_text(value, fallback="", maxlen=200) -> str:
    return str(value or fallback).strip()[:maxlen]


def _output_ext(mime: str, fallback=".png") -> str:
    m = mime.lower()
    if "mp4" in m:
        return ".mp4"
    if "webm" in m:
        return ".webm"
    if "quicktime" in m or "mov" in m:
        return ".mov"
    if "jpeg" in m or "jpg" in m:
        return ".jpg"
    if "webp" in m:
        return ".webp"
    if "gif" in m:
        return ".gif"
    if "bmp" in m:
        return ".bmp"
    if "png" in m:
        return ".png"
    if "mp3" in m or "mpeg" in m:
        return ".mp3"
    if "wav" in m:
        return ".wav"
    if "ogg" in m:
        return ".ogg"
    return fallback


def _output_ext_from_url(url: str, fallback=".png") -> str:
    try:
        parsed = __import__("urllib.parse").urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
                    ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".ogg"):
            return ext
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return fallback


def _default_ext(kind: str) -> str:
    return ".mp4" if kind == "video" else (".mp3" if kind == "audio" else ".png")


def _write_media(buffer: bytes, ext: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    fname = f"ext_{int(time.time()*1000)}_{suffix}{ext}"
    with open(os.path.join(OUTPUT_DIR, fname), "wb") as f:
        f.write(buffer)
    return f"/imdf/media/output/{fname}"


def _generation_timeout(value) -> int:
    try:
        n = int(value)
        return max(GENERATION_TIMEOUT, n) if n > 0 else GENERATION_TIMEOUT
    except (TypeError, ValueError):
        return GENERATION_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════════════
# 媒体输出保存
# ═══════════════════════════════════════════════════════════════════════════════

async def _save_one_output(url: str, kind: str = "image") -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    # data: URI
    dm = re.match(r"^data:([^;]+);base64,(.+)$", text, re.I)
    if dm:
        mime = dm.group(1)
        ext = _output_ext(mime, _default_ext(kind))
        buf = __import__("base64").b64decode(dm.group(2))
        return _write_media(buf, ext)
    # http URL
    if re.match(r"^https?://", text, re.I):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(text, follow_redirects=True)
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "")
            ext = _output_ext(mime, _output_ext_from_url(text, _default_ext(kind)))
            return _write_media(resp.content, ext)
    # 本地路径
    if text.startswith("/imdf/media/output/"):
        return text
    return text


async def _save_outputs(urls: List[str], kind: str = "image") -> List[str]:
    results = []
    for url in urls:
        saved = await _save_one_output(url, kind)
        if saved:
            results.append(saved)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/test")
async def test_provider(req: TestProviderRequest):
    """测试 provider 连接"""
    settings = _load_settings()
    providers = settings.get("providerExtensions", [])
    provider = _resolve_provider(req, providers)
    if not provider:
        raise HTTPException(status_code=404, detail="未找到扩展平台配置")
    result = await _do_test_connection(provider, req.dry_run, req.timeout_ms)
    return {"success": result.get("ok", False), "data": result}


@router.post("/llm")
async def call_llm(payload: Dict):
    """调用 LLM 生成"""
    settings = _load_settings()
    providers = settings.get("providerExtensions", [])
    provider = _resolve_runnable(payload, providers)
    if not provider["ok"]:
        raise HTTPException(status_code=400, detail=provider["error"])
    result = await _do_llm_call(provider["provider"], payload)
    return {"success": result.get("ok", False), "data": result}


@router.post("/image")
async def call_image(payload: Dict):
    """调用图像生成"""
    settings = _load_settings()
    providers = settings.get("providerExtensions", [])
    provider = _resolve_runnable(payload, providers)
    if not provider["ok"]:
        raise HTTPException(status_code=400, detail=provider["error"])
    timeout = _generation_timeout(payload.get("timeout_ms"))
    result = await _do_image_gen(provider["provider"], payload, timeout)
    if not result.get("ok"):
        return {"success": False, "data": result}
    remote_urls = result.get("imageUrls", []) or []
    local_urls = await _save_outputs(remote_urls, "image")
    return {"success": True, "data": {**result, "remoteImageUrls": remote_urls, "imageUrls": local_urls}}


@router.post("/video")
async def call_video(payload: Dict):
    """调用视频生成"""
    settings = _load_settings()
    providers = settings.get("providerExtensions", [])
    provider = _resolve_runnable(payload, providers)
    if not provider["ok"]:
        raise HTTPException(status_code=400, detail=provider["error"])
    timeout = _generation_timeout(payload.get("timeout_ms"))
    result = await _do_video_gen(provider["provider"], payload, timeout)
    if not result.get("ok"):
        return {"success": False, "data": result}
    remote_urls = result.get("videoUrls", []) or []
    local_urls = await _save_outputs(remote_urls, "video")
    return {"success": True, "data": {**result, "remoteVideoUrls": remote_urls, "videoUrls": local_urls}}


# ═══════════════════════════════════════════════════════════════════════════════
# Provider 解析
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_provider(req: TestProviderRequest, providers: List[Dict]) -> Optional[Dict]:
    if req.provider and isinstance(req.provider, dict):
        return _normalize_single(req.provider, providers)
    pid = _sanitize_text(req.provider_id)
    if pid:
        return next((p for p in providers if p.get("id") == pid), None)
    return providers[0] if providers else None


def _resolve_runnable(payload: Dict, providers: List[Dict]) -> Dict:
    pid = _sanitize_text(payload.get("provider_id"))
    raw_prov = payload.get("provider")
    provider = None
    if raw_prov and isinstance(raw_prov, dict):
        provider = _normalize_single(raw_prov, providers)
    elif pid:
        provider = next((p for p in providers if p.get("id") == pid), None)
    if not provider:
        return {"ok": False, "error": "未找到扩展平台配置"}
    if not provider.get("enabled"):
        return {"ok": False, "error": "扩展平台未启用", "provider": provider}
    return {"ok": True, "provider": provider}


def _normalize_single(raw: Dict, current: List[Dict]) -> Dict:
    """简化 provider 规范化"""
    protocol = str(raw.get("protocol", "")).strip().lower()
    return {
        "id": str(raw.get("id", "custom")).strip(),
        "label": str(raw.get("label", raw.get("id", "custom"))).strip()[:60],
        "protocol": protocol,
        "baseUrl": str(raw.get("baseUrl", "")).strip().rstrip("/"),
        "enabled": bool(raw.get("enabled", False)),
        "apiKey": str(raw.get("apiKey", "")).strip()[:4096],
        "imageModels": raw.get("imageModels") or [],
        "videoModels": raw.get("videoModels") or [],
        "chatModels": raw.get("chatModels") or [],
        "defaults": raw.get("defaults") or {},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Adapters (简化版 — 实际路由到子模块)
# ═══════════════════════════════════════════════════════════════════════════════

async def _do_test_connection(provider: Dict, dry_run: bool, timeout_ms: Optional[int]) -> Dict:
    """测试连接 — 发送一个简单请求到 baseUrl"""
    base = provider.get("baseUrl", "")
    if not base:
        return {"ok": False, "code": "missing_base_url", "error": "Base URL 为空"}
    try:
        async with httpx.AsyncClient(timeout=(timeout_ms or 8000) / 1000) as client:
            resp = await client.get(base + "/models", headers={"Authorization": f"Bearer {provider.get('apiKey', '')}"})
            if resp.status_code < 500:
                return {"ok": True, "code": "connected", "status": resp.status_code}
            return {"ok": False, "code": "http_error", "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "code": "connection_failed", "error": str(e)}


async def _do_llm_call(provider: Dict, payload: Dict) -> Dict:
    """LLM 调用 — 转发到 OpenAI 兼容接口"""
    base = provider.get("baseUrl", "")
    api_key = provider.get("apiKey", "")
    if not base:
        return {"ok": False, "code": "missing_base_url", "error": "Base URL 为空"}
    messages = payload.get("messages", [])
    model = payload.get("model", (provider.get("chatModels") or [None])[0] or "gpt-4o")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                json={"model": model, "messages": messages},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            data = resp.json()
            if resp.status_code < 400:
                return {"ok": True, "text": data.get("choices", [{}])[0].get("message", {}).get("content", "")}
            return {"ok": False, "code": "api_error", "error": str(data)}
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)}


async def _do_image_gen(provider: Dict, payload: Dict, timeout: int) -> Dict:
    """图像生成 — OpenAI 兼容 images/generations"""
    base = provider.get("baseUrl", "")
    api_key = provider.get("apiKey", "")
    model = payload.get("model", (provider.get("imageModels") or [None])[0] or "dall-e-3")
    prompt = payload.get("prompt", "")
    try:
        async with httpx.AsyncClient(timeout=timeout / 1000) as client:
            resp = await client.post(
                f"{base}/images/generations",
                json={"model": model, "prompt": prompt, "n": payload.get("n", 1)},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            data = resp.json()
            if resp.status_code < 400:
                urls = [item.get("url") or item.get("b64_json") or "" for item in data.get("data", [])]
                return {"ok": True, "imageUrls": [u for u in urls if u]}
            return {"ok": False, "code": "api_error", "error": str(data)}
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)}


async def _do_video_gen(provider: Dict, payload: Dict, timeout: int) -> Dict:
    """视频生成 — 简化为 images/generations (实际应调用视频端点)"""
    return await _do_image_gen(provider, payload, timeout)
