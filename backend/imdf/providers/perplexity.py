"""P20-A: PerplexityProvider — online LLMs with citations."""
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


class PerplexityProvider(BaseProvider):
    provider_name = "perplexity"
    family = "perplexity"

    DEFAULT_BASE_URL = "https://api.perplexity.ai"
    DEFAULT_MODEL = "llama-3.1-sonar-small-128k-online"

    # Search-augmented "online" models plus offline variants.
    DEFAULT_MODELS = [
        "llama-3.1-sonar-small-128k-online",
        "llama-3.1-sonar-large-128k-online",
        "llama-3.1-sonar-huge-128k-online",
        "llama-3.1-sonar-small-128k-chat",
        "llama-3.1-sonar-large-128k-chat",
        "llama-3.1-8b-instruct",
        "llama-3.1-70b-instruct",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            api_key=api_key or os.environ.get("PERPLEXITY_API_KEY"),
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
            "messages": [
                {"role": "system", "content": "Be precise and concise. "
                 "Cite sources inline as [1], [2]."},
                {"role": "user", "content": prompt},
            ],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
        }
        if params.stop:
            body["stop"] = params.stop

        # Perplexity-specific knobs surfaced via InvokeParams.extra:
        #   - return_citations / return_related_questions (bool)
        #   - search_domain_filter (list[str])  e.g. ["-reddit.com"]
        #   - search_recency_filter ("week", "month", "year")
        #   - search_mode ("academic", "web", "news")
        if params.extra:
            for key in ("return_citations", "return_related_questions",
                        "search_domain_filter", "search_recency_filter",
                        "search_mode", "frequency_penalty", "presence_penalty"):
                if key in params.extra:
                    body[key] = params.extra[key]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
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
                error=f"perplexity_http_error: {type(exc).__name__}: {exc}",
                latency_ms=round((time.time() - t0) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"perplexity_unexpected: {type(exc).__name__}: {exc}",
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
            raw = dict(data)
            # Perplexity puts citations / search_results at the top level.
            citations = data.get("citations") or []
            search_results = data.get("search_results") or []
            related = data.get("related_questions") or []
            if citations:
                raw["citations"] = citations
            if search_results:
                raw["search_results"] = search_results
            if related:
                raw["related_questions"] = related
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
            error=f"perplexity_http_{resp.status_code}: {err_text}",
            latency_ms=latency_ms,
            raw={"status_code": resp.status_code},
        )

    async def invoke_stream(
        self, prompt: str, params: InvokeParams,
    ) -> AsyncIterator[ProviderChunk]:
        model = params.model or self.DEFAULT_MODEL
        if not self.api_key:
            yield ProviderChunk(
                delta="[perplexity mock] streaming placeholder (no PERPLEXITY_API_KEY)",
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
            for key in ("return_citations", "search_domain_filter",
                        "search_recency_filter", "search_mode"):
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
                        "Accept": "text/event-stream",
                    },
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        snippet = await resp.aread()
                        yield ProviderChunk(
                            delta=f"[perplexity http {resp.status_code}] {snippet[:200]!r}",
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
                delta=f"[perplexity stream error] {type(exc).__name__}: {exc}",
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
                error="PERPLEXITY_API_KEY not configured",
            )
        try:
            # Perplexity doesn't expose /models. Use a tiny non-streaming call.
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.DEFAULT_MODEL,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
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
                error=f"perplexity_health_http_{resp.status_code}",
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
            content=f"[perplexity:{model}] mock fallback — PERPLEXITY_API_KEY not configured. "
                    f"prompt[:80]={prompt[:80]!r}",
            model=model,
            provider=self.provider_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            error=reason,
            latency_ms=round((time.time() - t0) * 1000.0, 1),
            raw={"mock": True},
        )


__all__ = ["PerplexityProvider"]