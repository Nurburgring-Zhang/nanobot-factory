"""P19-A1: Anthropic Claude Provider — claude-3-5-sonnet + claude-opus-4.

API: https://api.anthropic.com/v1/messages
Auth: x-api-key header + anthropic-version header
Pricing: $3/$15 per 1M tokens (sonnet)
Fallback: placeholder when no API key (开发/CI 环境照样跑通)

支持的模型:
    claude-3-5-sonnet-20241022  — 默认 chat, 8192 tokens
    claude-opus-4-20250514      — 大上下文推理
    claude-3-haiku-20240307     — 轻量快

Usage::

    from providers.claude import ClaudeProvider
    p = ClaudeProvider()                  # 从 ANTHROPIC_API_KEY env 读
    resp = await p.chat([{"role":"user","content":"hi"}])
    models = p.get_models()
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ClaudeProvider:
    provider_name = "claude"
    family = "claude"
    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"
    ENV_VAR = "ANTHROPIC_API_KEY"

    # 价格 USD per 1M tokens (input/output)
    PRICE_PER_M_INPUT = 3.0
    PRICE_PER_M_OUTPUT = 15.0

    DEFAULT_MODELS = [
        {"id": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet",
         "max_tokens": 8192, "capabilities": ["chat"], "default": True},
        {"id": "claude-opus-4-20250514", "label": "Claude Opus 4",
         "max_tokens": 16384, "capabilities": ["chat", "reasoning"]},
        {"id": "claude-3-haiku-20240307", "label": "Claude 3 Haiku",
         "max_tokens": 4096, "capabilities": ["chat"]},
    ]

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or os.environ.get(self.ENV_VAR, "")).strip()
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    # ─── Public API ──────────────────────────────────────────────────────

    def get_models(self) -> List[Dict[str, Any]]:
        """返回模型列表。无 key 时仍返回(开发用)。"""
        return [dict(m) for m in self.DEFAULT_MODELS]

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """调用 Anthropic /v1/messages。
        
        返回 ``{"success", "content", "model", "provider", "usage", "error", "latency_ms"}``。
        无 key 或失败时 ``success=False`` 带 ``error`` 字段。
        """
        model = model or "claude-3-5-sonnet-20241022"
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(messages, model, "ANTHROPIC_API_KEY 未配置")

        # 分拆 system 消息
        system_msg = ""
        chat_messages: List[Dict[str, str]] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_msg += (("\n" if system_msg else "") + content)
            else:
                chat_messages.append({"role": role, "content": content})

        body: Dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if system_msg:
            body["system"] = system_msg
        if temperature > 0:
            body["temperature"] = temperature

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.API_VERSION,
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = (time.time() - t0) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                content_blocks = data.get("content", [])
                text = ""
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += block.get("text", "")
                usage = data.get("usage", {}) or {}
                usage_norm = {
                    "prompt_tokens": int(usage.get("input_tokens") or 0),
                    "completion_tokens": int(usage.get("output_tokens") or 0),
                    "total_tokens": int(usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
                }
                return {
                    "success": True,
                    "content": text,
                    "model": model,
                    "provider": self.provider_name,
                    "usage": usage_norm,
                    "error": "",
                    "latency_ms": round(latency_ms, 1),
                }
            err_text = resp.text[:500] if hasattr(resp, "text") else ""
            return {
                "success": False,
                "content": "",
                "model": model,
                "provider": self.provider_name,
                "usage": {},
                "error": f"Anthropic HTTP {resp.status_code}: {err_text}",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "success": False,
                "content": "",
                "model": model,
                "provider": self.provider_name,
                "usage": {},
                "error": f"Anthropic 请求异常: {type(e).__name__}: {e}",
                "latency_ms": round(latency_ms, 1),
            }

    async def health_check(self, model: Optional[str] = None) -> Dict[str, Any]:
        """轻量级 ping。"""
        model = model or "claude-3-5-sonnet-20241022"
        resp = await self.chat(
            [{"role": "user", "content": "ping"}], model=model, max_tokens=10,
        )
        return {
            "status": "ok" if resp["success"] else "error",
            "model": model,
            "provider": self.provider_name,
            "latency_ms": resp.get("latency_ms", 0.0),
            "error": resp.get("error", ""),
        }

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Claude 不直接支持文生图 — 返回 placeholder 提示走其他 provider。"""
        return {
            "success": False,
            "error": "Claude 不支持 image generation — 走 doubao/agnes/comfyui/qwen-vl-plus",
            "provider": self.provider_name,
            "kind": "image",
            "prompt": prompt,
        }

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Claude 不直接支持文生视频。"""
        return {
            "success": False,
            "error": "Claude 不支持 video generation — 走 doubao-seedance/agnes-video",
            "provider": self.provider_name,
            "kind": "video",
            "prompt": prompt,
        }

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _placeholder(self, messages: List[Dict[str, str]], model: str, reason: str) -> Dict[str, Any]:
        """无 API key 时的占位响应 — 返回标准结构,success=False。"""
        return {
            "success": False,
            "content": f"[{self.provider_name}:{model}] placeholder — {reason}",
            "model": model,
            "provider": self.provider_name,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "error": reason,
            "latency_ms": 0.0,
        }

    def cost_estimate_usd(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> float:
        """返回 USD 成本估算。"""
        if prompt_tokens + completion_tokens <= 0:
            return 0.0
        cost = (prompt_tokens / 1_000_000) * self.PRICE_PER_M_INPUT \
             + (completion_tokens / 1_000_000) * self.PRICE_PER_M_OUTPUT
        return round(max(0.0, cost), 6)


__all__ = ["ClaudeProvider"]
