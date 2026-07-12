"""P19-B2: Cohere provider adapter (RAG-optimized).

Provider family: cohere
Protocol: Cohere native REST (NOT OpenAI compatible) — distinct
``/v1/chat`` + ``/v1/embed`` + ``/v1/rerank`` endpoints.
Auth: Bearer API key
Default models:
  - command-r-plus   (RAG 优化 flagship, 128k)
  - command-r        (cost-efficient, 128k)
  - embed-english-v3.0 (embeddings, 1024 dim)
Pricing (USD per 1M tokens):
  - input:  $2.50
  - output: $10.00

Endpoints:
  POST ``{api_base}/chat``     — chat / RAG / tools
  POST ``{api_base}/embed``    — embeddings
  POST ``{api_base}/rerank``   — reranking (RAG pipeline)

Cohere's wire format differs from OpenAI:
  * request body uses ``message`` (singular) and ``preamble`` for system,
    plus ``chat_history`` (list of role/mesage dicts);
  * response returns ``message.text`` and ``text`` per turn;
  * usage keys are ``input_tokens`` / ``output_tokens``;
  * for embeddings the request takes ``texts`` and ``model``.
We translate internally so the unified ``invoke()`` can stay uniform.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_API_BASE = "https://api.cohere.ai/v1"
DEFAULT_MODEL = "command-r-plus"

# USD per 1K tokens (input, output) — registry stores per-1K.
PRICE_INPUT_USD_PER_1K = 0.0025
PRICE_OUTPUT_USD_PER_1K = 0.01

DEFAULT_CHAT_MODELS: List[str] = [
    "command-r-plus",
    "command-r",
    "command",
    "command-light",
]

DEFAULT_EMBED_MODELS: List[str] = [
    "embed-english-v3.0",
    "embed-multilingual-v3.0",
    "embed-english-light-v3.0",
]

DEFAULT_RERANK_MODELS: List[str] = [
    "rerank-english-v3.0",
    "rerank-multilingual-v3.0",
]


@dataclass
class CohereProvider:
    """In-memory descriptor for a Cohere registration."""
    id: str = "cohere"
    name: str = "Cohere (RAG 优化)"
    family: str = "cohere"
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
        "protocol": "cohere",
        "auth": "bearer",
        "models": list(DEFAULT_CHAT_MODELS),
        "embed_models": list(DEFAULT_EMBED_MODELS),
        "rerank_models": list(DEFAULT_RERANK_MODELS),
        "supports_streaming": True,
        "supports_function_call": True,
        "supports_rag": True,
        "supports_embed": True,
        "supports_rerank": True,
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
    env = os.environ.get("COHERE_API_KEY") or os.environ.get("CO_API_KEY") or ""
    return env.strip()


def _resolve_model(model: Optional[str], default_model: str) -> str:
    m = str(model or "").strip()
    return m or default_model


def _convert_messages_to_cohere(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert OpenAI-style messages → Cohere ``chat`` body.

    Cohere expects:
      - ``message``        (the latest user/assistant turn content)
      - ``chat_history``   (array of {role, message} prior turns)
      - ``preamble``       (system prompt — takes precedence over messages)

    We collapse the last user message into ``message`` and put the rest
    into ``chat_history``. System messages are concatenated into
    ``preamble`` (Cohere's preferred location for system instructions).
    """
    chat_history: List[Dict[str, str]] = []
    preamble_parts: List[str] = []
    last_user_message = ""
    last_role = "user"

    if messages:
        for m in messages:
            role = str(m.get("role", "user")).lower()
            content = str(m.get("content", ""))
            if role == "system":
                preamble_parts.append(content)
                continue
            if role in ("user", "assistant"):
                chat_history.append({"role": role, "message": content})
                last_role = role

        # Cohere: ``message`` is the LATEST user message awaiting reply.
        # Strip the trailing assistant turn (model) — Cohere chat_history
        # allows it, but for new prompts we want the user to drive.
        if chat_history and chat_history[-1]["role"] == last_role and last_role == "assistant":
            chat_history.pop()
        if chat_history and chat_history[-1]["role"] == "user":
            last_user_message = chat_history.pop()["message"]

    body: Dict[str, Any] = {
        "message": last_user_message,
        "chat_history": chat_history,
    }
    if preamble_parts:
        body["preamble"] = "\n\n".join(preamble_parts)
    return body


def _convert_cohere_response_to_openai(data: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Normalize Cohere ``/v1/chat`` response → OpenAI ``chat.completion`` shape."""
    text = str(data.get("text", "") or "")
    if not text and "message" in data:
        text = str((data.get("message") or {}).get("text", "") or "")
    finish_reason = "stop"
    if data.get("finish_reason"):
        finish_reason = str(data["finish_reason"]).lower()
    elif data.get("is_search_required") is False and not data.get("tool_calls"):
        finish_reason = "stop"

    usage = data.get("usage") or {}
    if "input_tokens" in usage or "output_tokens" in usage:
        pt = int(usage.get("input_tokens", 0) or 0)
        ct = int(usage.get("output_tokens", 0) or 0)
    else:
        # Cohere v1 sometimes uses billed_input_tokens / output_tokens
        pt = int(usage.get("billed_input_tokens", 0) or 0)
        ct = int(usage.get("billed_output_tokens", 0) or 0)

    return {
        "id": f"cohere-{model}-{pt + ct}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        },
        "raw": data,
    }


async def call_cohere(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Cohere call — uses native ``/v1/chat`` (NOT OpenAI compatible)."""
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
        return {"ok": False, "code": "missing_api_key", "error": "Cohere apiKey not configured"}
    default_model = provider.get("default_model") or cfg.get("defaultModel") or DEFAULT_MODEL
    model = _resolve_model(payload.get("model"), default_model)

    if kind in ("image", "video"):
        return {"ok": False, "code": "unsupported_kind",
                "error": "Cohere adapter 不支持类型: chat/embed/rerank only"}
    if kind == "embed":
        # Native /v1/embed — payload carries 'texts' or single 'input'
        try:
            import httpx
        except Exception as e:
            return {"ok": False, "code": "missing_dependency",
                    "error": f"httpx not available: {e}"}
        embed_model = model if "embed" in model else (cfg.get("embed_models") or DEFAULT_EMBED_MODELS)[0]
        texts = payload.get("texts") or ([payload.get("input")] if payload.get("input") else [])
        if not texts:
            texts = [""]
        body = {"texts": list(texts), "model": embed_model, "input_type": "search_document"}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_val) as client:
                resp = await client.post(f"{api_base}/embed", json=body, headers=headers)
            if resp.status_code >= 400:
                return {"ok": False, "code": "api_error",
                        "error": str(resp.text)[:2000], "status_code": resp.status_code}
            data = resp.json()
            return {"ok": True, "data": data, "provider_id": provider.get("id") or "cohere"}
        except Exception as e:
            return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}

    # Chat path
    messages = payload.get("messages") or []
    if not messages and payload.get("prompt"):
        messages = [{"role": "user", "content": str(payload.get("prompt") or "")}]
    body = _convert_messages_to_cohere(messages)
    body["model"] = model
    if "temperature" in payload:
        body["temperature"] = float(payload["temperature"])
    if "max_tokens" in payload:
        body["max_tokens"] = int(payload["max_tokens"])
    if "p" in payload:
        body["p"] = float(payload["p"])
    if "k" in payload:
        body["k"] = int(payload["k"])
    if payload.get("tools"):
        body["tools"] = payload["tools"]

    try:
        import httpx
    except Exception as e:
        return {"ok": False, "code": "missing_dependency",
                "error": f"httpx not available: {e}"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(f"{api_base}/chat", json=body, headers=headers)
        if resp.status_code >= 400:
            return {"ok": False, "code": "api_error",
                    "error": str(resp.text)[:2000], "status_code": resp.status_code}
        data = resp.json()
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}

    return {
        "ok": True,
        "data": _convert_cohere_response_to_openai(data, model),
        "provider_id": provider.get("id") or "cohere",
    }


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
    "PRICE_OUTPUT_USD_PER_1K", "DEFAULT_CHAT_MODELS", "DEFAULT_EMBED_MODELS",
    "DEFAULT_RERANK_MODELS", "CohereProvider", "call_cohere", "compute_cost_usd",
]
