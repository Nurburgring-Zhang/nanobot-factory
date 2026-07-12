"""P20-B / LocalProvider — fully offline base model via llama.cpp HTTP server.

llama.cpp ships with an embedded HTTP server (``llama-server`` /
``server``) exposing an OpenAI-compatible ``/v1/chat/completions`` /
``/v1/completions`` API. This provider talks to that locally running server
so the rest of the platform has a free-of-charge, offline-fallback model —
often a Llama-3-8B-Instruct Q4_K_M GGUF or similar.

The expected runtime shape::

    ┌────────────────────────────────────────────┐
    │ llama-server -m llama-3-8b-instruct.Q4_K_M.gguf \\
    │            --port 8080 --host 127.0.0.1       │
    │            --ctx-size 4096                    │
    └────────────────────────────────────────────┘
                        ▲
                        │ /v1/chat/completions
                ┌───────┴───────┐
                │ LocalProvider │   ← this file
                └───────────────┘

If the server is not running (default ``http://127.0.0.1:8080``), the
provider returns a clear ``is_placeholder=True`` response and never throws.

Public interface (matches P20-A contract): see ``_provider_base``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

import httpx

from ._provider_base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


LLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
ENV_VAR_BASE = "LLAMA_BASE_URL"

DEFAULT_MODEL = "llama-3-8b-instruct"

DEFAULT_MODELS: List[str] = [
    "llama-3-8b-instruct",
    "llama-3.1-8b-instruct",
    "llama-3.2-3b-instruct",
    "qwen2.5-7b-instruct",
    "mistral-7b-instruct",
    "phi-3-mini",
    "gemma-2-9b-instruct",
]


# ─── Provider ────────────────────────────────────────────────────────────────
class LocalProvider(BaseProvider):
    """Local llama.cpp / ollama-style offline provider (no external network)."""

    provider_name = "local"
    family = "local"

    def __init__(
        self,
        api_key: Optional[str] = None,        # accepted for symmetry, unused
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ):
        super().__init__(
            api_key=api_key or "",
            base_url=(base_url or os.environ.get(ENV_VAR_BASE) or LLAMA_DEFAULT_BASE_URL),
            timeout=timeout,
        )

    @classmethod
    def _default_base_url(cls) -> str:
        return LLAMA_DEFAULT_BASE_URL

    # ── Auth override: local provider is fully offline, no key required ──
    def has_credentials(self) -> bool:
        """Local provider has no key requirement; always True.

        This unlocks ``invoke()`` regardless of whether ``api_key`` was set,
        which matches the offline-friendly contract documented in the class
        docstring.
        """
        return True

    # ── BaseProvider impl ──────────────────────────────────────────────
    async def list_models(self) -> List[str]:
        """Return the curated offline model catalogue.

        To discover models actually loaded by llama-server at runtime, use
        :meth:`list_models_remote`. Falls back to the static list when the
        server is unreachable.
        """
        return list(DEFAULT_MODELS)

    async def list_models_remote(self) -> List[str]:
        """Fetch ``/v1/models`` from llama-server (OpenAI-compatible)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/models")
            if resp.status_code != 200:
                return list(DEFAULT_MODELS)
            payload = resp.json() if hasattr(resp, "json") else {}
            items = payload.get("data") or []
            out: List[str] = []
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    out.append(str(it["id"]))
            return out or list(DEFAULT_MODELS)
        except Exception:
            return list(DEFAULT_MODELS)

    async def invoke(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Send prompt to local llama-server via OpenAI-compatible endpoint.

        ``params`` keys map directly to the OpenAI schema:
            model (str)         — default ``llama-3-8b-instruct``
            messages (list)     — [{"role":"user","content":prompt}, ...]
            temperature (float)
            max_tokens (int)
            stream (bool)       — passed through to ``stream_chunks``
        If the server is unreachable, returns ``is_placeholder=True``.
        """
        params = dict(params or {})
        messages: List[Dict[str, str]] = list(params.get("messages") or [])
        if not messages:
            # If a free-form prompt was passed, build a 1-message transcript
            if prompt:
                messages = [{"role": "user", "content": prompt}]
            else:
                return ProviderResponse(
                    success=False,
                    provider=self.provider_name,
                    error="LocalProvider.invoke 需要 prompt 或 messages",
                    error_code="missing_prompt",
                )

        body: Dict[str, Any] = {
            "model": str(
                params.get("model") or kwargs.get("model") or DEFAULT_MODEL,
            ),
            "messages": messages,
            "temperature": float(params.get("temperature", 0.7)),
            "max_tokens": int(params.get("max_tokens", 1024)),
            "stream": False,
        }
        # forward extras
        for k, v in params.items():
            if k in ("model", "messages", "temperature", "max_tokens", "stream"):
                continue
            body[k] = v

        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=body["model"],
                status="unreachable",
                is_placeholder=True,
                error=(
                    f"local llama-server 不可达 ({self.base_url}): "
                    f"{type(exc).__name__}: {exc}"
                ),
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
                raw={"base_url": self.base_url},
            )

        latency_ms = self._latency_ms(t0)
        if resp.status_code == 401:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=body["model"],
                error="local llama-server HTTP 401: 鉴权失败 (本地通常无鉴权)",
                error_code=str(resp.status_code),
                latency_ms=latency_ms,
            )
        if resp.status_code == 429:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=body["model"],
                error="local llama-server HTTP 429: rate-limit",
                error_code=str(resp.status_code),
                latency_ms=latency_ms,
            )
        if resp.status_code >= 500:
            err_text = getattr(resp, "text", "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=body["model"],
                error=f"local llama-server HTTP {resp.status_code}: {err_text}",
                error_code=str(resp.status_code),
                latency_ms=latency_ms,
            )
        if resp.status_code != 200:
            err_text = getattr(resp, "text", "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=body["model"],
                error=f"local HTTP {resp.status_code}: {err_text}",
                error_code=str(resp.status_code),
                latency_ms=latency_ms,
            )

        try:
            payload = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            payload = {}

        # OpenAI-shape: ``choices[].message.content`` + ``usage``
        content = ""
        try:
            choices = payload.get("choices") or []
            if choices:
                content = choices[0].get("message", {}).get("content", "") or ""
        except Exception:
            content = ""
        usage = payload.get("usage") or {}
        usage_norm = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(
                usage.get("total_tokens")
                or (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)),
            ),
        }
        return ProviderResponse(
            success=True,
            provider=self.provider_name,
            model=body["model"],
            content=content,
            status="succeeded",
            latency_ms=latency_ms,
            usage=usage_norm,
            raw=payload,
        )

    async def health_check(self) -> ProviderResponse:
        """Verify local llama-server reachability via ``/v1/models``."""
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/models")
            ok = resp.status_code == 200
            models = []
            if ok:
                payload = resp.json() if hasattr(resp, "json") else {}
                for it in payload.get("data") or []:
                    if isinstance(it, dict) and it.get("id"):
                        models.append(str(it["id"]))
            return ProviderResponse(
                success=ok,
                provider=self.provider_name,
                status="ok" if ok else "error",
                latency_ms=self._latency_ms(t0),
                raw={"models": models},
                error="" if ok else f"local /v1/models HTTP {resp.status_code}",
                error_code="" if ok else str(resp.status_code),
            )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                status="unreachable",
                error=f"local server unreachable: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
                raw={"base_url": self.base_url},
            )

    # ── Streaming override ─────────────────────────────────────────────
    async def stream_chunks(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """SSE streaming via llama-server (when ``stream=True``)."""
        params = dict(params or {})
        params.setdefault("stream", True)
        # Build body the same as invoke but stream=True
        messages = list(params.get("messages") or [{"role": "user", "content": prompt}])
        body: Dict[str, Any] = {
            "model": str(params.get("model") or kwargs.get("model") or DEFAULT_MODEL),
            "messages": messages,
            "temperature": float(params.get("temperature", 0.7)),
            "max_tokens": int(params.get("max_tokens", 1024)),
            "stream": True,
        }
        for k, v in params.items():
            if k in ("model", "messages", "temperature", "max_tokens", "stream"):
                continue
            body[k] = v
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            try:
                                obj = json.loads(data)
                            except Exception:
                                continue
                            choices = obj.get("choices") or []
                            if choices:
                                delta = (
                                    choices[0].get("delta")
                                    or {}
                                ).get("content") or ""
                                if delta:
                                    yield delta
        except Exception as exc:
            logger.debug("local stream failed: %s", exc)
            return


__all__ = ["LocalProvider"]
