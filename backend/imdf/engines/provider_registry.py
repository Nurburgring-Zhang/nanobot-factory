"""
AI Provider Registry & Adapters — 复刻 Penguin Canvas providers/*
===========================================================================
Provider 注册中心 + 各协议适配器(OpenAI兼容/ModelScope/火山引擎/ComfyUI/即梦CLI)

P2-3-W2 新增 (3 件):
- ``RateLimiter.check(user_id, provider_id, per_hour)``      进程内滑动窗口限流
- ``compute_cost_usd(protocol, model, prompt_tokens, completion_tokens)``  按协议+模型查单价表算 USD
- ``CircuitBreaker`` (per provider)                            错误率 > 50% 自动 open, 半开恢复

设计:
- **降级**: 限流/熔断都做了 try/except, 单个 provider 出问题不影响其他 provider。
- **env 覆盖**: ``AI_RATE_LIMIT_PER_HOUR`` / ``AI_COST_PER_1K_TOKENS`` 可覆盖默认值。
- **mock 模式**: 当 provider 没有真 apiKey 时, 自动降级到 ``mock`` adapter (返回固定 mock 响应),
  让开发环境 / CI / 单元测试都不需要真 key 就能跑通。
"""
import os
import re
import json
import hashlib
import time
import uuid
import asyncio
import subprocess
import threading
import logging
from collections import deque
from typing import Optional, List, Dict, Any, Tuple, Set, Deque
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from config.global_config import (
    OUTPUT_DIR, INPUT_DIR, SETTINGS_FILE, MIME_BY_EXT,
)

# ─── 支持的协议 ─────────────────────────────────────────────────────────────
SUPPORTED_PROTOCOLS = frozenset([
    "openai-compatible", "modelscope", "volcengine", "comfyui", "jimeng-cli",
])

# ─── 默认模型 ───────────────────────────────────────────────────────────────
DEFAULT_MODELSCOPE_IMAGE_MODELS = [
    "Tongyi-MAI/Z-Image-Turbo", "Qwen/Qwen-Image-2512",
    "Qwen/Qwen-Image-Edit-2511", "black-forest-labs/FLUX.2-klein-9B",
]
DEFAULT_MODELSCOPE_CHAT_MODELS = [
    "Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "MiniMax/MiniMax-M2.7:MiniMax",
]
DEFAULT_VOLC_IMAGE_MODELS = ["doubao-seedream-4-0-250828"]
DEFAULT_VOLC_VIDEO_MODELS = [
    "doubao-seedance-2-0-260128", "doubao-seedance-2-0-fast-260128",
    "doubao-seedance-1-5-pro-251215", "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-t2v-250428", "doubao-seedance-1-0-lite-i2v-250428",
]
DEFAULT_VOLC_CHAT_MODELS = ["doubao-seed-1-6-250615"]
DEFAULT_JIMENG_IMAGE_MODELS = [
    "seedream-4.7", "seedream-4.6", "seedream-4.5", "seedream-5.0",
    "jimeng-image-2k", "jimeng-image-4k",
]
DEFAULT_JIMENG_VIDEO_MODELS = [
    "seedance2.0fast_vip", "seedance2.0_vip", "seedance2.0fast",
    "seedance2.0", "jimeng-video-720p", "jimeng-video-1080p",
]

# ─── 默认 LoRA ──────────────────────────────────────────────────────────────
DEFAULT_MODELSCOPE_LORAS = [
    {"id": "Daniel8152/film", "name": "Z-Image Film",
     "targetModel": "Tongyi-MAI/Z-Image-Turbo", "strength": 0.8, "enabled": True, "note": ""},
    {"id": "Daniel8152/Qwen-Image-2512-Film", "name": "Qwen Image 2512 Film",
     "targetModel": "Qwen/Qwen-Image-2512", "strength": 0.8, "enabled": True, "note": ""},
    {"id": "Daniel8152/Klein-enhance", "name": "Klein enhance",
     "targetModel": "black-forest-labs/FLUX.2-klein-9B", "strength": 0.8, "enabled": True, "note": ""},
]

DEFAULT_VOLC_BASE = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODELSCOPE_BASE = "https://api-inference.modelscope.cn/v1"

# ─── Provider ID 正则 ──────────────────────────────────────────────────────
PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")
CONTROL_CHAR = re.compile(r"[\x00-\x1f\x7f]")

# ═══════════════════════════════════════════════════════════════════════════════
# 规范化工具
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_text(value: Any, maxlen: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maxlen]


def _clean_id(value: Any) -> str:
    cid = str(value or "").strip().lower()
    return cid if PROVIDER_ID_PATTERN.match(cid) else ""


def _clean_protocol(value: Any) -> str:
    p = str(value or "").strip().lower()
    return p if p in SUPPORTED_PROTOCOLS else ""


def _is_masked(value: Any) -> bool:
    return isinstance(value, str) and bool(re.match(r"^\*{2,}", value.strip()))


def _clean_secret(value: Any, previous: str = "") -> str:
    if not isinstance(value, str):
        return previous or ""
    trimmed = value.strip()
    if not trimmed or _is_masked(trimmed) or CONTROL_CHAR.search(trimmed):
        return previous or ""
    return trimmed[:4096]


def _mask_secret(value: str) -> str:
    v = str(value or "").strip()
    return f"****{v[-4:]}" if v else ""


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https"):
            return ""
        return text
    except Exception:
        return ""


def _normalize_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return fallback


def _normalize_number(value: Any, fallback: float, lo: float, hi: float) -> float:
    try:
        n = float(value)
        return max(lo, min(hi, n))
    except (TypeError, ValueError):
        return fallback


def _normalize_model_list(values: Any) -> List[str]:
    result = []
    for v in (values if isinstance(values, list) else []):
        item = str(v or "").strip()
        if item and len(item) <= 240 and not CONTROL_CHAR.search(item):
            if item not in result:
                result.append(item)
    return result


def _merge_model_lists(defaults: List[str], values: List[str]) -> List[str]:
    return _normalize_model_list(defaults + values)


def _clone_json(v: Any, max_bytes: int = 2 * 1024 * 1024) -> Any:
    try:
        text = json.dumps(v)
        if len(text) > max_bytes:
            return None
        return json.loads(text)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Provider 规范化
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_modelscope_loras(values: Any) -> List[Dict]:
    out = []
    seen = set()
    for raw in (values if isinstance(values, list) else []):
        if not isinstance(raw, dict):
            continue
        lora_id = _clean_text(raw.get("id") or raw.get("loraId") or "", 180)
        target = _clean_text(raw.get("targetModel") or raw.get("target_model") or raw.get("model") or "", 180)
        if not lora_id or not target:
            continue
        key = f"{target}\n{lora_id}"
        if key in seen:
            continue
        seen.add(key)
        strength = _normalize_number(raw.get("strength") or raw.get("default_strength") or 0.8, 0.8, 0, 2)
        out.append({
            "id": lora_id,
            "name": _clean_text(raw.get("name") or lora_id, 80) or lora_id,
            "targetModel": target,
            "strength": strength,
            "enabled": _normalize_bool(raw.get("enabled"), True),
            "note": _clean_text(raw.get("note") or "", 300),
        })
    return out[:120]


def normalize_provider(raw: Any, previous: Optional[Dict] = None) -> Optional[Dict]:
    """规范化单个 provider 配置"""
    if not isinstance(raw, dict):
        return None
    pid = _clean_id(raw.get("id"))
    protocol = _clean_protocol(raw.get("protocol"))
    if not pid or not protocol:
        return None

    prev = previous or {}
    base_url = _normalize_url(raw.get("baseUrl") or raw.get("base_url") or "")
    if not base_url:
        if protocol == "modelscope":
            base_url = DEFAULT_MODELSCOPE_BASE
        elif protocol == "volcengine":
            base_url = DEFAULT_VOLC_BASE
        elif protocol == "comfyui":
            base_url = "http://127.0.0.1:8188"

    allow_remote = _normalize_bool(raw.get("allowRemote"), False) if protocol == "comfyui" else False

    provider = {
        "id": pid,
        "label": _clean_text(raw.get("label") or raw.get("name") or prev.get("label") or pid, 60) or pid,
        "protocol": protocol,
        "baseUrl": base_url,
        "enabled": _normalize_bool(raw.get("enabled"), False),
        "apiKey": _clean_secret(raw.get("apiKey") or raw.get("api_key"), prev.get("apiKey")),
        "imageModels": _normalize_model_list(raw.get("imageModels") or raw.get("image_models")),
        "videoModels": _normalize_model_list(raw.get("videoModels") or raw.get("video_models")),
        "chatModels": _normalize_model_list(raw.get("chatModels") or raw.get("chat_models")),
        "defaults": raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {},
    }

    if protocol == "comfyui" and allow_remote:
        provider["allowRemote"] = True

    # 协议特定配置
    if pid == "modelscope" and protocol == "modelscope":
        provider["imageModels"] = _merge_model_lists(DEFAULT_MODELSCOPE_IMAGE_MODELS, provider["imageModels"])
        provider["chatModels"] = _merge_model_lists(DEFAULT_MODELSCOPE_CHAT_MODELS, provider["chatModels"])
        provider["defaults"] = {"imageModel": DEFAULT_MODELSCOPE_IMAGE_MODELS[0],
                                 "chatModel": DEFAULT_MODELSCOPE_CHAT_MODELS[0], **provider["defaults"]}
        loras = _normalize_modelscope_loras([
            *DEFAULT_MODELSCOPE_LORAS,
            *(raw.get("modelscopeConfig") or raw.get("modelscope_config") or {}).get("loras", []),
            *(raw.get("ms_loras") or raw.get("msLoras") or []),
        ])
        provider["modelscopeConfig"] = {"loras": loras}

    if pid == "volcengine" and protocol == "volcengine":
        provider["imageModels"] = _merge_model_lists(DEFAULT_VOLC_IMAGE_MODELS, provider["imageModels"])
        provider["videoModels"] = _merge_model_lists(DEFAULT_VOLC_VIDEO_MODELS, provider["videoModels"])
        provider["chatModels"] = _merge_model_lists(DEFAULT_VOLC_CHAT_MODELS, provider["chatModels"])
        provider["defaults"] = {
            "imageModel": DEFAULT_VOLC_IMAGE_MODELS[0],
            "videoModel": DEFAULT_VOLC_VIDEO_MODELS[1],
            "chatModel": DEFAULT_VOLC_CHAT_MODELS[0],
            **provider["defaults"],
        }
        vc = raw.get("volcengineConfig") or raw.get("volcengine_config") or {}
        provider["volcengineConfig"] = {
            "project": _clean_text(vc.get("project") or prev.get("volcengineConfig", {}).get("project") or "default", 80),
            "region": _clean_text(vc.get("region") or prev.get("volcengineConfig", {}).get("region") or "cn-beijing", 40),
            "accessKeyId": _clean_secret(vc.get("accessKeyId") or vc.get("accessKeyID") or vc.get("ak"),
                                           prev.get("volcengineConfig", {}).get("accessKeyId", "")),
            "secretAccessKey": _clean_secret(vc.get("secretAccessKey") or vc.get("secretKey") or vc.get("sk"),
                                               prev.get("volcengineConfig", {}).get("secretAccessKey", "")),
        }

    if protocol == "comfyui":
        comfy_cfg = raw.get("comfyuiConfig") or raw.get("comfyui_config") or {}
        provider["comfyuiConfig"] = {
            "instances": [u for u in (comfy_cfg.get("instances") or []) if _normalize_url(u)],
            "workflows": (comfy_cfg.get("workflows") or [])[:80],
        }

    if protocol == "jimeng-cli":
        provider["imageModels"] = _merge_model_lists(DEFAULT_JIMENG_IMAGE_MODELS, provider["imageModels"])
        provider["videoModels"] = _merge_model_lists(DEFAULT_JIMENG_VIDEO_MODELS, provider["videoModels"])
        provider["baseUrl"] = ""
        jc = raw.get("jimengConfig") or raw.get("jimeng_config") or {}
        provider["jimengConfig"] = {
            "executablePath": _clean_text(jc.get("executablePath") or jc.get("binPath") or "", 260),
            "useWsl": _normalize_bool(jc.get("useWsl"), False),
            "wslDistro": _clean_text(jc.get("wslDistro") or "", 80),
            "pollSeconds": int(_normalize_number(jc.get("pollSeconds") or 3600, 3600, 0, 3600)),
        }

    return provider


def normalize_providers(raw_providers: Any, current: Optional[List[Dict]] = None) -> List[Dict]:
    """规范化 providers 列表"""
    prev_by_id = {}
    if isinstance(current, list):
        for p in current:
            if isinstance(p, dict):
                pid = _clean_id(p.get("id"))
                if pid:
                    prev_by_id[pid] = p

    by_id = {}
    raw_list = raw_providers if isinstance(raw_providers, list) else []

    # 先处理 default providers
    for default in _get_default_providers():
        pid = default["id"]
        prev = prev_by_id.get(pid)
        merged = {**default, **(prev or {})}
        p = normalize_provider(merged, prev)
        if p:
            by_id[pid] = p

    # 处理用户提供的
    for raw in raw_list:
        pid = _clean_id(raw.get("id"))
        prev = prev_by_id.get(pid) or by_id.get(pid)
        p = normalize_provider(raw, prev)
        if p:
            by_id[pid] = p

    return list(by_id.values())


def _get_default_providers() -> List[Dict]:
    """返回默认 provider 模板.

    P11-A: 默认开启 OpenAI 兼容协议 (``enabled=True``), 让 ``call_provider_smart``
    路径在没有任何 settings.json 配置时也能命中 (无 apiKey 时自动 mock 降级,
    有 apiKey 时直接打 https://api.openai.com/v1)。其他 provider 仍默认关闭,
    因为它们需要各自平台的 API key 或本地守护进程。
    """
    return [
        {"id": "openai-compatible", "label": "OpenAI 兼容", "protocol": "openai-compatible",
         "baseUrl": "https://api.openai.com/v1", "enabled": True,
         "imageModels": ["dall-e-3", "gpt-image-1"],
         "videoModels": [],
         "chatModels": ["gpt-4o-mini", "gpt-4o", "o1-mini", "claude-3-5-sonnet", "deepseek-chat"],
         "defaults": {"chatModel": "gpt-4o-mini", "imageModel": "dall-e-3"}},
        {"id": "modelscope", "label": "ModelScope", "protocol": "modelscope",
         "baseUrl": DEFAULT_MODELSCOPE_BASE, "enabled": False,
         "imageModels": DEFAULT_MODELSCOPE_IMAGE_MODELS, "videoModels": [], "chatModels": DEFAULT_MODELSCOPE_CHAT_MODELS,
         "defaults": {"imageModel": DEFAULT_MODELSCOPE_IMAGE_MODELS[0], "chatModel": DEFAULT_MODELSCOPE_CHAT_MODELS[0]},
         "modelscopeConfig": {"loras": DEFAULT_MODELSCOPE_LORAS}},
        {"id": "volcengine", "label": "火山引擎", "protocol": "volcengine",
         "baseUrl": DEFAULT_VOLC_BASE, "enabled": False,
         "imageModels": DEFAULT_VOLC_IMAGE_MODELS, "videoModels": DEFAULT_VOLC_VIDEO_MODELS, "chatModels": DEFAULT_VOLC_CHAT_MODELS,
         "defaults": {"imageModel": DEFAULT_VOLC_IMAGE_MODELS[0], "videoModel": DEFAULT_VOLC_VIDEO_MODELS[1], "chatModel": DEFAULT_VOLC_CHAT_MODELS[0]},
         "volcengineConfig": {"project": "default", "region": "cn-beijing"}},
        {"id": "comfyui", "label": "ComfyUI", "protocol": "comfyui",
         "baseUrl": "http://127.0.0.1:8188", "enabled": False,
         "imageModels": [], "videoModels": [], "chatModels": [], "defaults": {},
         "comfyuiConfig": {"instances": ["http://127.0.0.1:8188"], "workflows": []}},
        {"id": "jimeng-cli", "label": "即梦 CLI", "protocol": "jimeng-cli",
         "baseUrl": "", "enabled": False,
         "imageModels": DEFAULT_JIMENG_IMAGE_MODELS, "videoModels": DEFAULT_JIMENG_VIDEO_MODELS,
         "chatModels": [], "defaults": {},
         "jimengConfig": {"executablePath": "", "useWsl": False, "wslDistro": "", "pollSeconds": 3600}},
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Adapters (各协议生成调用)
# ═══════════════════════════════════════════════════════════════════════════════

async def call_openai_compatible(provider: Dict, payload: Dict, kind: str = "chat") -> Dict:
    """OpenAI 兼容 API 调用"""
    base = provider.get("baseUrl", "")
    api_key = provider.get("apiKey", "")
    if not base:
        return {"ok": False, "code": "missing_base_url", "error": "Base URL 为空"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if kind == "chat":
        model = payload.get("model", (provider.get("chatModels") or [None])[0] or "gpt-4o")
        endpoint = f"{base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
        if "temperature" in payload:
            body["temperature"] = payload["temperature"]
        if "max_tokens" in payload:
            body["max_tokens"] = payload["max_tokens"]
    elif kind == "image":
        model = payload.get("model", (provider.get("imageModels") or [None])[0] or "dall-e-3")
        endpoint = f"{base}/images/generations"
        body = {"model": model, "prompt": payload.get("prompt", ""), "n": payload.get("n", 1)}
    elif kind == "video":
        model = payload.get("model", (provider.get("videoModels") or [None])[0] or "")
        endpoint = f"{base}/videos/generations" if "videos" in base else f"{base}/images/generations"
        body = {"model": model, "prompt": payload.get("prompt", ""), "n": payload.get("n", 1)}
    else:
        return {"ok": False, "code": "invalid_kind", "error": f"不支持的类型: {kind}"}

    timeout_val = max(30, (payload.get("timeout_ms") or 120000) / 1000)
    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(endpoint, json=body, headers=headers)
            data = resp.json()
            if resp.status_code >= 400:
                return {"ok": False, "code": "api_error", "error": str(data)}
            return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)}


async def call_volcengine(provider: Dict, payload: Dict, kind: str = "chat") -> Dict:
    """火山引擎 API 调用 (方舟)"""
    base = provider.get("baseUrl", DEFAULT_VOLC_BASE)
    api_key = provider.get("apiKey", "")
    vc = provider.get("volcengineConfig") or {}

    if not api_key:
        return {"ok": False, "code": "missing_api_key", "error": "请先填写方舟 Ark API Key"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if kind == "chat":
        model = payload.get("model", provider.get("defaults", {}).get("chatModel", "doubao-seed-1-6-250615"))
        endpoint = f"{base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
    elif kind == "image":
        model = payload.get("model", provider.get("defaults", {}).get("imageModel", "doubao-seedream-4-0-250828"))
        endpoint = f"{base}/images/generations"
        body = {"model": model, "prompt": payload.get("prompt", ""), "n": payload.get("n", 1)}
    elif kind == "video":
        model = payload.get("model", provider.get("defaults", {}).get("videoModel", "doubao-seedance-2-0-260128"))
        endpoint = f"{base}/contents/generations/video"
        body = {"model": model, "content": payload.get("prompt", "")}
    else:
        return {"ok": False, "code": "invalid_kind", "error": f"不Supported: {kind}"}

    timeout_val = max(30, (payload.get("timeout_ms") or 3600000) / 1000)
    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(endpoint, json=body, headers=headers)
            data = resp.json()
            if resp.status_code >= 400:
                return {"ok": False, "code": "api_error", "error": str(data)}
            return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)}


async def call_comfyui(provider: Dict, payload: Dict) -> Dict:
    """ComfyUI API 调用"""
    instances = provider.get("comfyuiConfig", {}).get("instances", [])
    base = instances[0] if instances else provider.get("baseUrl", "http://127.0.0.1:8188")
    workflow = payload.get("workflowJson") or payload.get("workflow")
    prompt_text = payload.get("prompt", "")

    # 简化: 加载 workflow 并替换 prompt
    if workflow:
        try:
            wf = json.loads(workflow) if isinstance(workflow, str) else workflow
        except Exception:
            wf = workflow

        # 查找 CLIPTextEncode 节点并替换
        for node_id, node in (wf or {}).items():
            if isinstance(node, dict):
                ct = str(node.get("class_type", "")).lower()
                if "cliptextencode" in ct and "text" in node.get("inputs", {}):
                    node["inputs"]["text"] = prompt_text

        async with httpx.AsyncClient(timeout=600) as client:
            try:
                resp = await client.post(f"{base}/prompt", json={"prompt": wf})
                data = resp.json()
                if resp.status_code < 400:
                    return {"ok": True, "prompt_id": data.get("prompt_id", "")}
                return {"ok": False, "error": str(data)}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    return {"ok": False, "code": "no_workflow", "error": "ComfyUI 调用需要 workflowJson"}


async def call_jimeng_cli(provider: Dict, payload: Dict, kind: str = "image") -> Dict:
    """即梦 CLI 调用 (通过子进程)"""
    jc = provider.get("jimengConfig") or {}
    exe = jc.get("executablePath", "dreamina")
    use_wsl = jc.get("useWsl", False)
    model = payload.get("model", (provider.get("imageModels") or [None])[0] or "seedream-4.7")
    prompt = payload.get("prompt", "")

    cmd = [exe, "--model", model, "--prompt", prompt]
    if kind == "video":
        cmd.extend(["--mode", "video"])
    if payload.get("size"):
        cmd.extend(["--size", payload["size"]])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600,
            shell=use_wsl,
        )
        if result.returncode == 0:
            output_path = result.stdout.strip()
            if output_path and os.path.exists(output_path):
                return {"ok": True, "localPath": output_path,
                        "url": f"/imdf/media/output/{os.path.basename(output_path)}"}
            return {"ok": True, "message": output_path or "即梦 CLI 生成完成，但未返回路径"}
        return {"ok": False, "error": result.stderr[:2000] or result.stdout[:2000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "timeout", "error": "即梦 CLI 超时"}
    except FileNotFoundError:
        return {"ok": False, "code": "not_found", "error": f"未找到即梦 CLI: {exe}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def call_provider(provider: Dict, payload: Dict, kind: str = "chat") -> Dict:
    """根据 protocol 路由到对应 adapter"""
    protocol = provider.get("protocol", "")
    if protocol == "openai-compatible":
        return await call_openai_compatible(provider, payload, kind)
    elif protocol == "modelscope":
        return await call_openai_compatible(provider, payload, kind)
    elif protocol == "volcengine":
        return await call_volcengine(provider, payload, kind)
    elif protocol == "comfyui":
        return await call_comfyui(provider, payload)
    elif protocol == "jimeng-cli":
        return await call_jimeng_cli(provider, payload, kind)
    return {"ok": False, "code": "unsupported_protocol", "error": f"不支持的协议: {protocol}"}


# ═══════════════════════════════════════════════════════════════════════════════
# ComfyUI 工作流字段推断 (复刻 comfyui.js 的 inferWorkflowFields)
# ═══════════════════════════════════════════════════════════════════════════════

def infer_workflow_fields(prompt: Dict) -> List[Dict]:
    """从 ComfyUI workflow 推测字段映射"""
    fields = []
    seen = set()
    prompt_seen = False
    image_index = 0
    clip_roles = {}

    for nid, node in (prompt or {}).items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        inputs = node["inputs"]
        pos = inputs.get("positive")
        neg = inputs.get("negative")
        if isinstance(pos, list) and pos:
            clip_roles[str(pos[0])] = "prompt"
        if isinstance(neg, list) and neg:
            clip_roles[str(neg[0])] = "negative"

    def _push(node_id, fname, source):
        key = f"{node_id}::{fname}"
        if key in seen:
            return
        seen.add(key)
        fields.append({"nodeId": node_id, "fieldName": fname, "source": source})

    for nid, node in (prompt or {}).items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        ct = str(node.get("class_type", "")).lower()
        title = f"{node.get('_meta', {}).get('title', '')} {node.get('title', '')}".lower()

        if "cliptextencode" in ct and "text" in inputs:
            role = clip_roles.get(str(nid))
            is_neg = False
            if role == "negative":
                is_neg = True
            elif role != "prompt":
                is_neg = bool(re.search(r"negative|neg|反向|负向|不要|排除", title)) or (prompt_seen and role is None)
            _push(nid, "text", "negative" if is_neg else "prompt")
            if not is_neg:
                prompt_seen = True

        if ("loadimage" in ct or "imageinput" in ct) and "image" in inputs:
            image_index += 1
            _push(nid, "image", f"image{min(image_index, 3)}")

        if "ksampler" in ct or "sampler" in ct:
            if "seed" in inputs:
                _push(nid, "seed", "seed")
            if "noise_seed" in inputs:
                _push(nid, "noise_seed", "seed")
            for k in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if k in inputs:
                    _push(nid, k, k)

        if "emptylatent" in ct or "latentimage" in ct:
            for k in ("width", "height", "batch_size"):
                if k in inputs:
                    _push(nid, k, k)

    return fields


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3-W2: Rate Limiter — 进程内滑动窗口 (per (user_id, provider_id))
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """简单的 (user_id, provider_id) → 滑动窗口计数。

    内存版, 单进程够用; 多 worker / 多机部署应换 Redis (``INCR`` + ``EXPIRE``)。

    使用::

        limiter = RateLimiter(window_seconds=3600)
        allowed, remaining = limiter.check("user_abc", "openai-compatible", per_hour=1000)
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded")
    """

    def __init__(self, window_seconds: int = 3600) -> None:
        self.window_seconds = int(window_seconds)
        self._buckets: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id: str, provider_id: str, per_hour: int) -> Tuple[bool, int]:
        """检查并记录一次 hit。返回 ``(allowed, remaining)``。"""
        now = time.time()
        uid = str(user_id or "anonymous")[:60]
        pid = str(provider_id or "*")[:60]
        limit = max(1, int(per_hour))
        with self._lock:
            bucket = self._buckets.setdefault((uid, pid), deque())
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, 0
            bucket.append(now)
            return True, max(0, limit - len(bucket))

    def reset(self, user_id: Optional[str] = None, provider_id: Optional[str] = None) -> None:
        """重置 (测试用)。"""
        with self._lock:
            if user_id is None and provider_id is None:
                self._buckets.clear()
            else:
                keys = [k for k in self._buckets if (
                    (user_id is None or k[0] == user_id) and
                    (provider_id is None or k[1] == provider_id)
                )]
                for k in keys:
                    del self._buckets[k]


def rate_limit(user_id: str, provider_id: str = "*", per_hour: Optional[int] = None) -> Tuple[bool, int]:
    """便捷函数 — 检查限流。

    ``per_hour=None`` → 环境变量 ``AI_RATE_LIMIT_PER_HOUR`` (默认 1000)。
    """
    limit = int(per_hour) if per_hour and per_hour > 0 else int(
        os.environ.get("AI_RATE_LIMIT_PER_HOUR", "1000")
    )
    return _GLOBAL_LIMITER.check(user_id, provider_id, limit)


_GLOBAL_LIMITER = RateLimiter(window_seconds=3600)
"""进程级 RateLimiter 单例 — canvas_web 直接 ``rate_limit()`` 即可。"""


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3-W2: Cost Estimation — 按协议 + 模型 算 USD
# ═══════════════════════════════════════════════════════════════════════════════

# 默认 USD per 1K tokens (input / output 同样单价, 简化模型)
# 可通过 ``AI_COST_PER_1K_TOKENS`` 环境变量覆盖 (格式: "provider:model=price_in,price_out,provider:*=price_in,price_out")
DEFAULT_COST_TABLE: Dict[str, Dict[str, Tuple[float, float]]] = {
    # protocol → model → (input_per_1k, output_per_1k)
    "openai-compatible": {
        "gpt-4o": (0.005, 0.015),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4-turbo": (0.01, 0.03),
        "claude-3-5-sonnet": (0.003, 0.015),
        "deepseek-chat": (0.00014, 0.00028),
        "deepseek-reasoner": (0.00055, 0.0022),
        "*": (0.002, 0.006),  # 默认 fallback
    },
    "modelscope": {
        "*": (0.0008, 0.001),  # ModelScope 通义系列大致
    },
    "volcengine": {
        "doubao-seed-1-6-250615": (0.0008, 0.002),
        "doubao-seedream-4-0-250828": (0.0, 0.04),  # 图像生成按张
        "doubao-seedance-2-0-260128": (0.0, 0.40),  # 视频按秒
        "*": (0.001, 0.003),
    },
    "jimeng-cli": {
        "*": (0.0, 0.0),  # 自托管不计费
    },
    "comfyui": {
        "*": (0.0, 0.0),  # 本地 GPU 不计费
    },
}


def _parse_env_cost_overrides() -> Dict[str, Dict[str, Tuple[float, float]]]:
    """解析 ``AI_COST_PER_1K_TOKENS`` 环境变量。格式::

        AI_COST_PER_1K_TOKENS=openai-compatible:gpt-4o=0.005,0.015;volcengine:*=0.001,0.002
    """
    raw = os.environ.get("AI_COST_PER_1K_TOKENS", "").strip()
    if not raw:
        return {}
    out: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        head, prices = entry.rsplit("=", 1)
        if ":" not in head:
            continue
        proto, model = head.split(":", 1)
        proto = proto.strip().lower()
        model = model.strip()
        parts = [p.strip() for p in prices.split(",")]
        if len(parts) != 2:
            continue
        try:
            inp, outp = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        out.setdefault(proto, {})[model] = (inp, outp)
    return out


def _lookup_cost(protocol: str, model: str) -> Tuple[float, float]:
    """查表, 找 (input_per_1k, output_per_1k)。fallback = (*, *)。"""
    proto = str(protocol or "").strip().lower()
    m = str(model or "").strip()
    # env 覆盖
    overrides = _parse_env_cost_overrides()
    table = {**DEFAULT_COST_TABLE.get(proto, {}), **overrides.get(proto, {})}
    if m in table:
        return table[m]
    if "*" in table:
        return table["*"]
    # 全局 fallback
    return (0.001, 0.003)


def compute_cost_usd(
    protocol: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """根据 protocol + model + tokens 计算 USD 成本。

    返回 float, 4 位小数。tokens = 0 → 0。
    """
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    in_p, out_p = _lookup_cost(protocol, model)
    cost = (prompt_tokens / 1000.0) * in_p + (completion_tokens / 1000.0) * out_p
    return round(max(0.0, cost), 6)


def cost_estimate(
    protocol: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Dict[str, Any]:
    """人类友好的成本估算 — ``cost_estimate`` 在任务描述里的接口名。

    返回 ``{"protocol", "model", "prompt_tokens", "completion_tokens",
    "input_per_1k_usd", "output_per_1k_usd", "cost_usd"}``。
    """
    in_p, out_p = _lookup_cost(protocol, model)
    cost = compute_cost_usd(protocol, model, prompt_tokens, completion_tokens)
    return {
        "protocol": protocol,
        "model": model,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "input_per_1k_usd": in_p,
        "output_per_1k_usd": out_p,
        "cost_usd": cost,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3-W2: Circuit Breaker — 每 provider 独立, 错误率 > 50% 自动 open
# ═══════════════════════════════════════════════════════════════════════════════

class CircuitBreakerOpen(Exception):
    """当熔断器 open 时, 拒绝调用。"""


class _CircuitState:
    """单 provider 熔断状态。"""

    def __init__(self, window_size: int = 20, error_threshold: float = 0.5,
                 cooldown_seconds: float = 30.0) -> None:
        self.window_size = int(window_size)
        self.error_threshold = float(error_threshold)
        self.cooldown_seconds = float(cooldown_seconds)
        self._calls: Deque[bool] = deque(maxlen=self.window_size)
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if (time.time() - self._opened_at) >= self.cooldown_seconds:
                # 半开 — 放行一次试水
                self._opened_at = None
                self._calls.clear()
                return True
            return False

    def record(self, ok: bool) -> None:
        with self._lock:
            self._calls.append(bool(ok))
            if len(self._calls) < max(5, self.window_size // 2):
                return  # 数据不够, 不决策
            errors = sum(1 for x in self._calls if not x)
            error_rate = errors / len(self._calls)
            if error_rate >= self.error_threshold and self._opened_at is None:
                self._opened_at = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._calls)
            errors = sum(1 for x in self._calls if not x)
            rate = (errors / total) if total else 0.0
            return {
                "window_size": self.window_size,
                "calls": total,
                "errors": errors,
                "error_rate": round(rate, 4),
                "error_threshold": self.error_threshold,
                "state": "open" if self._opened_at is not None else "closed",
                "opened_at": self._opened_at,
                "cooldown_seconds": self.cooldown_seconds,
            }


class CircuitBreaker:
    """进程内 circuit breaker (per provider)。"""

    def __init__(self, window_size: int = 20, error_threshold: float = 0.5,
                 cooldown_seconds: float = 30.0) -> None:
        self._states: Dict[str, _CircuitState] = {}
        self._defaults = {
            "window_size": int(window_size),
            "error_threshold": float(error_threshold),
            "cooldown_seconds": float(cooldown_seconds),
        }
        self._lock = threading.Lock()

    def _state_for(self, provider_id: str) -> _CircuitState:
        with self._lock:
            st = self._states.get(provider_id)
            if st is None:
                st = _CircuitState(**self._defaults)
                self._states[provider_id] = st
            return st

    def allow(self, provider_id: str) -> bool:
        return self._state_for(provider_id).allow()

    def record(self, provider_id: str, ok: bool) -> None:
        self._state_for(provider_id).record(ok)

    def snapshot(self, provider_id: Optional[str] = None) -> Dict[str, Any]:
        if provider_id:
            return self._state_for(provider_id).snapshot()
        with self._lock:
            return {pid: self._states[pid].snapshot() for pid in sorted(self._states)}

    def reset(self, provider_id: Optional[str] = None) -> None:
        with self._lock:
            if provider_id:
                self._states.pop(provider_id, None)
            else:
                self._states.clear()


_GLOBAL_BREAKER = CircuitBreaker()
"""进程级 CircuitBreaker 单例。"""


def circuit_breaker(provider_id: str, error_rate: Optional[float] = None,
                    cooldown_seconds: Optional[float] = None) -> Dict[str, Any]:
    """任务描述里的接口名 — ``circuit_breaker(provider, error_rate)``。

    两种用法:
    1. **查状态**: ``circuit_breaker("openai-compatible")`` → 返回当前快照
    2. **手动触发**: ``circuit_breaker("openai-compatible", error_rate=0.7)`` → 强行设置状态
       (用于测试熔断流程, 不推荐生产调用)

    返回 ``{"provider_id", "state", "error_rate", "calls", "errors", "cooldown_seconds"}``。
    """
    if error_rate is not None:
        # 手动注入 — 把 window 填满到指定错误率, 然后 record 触发熔断
        try:
            rate = float(error_rate)
            cooldown = float(cooldown_seconds) if cooldown_seconds else _GLOBAL_BREAKER._defaults["cooldown_seconds"]
            st = _CircuitState(
                window_size=_GLOBAL_BREAKER._defaults["window_size"],
                error_threshold=_GLOBAL_BREAKER._defaults["error_threshold"],
                cooldown_seconds=cooldown,
            )
            with _GLOBAL_BREAKER._lock:
                _GLOBAL_BREAKER._states[provider_id] = st
            # 先填 enough ok 触发 "数据够决策" 阈值
            target_errors = max(5, int(st.window_size * rate))
            for _ in range(st.window_size - target_errors):
                st.record(True)
            for _ in range(target_errors):
                st.record(False)
        except Exception as e:
            logger.warning(f"circuit_breaker() 手动注入失败: {e}")
    return _GLOBAL_BREAKER.snapshot(provider_id)


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3-W2: Mock Adapters — 没真 key 时自动降级 (让 dev/CI 不依赖外部服务)
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_RESPONSES = {
    "chat": {
        "id": f"mock-chat-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "model": "mock-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a mock AI response — no real API key configured.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30},
    },
    "image": {
        "created": int(time.time()),
        "data": [{"url": "https://via.placeholder.com/512.png?text=mock+image"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 0, "total_tokens": 8},
    },
    "video": {
        "id": f"mock-video-{uuid.uuid4().hex[:8]}",
        "status": "queued",
        "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
    },
}


async def _mock_provider(provider: Dict, payload: Dict, kind: str = "chat") -> Dict:
    """没 apiKey 时返回固定 mock 响应 (用于开发/CI)。"""
    model = (payload.get("model") or "").strip()
    if not model:
        models = provider.get(f"{kind}Models") or []
        model = models[0] if models else "mock-model"
    resp = dict(_MOCK_RESPONSES.get(kind, _MOCK_RESPONSES["chat"]))
    resp["model"] = model
    resp["mock"] = True
    return {
        "ok": True,
        "data": resp,
        "mock": True,
        "provider_id": provider.get("id"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3-W2: 入口函数 — ``call_provider_smart`` (限流 + 熔断 + mock 降级 + 用量记账)
# ═══════════════════════════════════════════════════════════════════════════════

async def call_provider_smart(
    provider: Dict,
    payload: Dict,
    kind: str = "chat",
    *,
    user_id: str = "anonymous",
    org_id: str = "",
    record_usage: bool = True,
) -> Dict:
    """比 ``call_provider`` 更"业务完整"的入口 — 自动:
    1. 限流检查 (env ``AI_RATE_LIMIT_PER_HOUR``)
    2. 熔断检查 (process-global CircuitBreaker)
    3. mock 降级 (无 apiKey 时直接返回 mock)
    4. 用量记账 (调用 usage_tracker.record, 含 cost_usd)
    5. 熔断状态更新 (成功=ok, 失败=error)

    返回 ``call_provider`` 同样的 ``{ok, data, code, error}``, 但额外带
    ``mock`` / ``provider_id`` / ``cost_usd`` / ``rate_limited`` 字段。
    """
    pid = provider.get("id", "unknown")
    start_ms = int(time.time() * 1000)

    # 1. 限流
    allowed, _remaining = rate_limit(user_id, pid)
    if not allowed:
        if record_usage:
            try:
                from engines.usage_tracker import get_tracker
                get_tracker().record(
                    user_id=user_id, org_id=org_id, provider_id=pid,
                    protocol=provider.get("protocol", ""), kind=kind,
                    model=str(payload.get("model", "")), status="error",
                    error_code="rate_limited", latency_ms=int(time.time() * 1000) - start_ms,
                )
            except Exception:
                pass
        return {"ok": False, "code": "rate_limited",
                "error": f"用户 {user_id} 对 provider {pid} 超出每小时限额",
                "provider_id": pid, "rate_limited": True}

    # 2. 熔断
    if not _GLOBAL_BREAKER.allow(pid):
        return {"ok": False, "code": "circuit_open",
                "error": f"provider {pid} 熔断中, 请稍后重试",
                "provider_id": pid}

    # 3. mock 降级 (没 apiKey + comfyui 没实例)
    needs_key = provider.get("protocol") in ("openai-compatible", "modelscope", "volcengine")
    has_key = bool(provider.get("apiKey"))
    if needs_key and not has_key:
        result = await _mock_provider(provider, payload, kind)
    elif provider.get("protocol") == "comfyui":
        instances = provider.get("comfyuiConfig", {}).get("instances") or []
        if not instances:
            result = await _mock_provider(provider, payload, kind)
        else:
            result = await call_provider(provider, payload, kind)
    else:
        result = await call_provider(provider, payload, kind)

    # 4. 熔断更新
    _GLOBAL_BREAKER.record(pid, bool(result.get("ok")))

    # 4.5 P5-W1: audit_chain 记录 (HMAC 签名, 防篡改)
    try:
        from engines.audit_chain import get_chain as _get_audit_chain
        _chain = _get_audit_chain()
        from datetime import datetime, timezone
        _ts = datetime.now(timezone.utc).isoformat()
        # body_hash = provider_id + model + status + cost 的 hash
        import hashlib
        _body_str = f"{pid}|{payload.get('model', '')}|{result.get('ok')}|{provider.get('protocol', '')}|{user_id}"
        _body_hash = hashlib.sha256(_body_str.encode("utf-8")).hexdigest()[:16]
        _chain.append(
            timestamp=_ts,
            method="AI_PROVIDER",
            path=f"/ai/{provider.get('protocol', '')}/{pid}/{kind}",
            user=user_id,
            body_hash=_body_hash,
            status_code=200 if result.get("ok") else 500,
            actor=f"provider={pid}",
        )
    except Exception as _audit_err:
        # audit 失败不影响主调用 (降级), 但要记 warning 便于排障
        logger.warning(f"call_provider_smart audit_chain record failed: {_audit_err}")

    # 5. 用量记账
    if record_usage:
        try:
            from engines.usage_tracker import get_tracker
            data = result.get("data") or {}
            usage = data.get("usage") if isinstance(data, dict) else None
            pt = int((usage or {}).get("prompt_tokens", 0))
            ct = int((usage or {}).get("completion_tokens", 0))
            tt = int((usage or {}).get("total_tokens", pt + ct))
            cost = compute_cost_usd(
                provider.get("protocol", ""),
                str(payload.get("model", "")),
                prompt_tokens=pt, completion_tokens=ct,
            )
            get_tracker().record(
                user_id=user_id, org_id=org_id, provider_id=pid,
                protocol=provider.get("protocol", ""), kind=kind,
                model=str(payload.get("model", "")),
                status="ok" if result.get("ok") else "error",
                prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
                cost_usd=cost, latency_ms=int(time.time() * 1000) - start_ms,
                error_code=str(result.get("code") or ""),
                error_message=str(result.get("error") or "")[:2000],
            )
            result["cost_usd"] = cost
            result["usage_tokens"] = tt
        except Exception as e:
            logger.warning(f"call_provider_smart usage record failed: {e}")

    result.setdefault("provider_id", pid)
    return result
