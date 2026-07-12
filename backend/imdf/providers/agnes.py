"""P20-A: AgnesProvider — free multi-modal (refactored to BaseProvider pattern).

API:      https://api.agnes.ai (placeholder / mock fallback when no key)
Auth:     Authorization: Bearer <AGNES_API_KEY>
Models:   agnes-2.0-flash (chat) | agnes-image-2.1-flash | agnes-video-2.0 | agnes-drama-1.0

This file REPLACES the P19-A1 agnes.py that used the legacy ``chat(messages)``
shape.  The class now inherits ``BaseProvider`` so it slots cleanly into the
P20+ registry alongside groq / together / fireworks / perplexity.  The
multi-modal capabilities (image / video / drama) are preserved as additional
methods on the same class — they're orthogonal to the LLM ``invoke`` surface.

Fallback: no API key -> placeholder mode (returns success=False with
``error='AGNES_API_KEY not configured'`` and ``raw.mock=True``).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .base import (
    BaseProvider,
    HealthStatus,
    InvokeParams,
    ProviderChunk,
    ProviderResponse,
)

logger = logging.getLogger(__name__)


class AgnesProvider(BaseProvider):
    provider_name = "agnes"
    family = "agnes"

    DEFAULT_BASE_URL = "https://api.agnes.ai/v1"
    CHAT_BASE_URL = "https://platform.agnes-ai.com/api/v1"
    DEFAULT_MODEL = "agnes-2.0-flash"

    # Multi-modal model catalog.  Chat models are surfaced via list_models();
    # image / video / drama have separate endpoints and live behind dedicated
    # methods on this class.
    CHAT_MODELS = [
        "agnes-2.0-flash",
        "agnes-2.0-pro",
    ]
    IMAGE_MODELS = ["agnes-image-2.1-flash"]
    VIDEO_MODELS = ["agnes-video-2.0"]
    DRAMA_MODELS = ["agnes-drama-1.0"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        # The chat path lives on the legacy endpoint; the generic provider
        # default_base_url() still reports the canonical agnes.ai URL.
        super().__init__(
            api_key=api_key or os.environ.get("AGNES_API_KEY"),
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )
        # Chat path uses a separate platform endpoint.
        self.chat_base_url = (os.environ.get("AGNES_CHAT_BASE_URL") or self.CHAT_BASE_URL).rstrip("/")

    def default_base_url(self) -> str:
        return self.DEFAULT_BASE_URL

    async def list_models(self) -> List[str]:
        """List chat models.  Multi-modal models are returned by
        ``list_all_models()`` and surfaced through the dedicated methods.
        """
        return list(self.CHAT_MODELS)

    def list_all_models(self) -> List[str]:
        """All Agnes models, including multi-modal ones."""
        return list(self.CHAT_MODELS) + list(self.IMAGE_MODELS) + \
            list(self.VIDEO_MODELS) + list(self.DRAMA_MODELS)

    def get_models(self) -> List[Dict[str, Any]]:
        """Rich model descriptors (capability tags) — used by routes/UI."""
        models: List[Dict[str, Any]] = []
        for m in self.CHAT_MODELS:
            models.append({
                "id": m, "label": m,
                "max_tokens": 8192, "capabilities": ["chat"],
                "default": m == self.DEFAULT_MODEL,
            })
        for m in self.IMAGE_MODELS:
            models.append({
                "id": m, "label": m,
                "max_tokens": 0, "capabilities": ["image"],
            })
        for m in self.VIDEO_MODELS:
            models.append({
                "id": m, "label": m,
                "max_tokens": 0, "capabilities": ["video"],
            })
        for m in self.DRAMA_MODELS:
            models.append({
                "id": m, "label": m,
                "max_tokens": 0, "capabilities": ["drama", "storyboard"],
            })
        return models

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def is_placeholder_mode(self) -> bool:
        return not self.api_key

    async def invoke(self, prompt: str, params: InvokeParams) -> ProviderResponse:
        model = params.model or self.DEFAULT_MODEL
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(model, prompt, t0, "missing_key")

        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
        }
        if params.stop:
            body["stop"] = params.stop
        body.update(params.extra or {})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.chat_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                content = ""
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                usage = data.get("usage") or {}
                return ProviderResponse(
                    success=True,
                    content=content,
                    model=model,
                    provider=self.provider_name,
                    usage={
                        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                        "completion_tokens": int(usage.get("completion_tokens") or 0),
                        "total_tokens": int(usage.get("total_tokens") or 0),
                    },
                    latency_ms=latency_ms,
                    raw=data,
                )
            err_text = (resp.text or "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"agnes_http_{resp.status_code}: {err_text}",
                latency_ms=latency_ms,
                raw={"status_code": resp.status_code},
            )
        except httpx.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"agnes_http_error: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"agnes_unexpected: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )

    async def invoke_stream(
        self, prompt: str, params: InvokeParams,
    ) -> AsyncIterator[ProviderChunk]:
        model = params.model or self.DEFAULT_MODEL
        if not self.api_key:
            yield ProviderChunk(
                delta=f"[agnes mock] streaming placeholder (no AGNES_API_KEY). prompt[:80]={prompt[:80]!r}",
                done=True,
                finish_reason="mock",
                model=model,
                provider=self.provider_name,
            )
            return

        body: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "stream": True,
        }
        body.update(params.extra or {})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.chat_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        snippet = await resp.aread()
                        yield ProviderChunk(
                            delta=f"[agnes http {resp.status_code}] {snippet[:200]!r}",
                            done=True,
                            finish_reason="error",
                            model=model,
                            provider=self.provider_name,
                        )
                        return
                    async for raw_line in resp.aiter_lines():
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            yield ProviderChunk(
                                delta="",
                                done=True,
                                finish_reason="stop",
                                model=model,
                                provider=self.provider_name,
                            )
                            return
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = obj.get("choices") or []
                        delta_text = ""
                        finish_reason = None
                        if choices:
                            delta = choices[0].get("delta") or {}
                            delta_text = delta.get("content") or ""
                            finish_reason = choices[0].get("finish_reason")
                        yield ProviderChunk(
                            delta=delta_text,
                            done=bool(finish_reason),
                            finish_reason=finish_reason,
                            model=model,
                            provider=self.provider_name,
                        )
        except httpx.HTTPError as exc:
            yield ProviderChunk(
                delta=f"[agnes stream error] {type(exc).__name__}: {exc}",
                done=True,
                finish_reason="error",
                model=model,
                provider=self.provider_name,
            )

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus(
                status="placeholder",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=0.0,
                error="AGNES_API_KEY not configured",
            )
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                resp = await client.get(
                    f"{self.chat_base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200:
                return HealthStatus(
                    status="ok",
                    provider=self.provider_name,
                    model=self.DEFAULT_MODEL,
                    latency_ms=latency_ms,
                )
            return HealthStatus(
                status="error",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=latency_ms,
                error=f"agnes_health_http_{resp.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(
                status="error",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=round((time.time() - t0) * 1000.0, 1),
                error=f"{type(exc).__name__}: {exc}",
            )

    def _placeholder(
        self, model: str, prompt: str, t0: float, reason: str,
    ) -> ProviderResponse:
        return ProviderResponse(
            success=False,
            content=f"[agnes:{model}] mock fallback — AGNES_API_KEY not configured. "
                    f"prompt[:80]={prompt[:80]!r}",
            model=model,
            provider=self.provider_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            error=reason,
            latency_ms=round((time.time() - t0) * 1000.0, 1),
            raw={"mock": True},
        )    # ─── Multi-modal extensions (image / video / drama) ─────────────────
    # These are not part of the LLM ``invoke`` contract but preserve the
    # original P19-A1 capabilities so the multi-modal routes keep working.

    async def generate_image(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "success": False,
                "error": "AGNES_API_KEY not configured — placeholder URL",
                "provider": self.provider_name,
                "kind": "image",
                "prompt": prompt,
                "placeholder_url": "https://via.placeholder.com/512.png?text=agnes-image-placeholder",
                "mock": True,
            }
        t0 = time.time()
        body = {"model": kwargs.get("model", self.IMAGE_MODELS[0]),
                "prompt": prompt, "n": kwargs.get("n", 1)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.chat_base_url}/images/generations",
                    headers={"Authorization": f"Bearer {self.api_key}",
                              "Content-Type": "application/json"},
                    json=body,
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200:
                data = resp.json()
                urls = [item["url"] for item in (data.get("data") or [])
                        if isinstance(item, dict) and item.get("url")]
                return {
                    "success": True, "provider": self.provider_name,
                    "kind": "image", "prompt": prompt, "urls": urls,
                    "model": body["model"], "latency_ms": latency_ms,
                }
            return {
                "success": False, "provider": self.provider_name,
                "kind": "image", "prompt": prompt,
                "error": f"agnes_image_http_{resp.status_code}: {resp.text[:200]}",
                "model": body["model"], "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False, "provider": self.provider_name,
                "kind": "image", "prompt": prompt,
                "error": f"agnes_image_unexpected: {type(exc).__name__}: {exc}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
            }

    async def generate_video(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "success": False,
                "error": "AGNES_API_KEY not configured — placeholder URL",
                "provider": self.provider_name,
                "kind": "video",
                "prompt": prompt,
                "placeholder_url": "https://via.placeholder.com/512.png?text=agnes-video-placeholder",
                "mock": True,
            }
        t0 = time.time()
        body = {"model": kwargs.get("model", self.VIDEO_MODELS[0]),
                "prompt": prompt, "duration": kwargs.get("duration", 5)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.chat_base_url}/videos/generations",
                    headers={"Authorization": f"Bearer {self.api_key}",
                              "Content-Type": "application/json"},
                    json=body,
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code in (200, 202):
                data = resp.json()
                return {
                    "success": True, "provider": self.provider_name,
                    "kind": "video", "prompt": prompt,
                    "task_id": data.get("id") or data.get("task_id") or "",
                    "model": body["model"], "latency_ms": latency_ms,
                }
            return {
                "success": False, "provider": self.provider_name,
                "kind": "video", "prompt": prompt,
                "error": f"agnes_video_http_{resp.status_code}: {resp.text[:200]}",
                "model": body["model"], "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False, "provider": self.provider_name,
                "kind": "video", "prompt": prompt,
                "error": f"agnes_video_unexpected: {type(exc).__name__}: {exc}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
            }

    async def generate_drama(self, theme: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "success": False,
                "error": "AGNES_API_KEY not configured — placeholder",
                "provider": self.provider_name,
                "kind": "drama",
                "theme": theme,
                "scenes": [],
                "mock": True,
            }
        t0 = time.time()
        body = {"model": self.DRAMA_MODELS[0], "theme": theme,
                "scene_count": kwargs.get("scene_count", 8)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.chat_base_url}/drama/generate",
                    headers={"Authorization": f"Bearer {self.api_key}",
                              "Content-Type": "application/json"},
                    json=body,
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True, "provider": self.provider_name,
                    "kind": "drama", "theme": theme,
                    "scenes": data.get("scenes") or [],
                    "model": self.DRAMA_MODELS[0],
                    "latency_ms": latency_ms,
                }
            return {
                "success": False, "provider": self.provider_name,
                "kind": "drama", "theme": theme,
                "error": f"agnes_drama_http_{resp.status_code}: {resp.text[:200]}",
                "model": self.DRAMA_MODELS[0],
                "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False, "provider": self.provider_name,
                "kind": "drama", "theme": theme,
                "error": f"agnes_drama_unexpected: {type(exc).__name__}: {exc}",
                "latency_ms": round((time.time() - t0) * 1000.0, 1),
            }

    # ─── cost / accounting ─────────────────────────────────────────────

    def cost_estimate_usd(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> float:
        """Agnes is free — cost is always 0."""
        return 0.0


# ─── Legacy shim (P19-A1) ────────────────────────────────────────────────────
# The original P19-A1 module exposed ``call_agnes(provider, payload, kind)``
# which is still imported by ``_invoke.py``.  We re-export a shim that
# delegates to the new class for backward compat with the existing dispatch
# chain.

async def call_agnes(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Legacy dispatcher — kept for ``_invoke.py`` backward compat.

    ``provider`` is the descriptor dict (``apiKey``, ``api_base``, etc.);
    ``payload`` is the OpenAI-shaped message list.  ``kind`` accepts
    ``chat`` (default) and routes to ``AgnesProvider.invoke()``; for image /
    video / drama we delegate to the dedicated methods.
    """
    api_key = (
        provider.get("apiKey")
        or provider.get("api_key")
        or (provider.get("config") or {}).get("apiKey")
        or (provider.get("config") or {}).get("api_key")
    )
    base_url = (
        provider.get("api_base")
        or provider.get("baseUrl")
        or (provider.get("config") or {}).get("baseUrl")
    )
    inst = AgnesProvider(api_key=api_key, base_url=base_url)
    default_model = provider.get("default_model") or AgnesProvider.DEFAULT_MODEL

    if kind in ("image",):
        prompt = (payload.get("messages") or [{}])[-1].get("content", "")
        res = await inst.generate_image(prompt)
        return {
            "ok": res.get("success", False),
            "code": "" if res.get("success") else "image_error",
            "error": res.get("error", ""),
            "data": res,
            "provider_id": provider.get("id") or "agnes",
        }
    if kind in ("video",):
        prompt = (payload.get("messages") or [{}])[-1].get("content", "")
        res = await inst.generate_video(prompt)
        return {
            "ok": res.get("success", False),
            "code": "" if res.get("success") else "video_error",
            "error": res.get("error", ""),
            "data": res,
            "provider_id": provider.get("id") or "agnes",
        }
    if kind in ("drama",):
        theme = (payload.get("messages") or [{}])[-1].get("content", "")
        res = await inst.generate_drama(theme)
        return {
            "ok": res.get("success", False),
            "code": "" if res.get("success") else "drama_error",
            "error": res.get("error", ""),
            "data": res,
            "provider_id": provider.get("id") or "agnes",
        }

    # chat (default)
    prompt = (payload.get("messages") or [{}])[-1].get("content", "")
    params = InvokeParams(
        model=payload.get("model") or default_model,
        temperature=float(payload.get("temperature", 0.7)),
        max_tokens=int(payload.get("max_tokens", 1024)),
    )
    res = await inst.invoke(prompt, params)
    if res.success:
        return {
            "ok": True,
            "data": {
                "model": res.model,
                "content": res.content,
                "usage": res.usage,
            },
            "provider_id": provider.get("id") or "agnes",
        }
    # 4xx/5xx surface as ok=False with the structured error.
    if "http_" in res.error:
        return {
            "ok": False,
            "code": "api_error",
            "error": res.error,
            "status_code": int(res.error.split("_")[2].split(":")[0]) if "_" in res.error else 0,
        }
    return {
        "ok": False,
        "code": "missing_api_key" if "missing_key" in res.error else "request_failed",
        "error": res.error,
    }


__all__ = ["AgnesProvider", "call_agnes"]