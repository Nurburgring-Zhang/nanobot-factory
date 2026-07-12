"""P19-A1: DeepSeek Provider — deepseek-chat + deepseek-coder.

API: https://api.deepseek.com/v1/chat/completions (OpenAI 兼容)
Auth: Authorization: Bearer <DEEPSEEK_API_KEY>
Pricing: $0.14/$0.28 per 1M tokens

Models:
    deepseek-chat       — 默认 chat
    deepseek-coder      — 代码专用

Fallback: 无 key → placeholder 响应 (开发 / CI 友好)
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    provider_name = "deepseek"
    family = "deepseek"
    BASE_URL = "https://api.deepseek.com/v1"
    ENV_VAR = "DEEPSEEK_API_KEY"

    # USD per 1M tokens
    PRICE_PER_M_INPUT = 0.14
    PRICE_PER_M_OUTPUT = 0.28

    DEFAULT_MODELS = [
        {"id": "deepseek-chat", "label": "DeepSeek Chat",
         "max_tokens": 8192, "capabilities": ["chat"], "default": True},
        {"id": "deepseek-coder", "label": "DeepSeek Coder",
         "max_tokens": 8192, "capabilities": ["chat", "code"]},
    ]

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or os.environ.get(self.ENV_VAR, "")).strip()
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    def get_models(self) -> List[Dict[str, Any]]:
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
        model = model or "deepseek-chat"
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(messages, model, "DEEPSEEK_API_KEY 未配置")

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = (time.time() - t0) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                content = ""
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                usage = data.get("usage", {}) or {}
                usage_norm = {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens")
                                        or (int(usage.get("prompt_tokens") or 0)
                                            + int(usage.get("completion_tokens") or 0))),
                }
                return {
                    "success": True, "content": content, "model": model,
                    "provider": self.provider_name, "usage": usage_norm,
                    "error": "", "latency_ms": round(latency_ms, 1),
                }
            err_text = resp.text[:500] if hasattr(resp, "text") else ""
            return {
                "success": False, "content": "", "model": model,
                "provider": self.provider_name, "usage": {},
                "error": f"DeepSeek HTTP {resp.status_code}: {err_text}",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "success": False, "content": "", "model": model,
                "provider": self.provider_name, "usage": {},
                "error": f"DeepSeek 异常: {type(e).__name__}: {e}",
                "latency_ms": round(latency_ms, 1),
            }

    async def health_check(self, model: Optional[str] = None) -> Dict[str, Any]:
        model = model or "deepseek-chat"
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
        """DeepSeek 无文生图 — 占位返回。"""
        return {
            "success": False,
            "error": "DeepSeek 不支持 image generation — 走 qwen-vl-plus/doubao-seedream",
            "provider": self.provider_name,
            "kind": "image",
            "prompt": prompt,
        }

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "DeepSeek 不支持 video generation — 走 doubao-seedance/agnes-video",
            "provider": self.provider_name,
            "kind": "video",
            "prompt": prompt,
        }

    def _placeholder(self, messages: List[Dict[str, str]], model: str, reason: str) -> Dict[str, Any]:
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
        if prompt_tokens + completion_tokens <= 0:
            return 0.0
        cost = (prompt_tokens / 1_000_000) * self.PRICE_PER_M_INPUT \
             + (completion_tokens / 1_000_000) * self.PRICE_PER_M_OUTPUT
        return round(max(0.0, cost), 6)


__all__ = ["DeepSeekProvider"]
