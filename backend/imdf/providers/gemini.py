"""P19-A2: Google Gemini provider adapter.

Provider family: gemini
Protocol: Google Generative Language API (REST, ``v1beta``)
Auth: API key (``x-goog-api-key`` header) — supports v1beta models
Default models:
  - gemini-2.0-flash         (text)
  - gemini-2.5-pro           (text, reasoning)
  - gemini-2.0-flash-vision  (multimodal image+text)
Pricing (USD per 1M tokens, public 2026 snapshot):
  - input:  $0.70
  - output: $2.10

Endpoint surface (REST):
  POST ``{api_base}/models/{model}:generateContent``
  POST ``{api_base}/models/{model}:streamGenerateContent?alt=sse``
  POST ``{api_base}/models/{model}:countTokens``

This module exposes a single async function ``call_gemini`` plus the
synchronous descriptor ``GeminiProvider`` that mirrors the registry's
``Provider`` dataclass so callers can introspect models/pricing.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.0-flash"

# Public 2026 USD per 1M tokens (input, output). Registry stores
# price_per_1k_input / price_per_1k_output, so divide by 1000 here.
PRICE_INPUT_USD_PER_1K = 0.0007
PRICE_OUTPUT_USD_PER_1K = 0.0021

DEFAULT_CHAT_MODELS: List[str] = [
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-vision",
]

# Multimodal (image+text) input models — exposed for vision routing.
DEFAULT_VISION_MODELS: List[str] = [
    "gemini-2.0-flash-vision",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]


@dataclass
class GeminiProvider:
    """In-memory descriptor for a Gemini registration.

    Mirrors the shape expected by ``providers.registry.Provider`` so the
    registry can convert it via ``Provider(**asdict(gp))``.
    """
    id: str = "gemini"
    name: str = "Google Gemini"
    family: str = "gemini"
    default_model: str = DEFAULT_MODEL
    api_base: str = DEFAULT_API_BASE
    price_per_1k_input: float = PRICE_INPUT_USD_PER_1K
    price_per_1k_output: float = PRICE_OUTPUT_USD_PER_1K
    quota_per_minute: int = 60
    latency_p50_ms: int = 600
    latency_p99_ms: int = 1800
    trust_level: str = "official"
    status: str = "active"
    config: Dict[str, Any] = field(default_factory=lambda: {
        "protocol": "gemini",
        "auth": "x-goog-api-key",
        "models": list(DEFAULT_CHAT_MODELS),
        "vision_models": list(DEFAULT_VISION_MODELS),
        "supports_streaming": True,
        "supports_vision": True,
        "supports_function_call": True,
    })
    chat_models: List[str] = field(default_factory=lambda: list(DEFAULT_CHAT_MODELS))

    def to_registry_kwargs(self) -> Dict[str, Any]:
        """Return kwargs compatible with ``Provider(...)``."""
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
    """API key precedence: explicit arg > env > empty."""
    if api_key:
        return str(api_key).strip()
    env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return env.strip()


def _resolve_model(model: Optional[str], default_model: str) -> str:
    m = str(model or "").strip()
    return m or default_model


def _build_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI-style messages → Gemini ``contents`` array.

    Gemini accepts a list of ``{"role": "user"|"model", "parts": [...]}``.
    System messages are mapped to the first user turn as a prefix (the
    Gemini v1beta REST API does not expose a system role yet).
    """
    contents: List[Dict[str, Any]] = []
    system_text = ""
    for msg in messages or []:
        role = str(msg.get("role", "user")).lower()
        content = msg.get("content", "")
        if role == "system":
            system_text += (str(content) + "\n") if content else ""
            continue
        if role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": str(content)}]})
        else:
            contents.append({"role": "user", "parts": [{"text": str(content)}]})
    if system_text and contents and contents[0].get("role") == "user":
        first = contents[0]
        first_text = first["parts"][0].get("text", "")
        first["parts"][0]["text"] = system_text + first_text
    return contents


def _normalize_usage(usage_meta: Dict[str, Any]) -> Dict[str, int]:
    """Normalize Gemini ``usageMetadata`` → {prompt, completion, total}."""
    pt = int(usage_meta.get("promptTokenCount", 0) or 0)
    ct = int(usage_meta.get("candidatesTokenCount", 0) or 0)
    tt = int(usage_meta.get("totalTokenCount", pt + ct) or (pt + ct))
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}


async def call_gemini(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Issue a REST call to Gemini's ``generateContent`` endpoint.

    Parameters
    ----------
    provider : dict
        Provider descriptor with ``api_base`` and ``apiKey`` (or
        ``config.apiKey``) populated.
    payload : dict
        ``{"model": str, "messages": [{role, content}, ...], ...}``
    kind : str
        ``"chat"`` (default) | ``"vision"`` (alias for chat with images).

    Returns
    -------
    dict
        ``{"ok": bool, "data"?: dict, "code"?: str, "error"?: str}``.
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
        return {"ok": False, "code": "missing_api_key", "error": "Gemini apiKey not configured"}

    default_model = provider.get("default_model") or cfg.get("defaultModel") or DEFAULT_MODEL
    model = _resolve_model(payload.get("model"), default_model)
    messages = payload.get("messages") or []
    if kind not in ("chat", "vision"):
        return {"ok": False, "code": "invalid_kind",
                "error": f"gemini adapter 不支持类型: {kind}"}

    body: Dict[str, Any] = {
        "contents": _build_contents(messages),
    }
    # Generation config
    gen_cfg: Dict[str, Any] = {}
    if "temperature" in payload:
        gen_cfg["temperature"] = float(payload["temperature"])
    if "max_tokens" in payload:
        gen_cfg["maxOutputTokens"] = int(payload["max_tokens"])
    if "top_p" in payload:
        gen_cfg["topP"] = float(payload["top_p"])
    if "stop" in payload:
        stop = payload["stop"]
        if isinstance(stop, str):
            stop = [stop]
        gen_cfg["stopSequences"] = list(stop)
    if gen_cfg:
        body["generationConfig"] = gen_cfg

    endpoint = f"{api_base}/models/{model}:generateContent"

    # Lazy import to keep module import cheap & work without httpx in unit tests.
    try:
        import httpx
    except Exception as e:
        return {"ok": False, "code": "missing_dependency",
                "error": f"httpx not available: {e}"}

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(endpoint, json=body, headers=headers)
        if resp.status_code >= 400:
            return {"ok": False, "code": "api_error",
                    "error": str(resp.text)[:2000],
                    "status_code": resp.status_code}
        data = resp.json()
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}

    # Convert Gemini response to OpenAI-ish shape for downstream uniformity
    candidates = data.get("candidates") or []
    text_chunks: List[str] = []
    finish_reason = "stop"
    for c in candidates:
        parts = (c.get("content") or {}).get("parts") or []
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                text_chunks.append(str(p["text"]))
        if c.get("finishReason"):
            finish_reason = str(c["finishReason"]).lower()
    text = "".join(text_chunks)
    usage = _normalize_usage(data.get("usageMetadata") or {})
    return {
        "ok": True,
        "data": {
            "id": f"gemini-{model}-{usage['total_tokens']}",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage,
            "raw": data,
        },
        "provider_id": provider.get("id") or "gemini",
    }


def compute_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    price_in: float = PRICE_INPUT_USD_PER_1K,
    price_out: float = PRICE_OUTPUT_USD_PER_1K,
) -> float:
    """Convenience: USD cost for a Gemini call."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    return round(
        (prompt_tokens / 1000.0) * price_in + (completion_tokens / 1000.0) * price_out,
        6,
    )


__all__ = [
    "DEFAULT_API_BASE", "DEFAULT_MODEL", "PRICE_INPUT_USD_PER_1K",
    "PRICE_OUTPUT_USD_PER_1K", "DEFAULT_CHAT_MODELS", "DEFAULT_VISION_MODELS",
    "GeminiProvider", "call_gemini", "compute_cost_usd",
]