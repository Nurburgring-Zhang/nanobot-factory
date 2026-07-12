"""P20-A: GroqProvider — ultra-fast LPU inference.

API:      https://api.groq.com/openai/v1  (OpenAI-compatible)
Auth:     Authorization: Bearer <GROQ_API_KEY>
Models:   llama-3.1-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768,
          llama-3.2-90b-vision-preview, whisper-large-v3-turbo (transcription)

Groq is OpenAI-compatible so we speak the same ``/chat/completions`` wire format
as every other OpenAI-shaped provider in the registry.  The differentiating
traits are (a) the LPU-class latency (p50 < 300ms) and (b) ``reasoning_format``
for select Llama models.

Reference: https://console.groq.com/docs/api-reference
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


class GroqProvider(BaseProvider):
    provider_name = "groq"
    family = "groq"

    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "llama-3.1-70b-versatile"

    # Curated chat models. Vision / audio live behind separate endpoints and
    # are out of scope for the LLM ``invoke`` surface.
    DEFAULT_MODELS = [
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.2-90b-vision-preview",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("GROQ_API_KEY"),
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    def default_base_url(self) -> str:
        return self.DEFAULT_BASE_URL

    async def list_models(self) -> List[str]:
        """Return the curated chat model catalog.

        We could hit ``GET /models`` but Groq's catalog includes preview /
        decommissioned entries; the curated list is what we actually want to
        offer to the engine router.
        """
        return list(self.DEFAULT_MODELS)

    # ─── invoke ─────────────────────────────────────────────────────────────

    async def invoke(self, prompt: str, params: InvokeParams) -> ProviderResponse:
        model = params.model or self.DEFAULT_MODEL
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(model, prompt, t0, reason="missing_key")

        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "stream": False,
        }
        if params.stop:
            body["stop"] = params.stop
        body.update(params.extra or {})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            latency_ms = round((time.time() - t0) * 1000.0, 1)
            return self._parse_chat_response(resp, model, latency_ms)
        except httpx.HTTPError as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"groq_http_error: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"groq_unexpected: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )

    def _parse_chat_response(
        self,
        resp: httpx.Response,
        model: str,
        latency_ms: float,
    ) -> ProviderResponse:
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
        # Surface 401/429/500 etc. as structured failure (caller decides retry).
        err_text = (resp.text or "")[:500]
        return ProviderResponse(
            success=False,
            provider=self.provider_name,
            model=model,
            error=f"groq_http_{resp.status_code}: {err_text}",
            latency_ms=latency_ms,
            raw={"status_code": resp.status_code},
        )

    # ─── streaming ─────────────────────────────────────────────────────────

    async def invoke_stream(
        self, prompt: str, params: InvokeParams,
    ) -> AsyncIterator[ProviderChunk]:
        """Stream via SSE (server-sent events) — Groq honors ``stream=true``.

        We parse the OpenAI delta chunks (``{"choices":[{"delta":{...}}]}``) line
        by line.  If we get back a non-200 status we yield one error chunk and
        stop — the engine router will see ``finish_reason='error'``.
        """
        model = params.model or self.DEFAULT_MODEL
        if not self.api_key:
            yield ProviderChunk(
                delta="[groq mock] streaming placeholder (no GROQ_API_KEY)",
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
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        # drain a snippet for diagnostics
                        snippet = await resp.aread()
                        yield ProviderChunk(
                            delta=f"[groq http {resp.status_code}] {snippet[:200]!r}",
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
                delta=f"[groq stream error] {type(exc).__name__}: {exc}",
                done=True,
                finish_reason="error",
                model=model,
                provider=self.provider_name,
            )

    # ─── health ─────────────────────────────────────────────────────────────

    async def health_check(self) -> HealthStatus:
        t0 = time.time()
        if not self.api_key:
            return HealthStatus(
                status="placeholder",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=0.0,
                error="GROQ_API_KEY not configured",
            )
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
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
                error=f"groq_health_http_{resp.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(
                status="error",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=round((time.time() - t0) * 1000.0, 1),
                error=f"{type(exc).__name__}: {exc}",
            )

    # ─── helpers ────────────────────────────────────────────────────────────

    def _placeholder(
        self, model: str, prompt: str, t0: float, reason: str,
    ) -> ProviderResponse:
        return ProviderResponse(
            success=False,
            content=f"[groq:{model}] mock fallback — GROQ_API_KEY not configured. "
                    f"prompt[:80]={prompt[:80]!r}",
            model=model,
            provider=self.provider_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            error=reason,
            latency_ms=round((time.time() - t0) * 1000.0, 1),
            raw={"mock": True},
        )


__all__ = ["GroqProvider"]