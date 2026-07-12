"""P19-B2: Nova (零一万物) provider adapter (OpenAI-compatible).

Provider family: nova
Protocol: OpenAI compatible (``/v1/chat/completions``)
Auth: Bearer API key
Default models:
  - yi-34b    (flagship 200k context)
  - yi-6b     (cost-efficient 200k context)
  - yi-vl-6b  (vision-language 6B)
Pricing (USD per 1M tokens):
  - input:  $0.20
  - output: $0.60

Endpoint:
  POST ``{api_base}/chat/completions``

Nova (零一万物, also branded as "01.AI" / "Yi") is a Chinese LLM
provider. Its chat endpoint is OpenAI-compatible, so we reuse the
engines ``call_openai_compatible`` plumbing under the hood.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_API_BASE = "https://api.lingyiwanwu.com/v1"
DEFAULT_MODEL = "yi-34b"

# USD per 1K tokens (input, output) — registry stores per-1K.
PRICE_INPUT_USD_PER_1K = 0.0002
PRICE_OUTPUT_USD_PER_1K = 0.0006

DEFAULT_CHAT_MODELS: List[str] = [
    "yi-34b",
    "yi-6b",
    "yi-6b-chat",
    "yi-34b-chat",
    "yi-vl-6b",
]

DEFAULT_VISION_MODELS: List[str] = [
    "yi-vl-6b",
]


@dataclass
class NovaProvider:
    """In-memory descriptor for a Nova (零一万物 / Yi) registration."""
    id: str = "nova"
    name: str = "零一万物 Nova"
    family: str = "nova"
    default_model: str = DEFAULT_MODEL
    api_base: str = DEFAULT_API_BASE
    price_per_1k_input: float = PRICE_INPUT_USD_PER_1K
    price_per_1k_output: float = PRICE_OUTPUT_USD_PER_1K
    quota_per_minute: int = 60
    latency_p50_ms: int = 500
    latency_p99_ms: int = 1500
    trust_level: str = "verified"
    status: str = "active"
    config: Dict[str, Any] = field(default_factory=lambda: {
        "protocol": "openai-compatible",
        "auth": "bearer",
        "models": list(DEFAULT_CHAT_MODELS),
        "vision_models": list(DEFAULT_VISION_MODELS),
        "supports_streaming": True,
        "supports_vision": True,
        "supports_function_call": True,
        "region": "cn",
        "max_context_tokens": 200000,
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
    env = (
        os.environ.get("NOVA_API_KEY")
        or os.environ.get("YI_API_KEY")
        or os.environ.get("LINGYIWANWU_API_KEY")
        or ""
    )
    return env.strip()


def _resolve_model(model: Optional[str], default_model: str) -> str:
    m = str(model or "").strip()
    return m or default_model


async def call_nova(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Nova call — OpenAI-compatible REST via shared helper."""
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
        return {"ok": False, "code": "missing_api_key", "error": "Nova apiKey not configured"}
    default_model = provider.get("default_model") or cfg.get("defaultModel") or DEFAULT_MODEL
    model = _resolve_model(payload.get("model"), default_model)

    openai_provider = {
        "id": provider.get("id") or "nova",
        "protocol": "openai-compatible",
        "baseUrl": api_base,
        "apiKey": api_key,
        "enabled": True,
        "chatModels": cfg.get("models", DEFAULT_CHAT_MODELS),
    }
    if kind in ("image", "video"):
        return {"ok": False, "code": "unsupported_kind",
                "error": "Nova adapter 不支持类型: chat/vision only"}

    try:
        from engines import provider_registry as pr  # type: ignore
        return await pr.call_openai_compatible(
            openai_provider,
            {"model": model, **payload},
            kind="chat",
        )
    except Exception:
        try:
            import httpx
        except Exception as e:
            return {"ok": False, "code": "missing_dependency",
                    "error": f"httpx not available: {e}"}
        endpoint = f"{api_base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
        if "temperature" in payload:
            body["temperature"] = float(payload["temperature"])
        if "max_tokens" in payload:
            body["max_tokens"] = int(payload["max_tokens"])
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                   "Accept": "application/json"}
        timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_val) as client:
                resp = await client.post(endpoint, json=body, headers=headers)
            if resp.status_code >= 400:
                return {"ok": False, "code": "api_error",
                        "error": str(resp.text)[:2000],
                        "status_code": resp.status_code}
            return {"ok": True, "data": resp.json(),
                    "provider_id": provider.get("id") or "nova"}
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
    "NovaProvider", "call_nova", "compute_cost_usd",
]
