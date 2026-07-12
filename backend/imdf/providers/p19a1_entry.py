"""P19-A1: 隔离的 invoke 入口 — 防被其他 worker 覆盖。

提供:
    - ``invoke(model, messages|prompt, ...)`` 统一路由 + fallback chain
    - ``list_all_providers()`` 返回 5 个 P19-A1 provider 实例 (dict 格式)
    - ``get_provider_by_family(family)`` 按 family 取实例
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .claude import ClaudeProvider
from .deepseek import DeepSeekProvider
from .qwen import QwenProvider
from .doubao_extended import DoubaoProvider
from .agnes import AgnesProvider

logger = logging.getLogger(__name__)


_PROVIDER_FACTORIES: Dict[str, Any] = {
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
    "qwen": QwenProvider,
    "doubao": DoubaoProvider,
    "agnes": AgnesProvider,
}


def list_all_providers() -> Dict[str, Any]:
    """返回 ``{family_name: provider_instance}`` — 5 个 P19-A1 provider."""
    cache = globals().setdefault("_p19a1_cache", {})
    for family, cls in _PROVIDER_FACTORIES.items():
        if family not in cache:
            cache[family] = cls()
    return cache


def get_provider_by_family(family: str) -> Optional[Any]:
    """按 family 取 P19-A1 provider 实例。"""
    return list_all_providers().get(family)


_MODEL_ALIASES: Dict[str, tuple] = {
    "claude-3-5-sonnet": ("claude", "claude-3-5-sonnet-20241022"),
    "claude-opus-4": ("claude", "claude-opus-4-20250514"),
    "claude-3-haiku": ("claude", "claude-3-haiku-20240307"),
    "deepseek-chat": ("deepseek", "deepseek-chat"),
    "deepseek-coder": ("deepseek", "deepseek-coder"),
    "qwen-plus": ("qwen", "qwen-plus"),
    "qwen-max": ("qwen", "qwen-max"),
    "qwen-vl-plus": ("qwen", "qwen-vl-plus"),
    "doubao-seed-1-6": ("doubao", "doubao-seed-1-6-250615"),
    "doubao-1-5-vision-pro": ("doubao", "doubao-1-5-vision-pro-250328"),
    "agnes-2.0-flash": ("agnes", "agnes-2.0-flash"),
    "agnes-image-2.1-flash": ("agnes", "agnes-image-2.1-flash"),
    "agnes-video-2.0": ("agnes", "agnes-video-2.0"),
    "agnes-drama-1.0": ("agnes", "agnes-drama-1.0"),
}


def _resolve_model(model: str) -> tuple:
    if not model:
        return ("claude", "claude-3-5-sonnet-20241022")
    if ":" in model:
        family, mid = model.split(":", 1)
        family = family.strip().lower()
        if family in _PROVIDER_FACTORIES:
            return (family, mid.strip())
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]
    m_lower = model.lower()
    if m_lower.startswith("claude"):
        return ("claude", model)
    if m_lower.startswith("deepseek"):
        return ("deepseek", model)
    if m_lower.startswith("qwen"):
        return ("qwen", model)
    if m_lower.startswith("doubao"):
        return ("doubao", model)
    if m_lower.startswith("agnes"):
        return ("agnes", model)
    return ("claude", model)


async def _try_provider_chat(prov, messages, model, temperature, max_tokens):
    try:
        return await prov.chat(messages, model=model,
                                temperature=temperature, max_tokens=max_tokens)
    except Exception as e:
        return {
            "success": False,
            "content": "",
            "model": model,
            "provider": getattr(prov, "provider_name", "unknown"),
            "usage": {},
            "error": f"invoke provider exception: {type(e).__name__}: {e}",
            "latency_ms": 0.0,
        }


async def invoke(
    model: str,
    messages: Optional[List[Dict[str, str]]] = None,
    prompt: Optional[str] = None,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    fallback: bool = True,
) -> Dict[str, Any]:
    """P19-A1 统一入口: invoke(provider, model, prompt) + fallback chain."""
    if messages is None and prompt is not None:
        messages = [{"role": "user", "content": prompt}]
    messages = messages or [{"role": "user", "content": "hi"}]

    primary_family, primary_model = _resolve_model(model)
    primary_prov = get_provider_by_family(primary_family)
    if primary_prov is None:
        return {
            "success": False,
            "content": "",
            "model": model,
            "provider": "none",
            "usage": {},
            "error": f"未知 provider family: {primary_family}",
            "latency_ms": 0.0,
        }

    resp = await _try_provider_chat(
        primary_prov, messages, primary_model, temperature, max_tokens,
    )
    if resp.get("success"):
        return resp

    primary_error = resp.get("error", "unknown")

    if not fallback:
        return resp

    fallback_chain = ["deepseek", "qwen", "agnes", "doubao", "claude"]
    attempted = {primary_family}

    for fb_family in fallback_chain:
        if fb_family in attempted:
            continue
        fb_prov = get_provider_by_family(fb_family)
        if fb_prov is None:
            continue
        models = fb_prov.get_models()
        fb_model = next(
            (m["id"] for m in models if m.get("default")),
            (models[0]["id"] if models else ""),
        )
        if not fb_model:
            continue
        fb_resp = await _try_provider_chat(
            fb_prov, messages, fb_model, temperature, max_tokens,
        )
        if fb_resp.get("success"):
            fb_resp["fallback_used"] = True
            fb_resp["fallback_reason"] = primary_error
            fb_resp["fallback_from"] = primary_family
            return fb_resp
        attempted.add(fb_family)

    resp["fallback_used"] = True
    resp["fallback_reason"] = primary_error
    return resp


__all__ = [
    "invoke", "list_all_providers", "get_provider_by_family",
]
