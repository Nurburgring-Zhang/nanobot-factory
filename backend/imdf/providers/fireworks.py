"""P20-A: FireworksProvider — fast inference + function calling + JSON mode."""
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


class FireworksProvider(BaseProvider):
    provider_name = "fireworks"
    family = "fireworks"
    DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"
    DEFAULT_MODEL = "accounts/fireworks/models/llama-v3p1-70b-instruct"

    DEFAULT_MODELS = [
        "accounts/fireworks/models/llama-v3p1-405b-instruct",
        "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "accounts/fireworks/models/mixtral-8x7b-instruct",
        "accounts/fireworks/models/mistral-7b-instruct-v0p2",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
        "accounts/fireworks/models/deepseek-v3",
        "accounts/fireworks/models/llama-v3p1-70b-instruct-function-calling",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("FIREWORKS_API_KEY"),
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    def default_base_url(self) -> str:
        return self.DEFAULT_BASE_URL

    async def list_models(self) -> List[str]:
        return list(self.DEFAULT_MODELS)

    async def invoke(self, prompt: str, params: InvokeParams) -> ProviderResponse:
        model = params.model or self.DEFAULT_MODEL
        t0 = time.time()
        if not self.api_key:
            return self._placeholder(model, prompt, t0, "missing_key")

        body: Dict[str, Any] = {
            "model": model,
            "messages":[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
        }
        if params.stop:
            body["stop"] = params.stop

        # Fireworks-specific: function-calling + JSON mode pass-through.
        # ``InvokeParams.extra`` may carry ``tools`` / ``response_format`` /
        # ``seed``.  Copy them into the body if present.
        if params.extra:
            for key in ("tools", "tool_choice", "response_format", "seed",
                        "frequency_penalty", "presence_penalty"):
                if key in params.extra:
                    body[key] = params.extra[key]

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
                error=f"fireworks_http_error: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"fireworks_unexpected: {type(exc).__name__}: {exc}",
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
            tool_calls: List[Dict[str, Any]] = []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
                if isinstance(msg.get("tool_calls"), list):
                    tool_calls = msg["tool_calls"]
            usage = data.get("usage") or {}
            raw = dict(data)
            if tool_calls:
                raw["tool_calls"] = tool_calls
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
                raw=raw,
            )
        err_text = (resp.text or "")[:500]
        return ProviderResponse(
            success=False,
            provider=self.provider_name,
            model=model,
            error=f"fireworks_http_{resp.status_code}: {err_text}",
            latency_ms=latency_ms,
            raw={"status_code": resp.status_code},
        )

    async def invoke_stream(
        self, prompt: str, params: InvokeParams,
    ) -> AsyncIterator[ProviderChunk]:
        model = params.model or self.DEFAULT_MODEL
        if not self.api_key:
            yield ProviderChunk(
                delta="[fireworks mock] streaming placeholder (no FIREWORKS_API_KEY)",
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
        if params.extra:
            for key in ("tools", "tool_choice", "response_format", "seed"):
                if key in params.extra:
                    body[key] = params.extra[key]

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
                        snippet = await resp.aread()
                        yield ProviderChunk(
                            delta=f"[fireworks http {resp.status_code}] {snippet[:200]!r}",
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
                delta=f"[fireworks stream error] {type(exc).__name__}: {exc}",
                done=True,
                finish_reason="error",
                model=model,
                provider=self.provider_name,
            )

    async def health_check(self) -> HealthStatus:
        t0 = time.time()
        if not self.api_key:
            return HealthStatus(
                status="placeholder",
                provider=self.provider_name,
                model=self.DEFAULT_MODEL,
                latency_ms=0.0,
                error="FIREWORKS_API_KEY not configured",
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
                error=f"fireworks_health_http_{resp.status_code}",
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
            content=f"[fireworks:{model}] mock fallback — FIREWORKS_API_KEY not configured. "
                    f"prompt[:80]={prompt[:80]!r}",
            model=model,
            provider=self.provider_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            error=reason,
            latency_ms=round((time.time() - t0) * 1000.0, 1),
            raw={"mock": True},
        )


__all__ = ["FireworksProvider"]