"""P19-A1: Qwen (阿里 DashScope) Provider — qwen-plus / qwen-max / qwen-vl-plus.

API: https://dashscope.aliyuncs.com/compatible-mode/v1 (OpenAI 兼容)
Auth: Authorization: Bearer <QWEN_API_KEY 或 DASHSCOPE_API_KEY>
Pricing: $0.40/$1.20 per 1M tokens (qwen-plus)

Models:
    qwen-plus         — 默认 chat
    qwen-max          — 强推理
    qwen-vl-plus      — 多模态视觉 (支持 generate_image via VL)

Fallback: 无 key → placeholder 响应
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class QwenProvider:
    provider_name = "qwen"
    family = "qwen"
    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # 兼容多个常用环境变量名
    ENV_VAR = "QWEN_API_KEY"
    ALT_ENV_VARS = ("DASHSCOPE_API_KEY", "ALIYUN_DASHSCOPE_API_KEY")

    # USD per 1M tokens
    PRICE_PER_M_INPUT = 0.40
    PRICE_PER_M_OUTPUT = 1.20

    DEFAULT_MODELS = [
        {"id": "qwen-plus", "label": "Qwen Plus",
         "max_tokens": 8192, "capabilities": ["chat"], "default": True},
        {"id": "qwen-max", "label": "Qwen Max",
         "max_tokens": 8192, "capabilities": ["chat", "reasoning"]},
        {"id": "qwen-vl-plus", "label": "Qwen VL Plus",
         "max_tokens": 8192, "capabilities": ["chat", "vision", "image"]},
    ]

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = (api_key or self._load_key()).strip()
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    @classmethod
    def _load_key(cls) -> str:
        for var in (cls.ENV_VAR, *cls.ALT_ENV_VARS):
            val = os.environ.get(var, "").strip()
            if val:
                return val
        return ""

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
        model = model or "qwen-plus"
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(messages, model, "QWEN_API_KEY / DASHSCOPE_API_KEY 未配置")

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
                "error": f"Qwen HTTP {resp.status_code}: {err_text}",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "success": False, "content": "", "model": model,
                "provider": self.provider_name, "usage": {},
                "error": f"Qwen 异常: {type(e).__name__}: {e}",
                "latency_ms": round(latency_ms, 1),
            }

    async def health_check(self, model: Optional[str] = None) -> Dict[str, Any]:
        model = model or "qwen-plus"
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
        """Qwen-VL-Plus 支持文生图(走特殊 endpoint)。"""
        if not self.api_key:
            return {
                "success": False,
                "error": "QWEN_API_KEY 未配置 — 走占位",
                "provider": self.provider_name,
                "kind": "image",
                "prompt": prompt,
                "placeholder_url": "https://via.placeholder.com/512.png?text=qwen-mock",
            }
        # 真接入 DashScope 的 wanx/image 生成端点
        t0 = time.time()
        body = {
            "model": kwargs.get("model", "wanx-v1"),
            "input": {"prompt": prompt},
            "parameters": {"style": kwargs.get("style", "<auto>"),
                            "size": kwargs.get("size", "1024*1024"),
                            "n": kwargs.get("n", 1)},
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = (time.time() - t0) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("output", {}).get("results") or []
                urls = [r.get("url") for r in results if r.get("url")]
                return {
                    "success": True,
                    "provider": self.provider_name,
                    "kind": "image",
                    "prompt": prompt,
                    "urls": urls,
                    "latency_ms": round(latency_ms, 1),
                    "model": body["model"],
                }
            return {
                "success": False,
                "provider": self.provider_name,
                "kind": "image",
                "prompt": prompt,
                "error": f"DashScope image HTTP {resp.status_code}: {resp.text[:200]}",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            return {
                "success": False,
                "provider": self.provider_name,
                "kind": "image",
                "prompt": prompt,
                "error": f"DashScope image 异常: {type(e).__name__}: {e}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
            }

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Qwen 文本端不直接支持文生视频。"""
        return {
            "success": False,
            "error": "Qwen 不直接支持 video generation — 走 doubao-seedance/agnes-video",
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


__all__ = ["QwenProvider"]
