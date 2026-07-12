"""P19-A2: Moonshot Kimi provider adapter (OpenAI-compatible).

Provider family: kimi
Protocol: OpenAI compatible (``/v1/chat/completions``)
Auth: Bearer API key
Default models:
  - kimi-k2.7         (Kimi K2.7 — new flagship, 2026)
  - moonshot-v1-128k  (legacy long-context 128k model)
Pricing (USD per 1M tokens):
  - input:  $0.30
  - output: $0.90

Endpoint:
  POST ``{api_base}/chat/completions``

Supports both Kimi K2.x and the moonshot-v1 family. The endpoint is a
strict OpenAI drop-in so we reuse the engines ``call_openai_compatible``
plumbing under the hood via ``OpenAICompatProvider``.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_API_BASE = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.7"

# USD per 1K tokens (input, output) — registry stores per-1K.
PRICE_INPUT_USD_PER_1K = 0.0003
PRICE_OUTPUT_USD_PER_1K = 0.0009

DEFAULT_CHAT_MODELS: List[str] = [
    "kimi-k2.7",
    "moonshot-v1-128k",
    "moonshot-v1-32k",
    "moonshot-v1-8k",
]

DEFAULT_VISION_MODELS: List[str] = [
    "kimi-k2.7-vision",
    "moonshot-v1-8k-vision-preview",
]


@dataclass
class KimiProvider:
    """In-memory descriptor for a Kimi registration."""
    id: str = "kimi"
    name: str = "月之暗面 Kimi"
    family: str = "kimi"
    default_model: str = DEFAULT_MODEL
    api_base: str = DEFAULT_API_BASE
    price_per_1k_input: float = PRICE_INPUT_USD_PER_1K
    price_per_1k_output: float = PRICE_OUTPUT_USD_PER_1K
    quota_per_minute: int = 60
    latency_p50_ms: int = 700
    latency_p99_ms: int = 2000
    trust_level: str = "verified"
    status: str = "active"
    config: Dict[str, Any] = field(default_factory=lambda: {
        "protocol": "openai-compatible",
        "auth": "bearer",
        "models": list(DEFAULT_CHAT_MODELS),
        "vision_models": list(DEFAULT_VISION_MODELS),
        "supports_streaming": True,
        "supports_vision": True,
        "max_context_tokens": 128000,
    })
    chat_models: List[str] = field(default_factory=lambda: list(DEFAULT_CHAT_MODELS))

    def to_registry_kwargs(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "family": self.family,
            "default_model": self.default_model,
            "api_base": self.api_base,
            "price_per_1k_input": self.price_per_1k_input,
            "price_per_1k_output": self.price_per_1k_output,
            "quota_per_minute": self.quota_per_minute,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "trust_level": self.trust_level,
            "status": self.status,
            "config": dict(self.config),
        }


def _resolve_api_key(api_key: Optional[str] = None) -> str:
    if api_key:
        return str(api_key).strip()
    env = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY") or ""
    return env.strip()


def _resolve_model(model: Optional[str], default_model: str) -> str:
    m = str(model or "").strip()
    return m or default_model


async def call_kimi(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Kimi call — delegates to ``call_openai_compatible`` if available,
    otherwise falls back to a local httpx implementation so the module
    is usable in isolation.
    """
    if not provider:
        return {"ok": False, "code": "missing_provider", "error": "provider descriptor is empty"}
    api_base = (provider.get("api_base") or provider.get("baseUrl") or DEFAULT_API_BASE).rstrip("/")
    cfg = provider.get("config") or {}
    api_key = (
        provider.get("apiKey")
        or provider.get("api_key")
        or cfg.get("apiKey")
        or cfg.get("api_key")
        or _resolve_api_key()
    )
    if not api_key:
        return {"ok": False, "code": "missing_api_key", "error": "Kimi apiKey not configured"}
    default_model = provider.get("default_model") or cfg.get("defaultModel") or DEFAULT_MODEL
    model = _resolve_model(payload.get("model"), default_model)

    # Prefer the shared OpenAI-compatible helper so behaviour stays uniform.
    openai_provider = {
        "id": provider.get("id") or "kimi",
        "protocol": "openai-compatible",
        "baseUrl": api_base,
        "apiKey": api_key,
        "enabled": True,
        "chatModels": cfg.get("models", DEFAULT_CHAT_MODELS),
    }
    if kind == "image":
        return {"ok": False, "code": "unsupported_kind",
                "error": "Kimi is a chat-only provider (no image generation endpoint)"}
    if kind == "video":
        return {"ok": False, "code": "unsupported_kind",
                "error": "Kimi is a chat-only provider (no video generation endpoint)"}

    try:
        from engines import provider_registry as pr  # type: ignore
        return await pr.call_openai_compatible(
            openai_provider,
            {"model": model, **payload},
            kind="chat",
        )
    except Exception:
        # Fallback: in-process httpx call.
        try:
            import httpx
        except Exception as e:
            return {"ok": False, "code": "missing_dependency",
                    "error": f"httpx not available and engines.provider_registry unreachable: {e}"}
        endpoint = f"{api_base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
        if "temperature" in payload:
            body["temperature"] = float(payload["temperature"])
        if "max_tokens" in payload:
            body["max_tokens"] = int(payload["max_tokens"])
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_val) as client:
                resp = await client.post(endpoint, json=body, headers=headers)
            if resp.status_code >= 400:
                return {"ok": False, "code": "api_error",
                        "error": str(resp.text)[:2000],
                        "status_code": resp.status_code}
            return {"ok": True, "data": resp.json(),
                    "provider_id": provider.get("id") or "kimi"}
        except Exception as e:
            return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}


def compute_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    price_in: float = PRICE_INPUT_USD_PER_1K,
    price_out: float = PRICE_OUTPUT_USD_PER_1K,
) -> float:
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    return round(
        (prompt_tokens / 1000.0) * price_in + (completion_tokens / 1000.0) * price_out,
        6,
    )


__all__ = [
    "DEFAULT_API_BASE", "DEFAULT_MODEL", "PRICE_INPUT_USD_PER_1K",
    "PRICE_OUTPUT_USD_PER_1K", "DEFAULT_CHAT_MODELS", "DEFAULT_VISION_MODELS",
    "KimiProvider", "call_kimi", "compute_cost_usd",
]