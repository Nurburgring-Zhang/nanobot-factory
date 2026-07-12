"""P19-A1: DoubaoProvider — 字节豆包,扩展了 seed-1-6 + 1-5-vision-pro。

API: https://ark.cn-beijing.volces.com/api/v3 (OpenAI 兼容)
Auth: Authorization: Bearer <DOUBAO_API_KEY 或 ARK_API_KEY>
Pricing: $0.80/$2.00 per 1M tokens

Models (扩展):
    doubao-seed-1-6          — 默认 chat (新增)
    doubao-1-5-vision-pro    — vision 多模态 (新增)
    doubao-pro-32k           — 长上下文 (已有)
    doubao-lite              — 轻量

支持 chat / image (wanx) / video (seedance) 三种能力。
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class DoubaoProvider:
    provider_name = "doubao"
    family = "doubao"
    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    ENV_VAR = "DOUBAO_API_KEY"
    ALT_ENV_VARS = ("ARK_API_KEY", "VOLCENGINE_API_KEY")

    # USD per 1M tokens (avg)
    PRICE_PER_M_INPUT = 0.80
    PRICE_PER_M_OUTPUT = 2.00

    DEFAULT_MODELS = [
        {"id": "doubao-seed-1-6-250615", "label": "豆包 Seed 1.6",
         "max_tokens": 8192, "capabilities": ["chat", "reasoning"], "default": True},
        {"id": "doubao-1-5-vision-pro-250328", "label": "豆包 1.5 Vision Pro",
         "max_tokens": 8192, "capabilities": ["chat", "vision", "image"]},
        {"id": "doubao-pro-32k-241215", "label": "豆包 Pro 32K",
         "max_tokens": 32768, "capabilities": ["chat"]},
        {"id": "doubao-lite-32k-241215", "label": "豆包 Lite 32K",
         "max_tokens": 32768, "capabilities": ["chat"]},
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
        model = model or "doubao-seed-1-6-250615"
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(messages, model, "DOUBAO_API_KEY 未配置")

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
                "error": f"Doubao HTTP {resp.status_code}: {err_text}",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {
                "success": False, "content": "", "model": model,
                "provider": self.provider_name, "usage": {},
                "error": f"Doubao 异常: {type(e).__name__}: {e}",
                "latency_ms": round(latency_ms, 1),
            }

    async def health_check(self, model: Optional[str] = None) -> Dict[str, Any]:
        model = model or "doubao-seed-1-6-250615"
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
        """Doubao 文生图 — 走 Seedream (doubao-seedream-4-0)."""
        if not self.api_key:
            return {
                "success": False,
                "error": "DOUBAO_API_KEY 未配置",
                "provider": self.provider_name,
                "kind": "image",
                "prompt": prompt,
                "placeholder_url": "https://via.placeholder.com/512.png?text=doubao-mock",
            }
        t0 = time.time()
        model = kwargs.get("model", "doubao-seedream-4-0-250828")
        body = {
            "model": model,
            "prompt": prompt,
            "n": kwargs.get("n", 1),
            "size": kwargs.get("size", "1024x1024"),
        }
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{self.base_url}/images/generations",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = (time.time() - t0) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                data_list = data.get("data") or []
                urls = []
                for item in data_list:
                    if isinstance(item, dict):
                        if item.get("url"):
                            urls.append(item["url"])
                        elif item.get("b64_json"):
                            urls.append("data:image/png;base64," + item["b64_json"])
                return {
                    "success": True, "provider": self.provider_name,
                    "kind": "image", "prompt": prompt, "urls": urls,
                    "model": model, "latency_ms": round(latency_ms, 1),
                }
            return {
                "success": False, "provider": self.provider_name,
                "kind": "image", "prompt": prompt,
                "error": f"Doubao image HTTP {resp.status_code}: {resp.text[:200]}",
                "model": model, "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            return {
                "success": False, "provider": self.provider_name,
                "kind": "image", "prompt": prompt,
                "error": f"Doubao image 异常: {type(e).__name__}: {e}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
            }

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Doubao 视频生成 — 走 Seedance async submit。"""
        if not self.api_key:
            return {
                "success": False,
                "error": "DOUBAO_API_KEY 未配置",
                "provider": self.provider_name,
                "kind": "video",
                "prompt": prompt,
                "placeholder_url": "https://via.placeholder.com/512.png?text=doubao-video-mock",
            }
        t0 = time.time()
        model = kwargs.get("model", "doubao-seedance-2-0-260128")
        body = {
            "model": model,
            "content": [{"type": "text", "text": prompt}],
            "parameters": {"ratio": kwargs.get("ratio", "16:9"),
                            "duration": kwargs.get("duration", 5),
                            "resolution": kwargs.get("resolution", "720p")},
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/contents/generations/video",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = (time.time() - t0) * 1000.0
            if resp.status_code in (200, 202):
                data = resp.json()
                task_id = data.get("id") or data.get("task_id") or ""
                return {
                    "success": True, "provider": self.provider_name,
                    "kind": "video", "prompt": prompt, "task_id": task_id,
                    "model": model, "latency_ms": round(latency_ms, 1),
                    "raw": data,
                }
            return {
                "success": False, "provider": self.provider_name,
                "kind": "video", "prompt": prompt,
                "error": f"Doubao video HTTP {resp.status_code}: {resp.text[:200]}",
                "model": model, "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            return {
                "success": False, "provider": self.provider_name,
                "kind": "video", "prompt": prompt,
                "error": f"Doubao video 异常: {type(e).__name__}: {e}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
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


# 旧代码里的 DoubaoExtendedProvider 是 DoubaoProvider 的别名,保持向后兼容
DoubaoExtendedProvider = DoubaoProvider


__all__ = ["DoubaoProvider", "DoubaoExtendedProvider"]
