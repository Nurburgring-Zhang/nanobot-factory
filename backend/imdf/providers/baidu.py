"""P19-A2: Baidu Ernie (文心一言) provider adapter.

Provider family: baidu
Protocol: Baidu Qianfan REST API (``aip.baidubce.com``) — NOT OpenAI compatible
Auth: client_id + client_secret exchanged for a short-lived ``access_token``
Default models:
  - ernie-4.0-turbo   (旗舰, 8K context)
  - ernie-4.0-8k      (8K context, slightly cheaper)
Pricing (USD per 1M tokens):
  - input:  $0.35
  - output: $1.00

Baidu auth flow:
  POST ``https://aip.baidubce.com/oauth/2.0/token`` with grant_type=client_credentials
  → returns ``{"access_token": "...", "expires_in": 2592000}`` (30 days)

Endpoint:
  POST ``https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{model}?access_token={token}``

The ``access_token`` is cached in-process for the configured lifetime.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_OAUTH_BASE = "https://aip.baidubce.com"
DEFAULT_API_BASE = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
DEFAULT_MODEL = "ernie-4.0-turbo"

# USD per 1K tokens (input, output).
PRICE_INPUT_USD_PER_1K = 0.00035
PRICE_OUTPUT_USD_PER_1K = 0.001

DEFAULT_CHAT_MODELS: List[str] = [
    "ernie-4.0-turbo",
    "ernie-4.0-8k",
    "ernie-3.5-8k",
    "ernie-3.5-4k",
]

DEFAULT_VISION_MODELS: List[str] = [
    "ernie-4.0-turbo-vision",
]


# ─── Process-wide access-token cache ─────────────────────────────────────────
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}
"""Mapping ``api_key_fingerprint`` → ``{"token": str, "expires_at": float}``."""


def _fingerprint(api_key: str) -> str:
    """Stable identifier for the (client_id, client_secret) pair."""
    import hashlib
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


async def _fetch_access_token(
    client_id: str,
    client_secret: str,
    *,
    oauth_base: str = DEFAULT_OAUTH_BASE,
    force: bool = False,
) -> Dict[str, Any]:
    """Exchange ``client_id``/``client_secret`` for an access_token.

    Caches the token in-process until ``expires_at``. Returns the
    ``{access_token, expires_in, expires_at}`` dict or an error
    ``{ok: False, code, error}`` payload.
    """
    fp = _fingerprint(f"{client_id}|{client_secret}")
    now = time.time()
    cached = _TOKEN_CACHE.get(fp)
    if cached and not force and cached.get("expires_at", 0) - 60 > now:
        return {"ok": True, "access_token": cached["token"],
                "expires_in": int(cached["expires_at"] - now), "cached": True}

    try:
        import httpx
    except Exception as e:
        return {"ok": False, "code": "missing_dependency",
                "error": f"httpx not available: {e}"}

    url = f"{oauth_base.rstrip('/')}/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, params=params)
        if resp.status_code >= 400:
            return {"ok": False, "code": "oauth_error",
                    "error": str(resp.text)[:2000],
                    "status_code": resp.status_code}
        data = resp.json()
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}

    token = data.get("access_token")
    expires_in = int(data.get("expires_in", 0) or 0)
    if not token:
        return {"ok": False, "code": "no_token",
                "error": f"Baidu OAuth 响应无 access_token: {data}"}
    _TOKEN_CACHE[fp] = {"token": token, "expires_at": now + max(60, expires_in)}
    return {"ok": True, "access_token": token,
            "expires_in": expires_in, "cached": False}


def clear_token_cache(api_key: Optional[str] = None) -> None:
    """Test hook: drop cached access tokens."""
    if api_key:
        fp = _fingerprint(api_key)
        _TOKEN_CACHE.pop(fp, None)
    else:
        _TOKEN_CACHE.clear()


@dataclass
class BaiduProvider:
    """In-memory descriptor for a Baidu (文心) registration."""
    id: str = "baidu"
    name: str = "百度文心 ERNIE"
    family: str = "baidu"
    default_model: str = DEFAULT_MODEL
    api_base: str = DEFAULT_API_BASE
    price_per_1k_input: float = PRICE_INPUT_USD_PER_1K
    price_per_1k_output: float = PRICE_OUTPUT_USD_PER_1K
    quota_per_minute: int = 60
    latency_p50_ms: int = 800
    latency_p99_ms: int = 2200
    trust_level: str = "verified"
    status: str = "active"
    config: Dict[str, Any] = field(default_factory=lambda: {
        "protocol": "baidu",
        "auth": "client_credentials",
        "models": list(DEFAULT_CHAT_MODELS),
        "vision_models": list(DEFAULT_VISION_MODELS),
        "oauth_base": DEFAULT_OAUTH_BASE,
        "supports_streaming": True,
        "supports_vision": True,
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


def _resolve_credentials(api_key: Optional[str] = None) -> Dict[str, str]:
    """Resolve client_id / client_secret from explicit arg or env.

    Baidu uses a single ``api_key`` string in the registry that we treat
    as ``"<client_id>:<client_secret>"``. As a fallback the env vars
    ``BAIDU_API_KEY`` / ``BAIDU_CLIENT_ID`` + ``BAIDU_CLIENT_SECRET``
    are honoured.
    """
    if api_key and ":" in api_key:
        cid, sec = api_key.split(":", 1)
        return {"client_id": cid.strip(), "client_secret": sec.strip()}
    env_key = (api_key or os.environ.get("BAIDU_API_KEY")
               or os.environ.get("BAIDU_CLIENT_ID") or "")
    env_secret = os.environ.get("BAIDU_CLIENT_SECRET") or ""
    if env_key and ":" in env_key:
        cid, sec = env_key.split(":", 1)
        return {"client_id": cid.strip(), "client_secret": sec.strip()}
    return {"client_id": env_key.strip(), "client_secret": env_secret.strip()}


def _resolve_model(model: Optional[str], default_model: str) -> str:
    m = str(model or "").strip()
    return m or default_model


async def call_baidu(
    provider: Dict[str, Any],
    payload: Dict[str, Any],
    kind: str = "chat",
) -> Dict[str, Any]:
    """Baidu Qianfan call — auth via client_credentials, then POST to chat endpoint."""
    if not provider:
        return {"ok": False, "code": "missing_provider", "error": "provider descriptor is empty"}
    if kind in ("image", "video"):
        return {"ok": False, "code": "unsupported_kind",
                "error": f"Baidu adapter 不支持类型: {kind}"}

    cfg = provider.get("config") or {}
    creds = _resolve_credentials(
        provider.get("apiKey") or provider.get("api_key")
        or cfg.get("apiKey") or cfg.get("api_key")
    )
    if not creds["client_id"] or not creds["client_secret"]:
        return {"ok": False, "code": "missing_credentials",
                "error": "Baidu apiKey 必须是 'client_id:client_secret' 格式"}

    api_base = (provider.get("api_base") or cfg.get("apiBase") or DEFAULT_API_BASE).rstrip("/")
    oauth_base = cfg.get("oauth_base") or DEFAULT_OAUTH_BASE

    # Step 1: get access_token (cached)
    tok = await _fetch_access_token(
        creds["client_id"], creds["client_secret"], oauth_base=oauth_base,
    )
    if not tok.get("ok"):
        return {"ok": False, "code": tok.get("code", "oauth_failed"),
                "error": tok.get("error", "OAuth failed")}

    access_token = tok["access_token"]
    default_model = provider.get("default_model") or cfg.get("defaultModel") or DEFAULT_MODEL
    model = _resolve_model(payload.get("model"), default_model)

    messages = payload.get("messages") or []
    # Baidu uses single ``message`` array; convert OpenAI messages.
    system_parts = []
    user_parts = []
    for m in messages:
        role = str(m.get("role", "user")).lower()
        if role == "system":
            system_parts.append(str(m.get("content", "")))
        elif role in ("assistant", "model"):
            user_parts.append({"role": "assistant", "content": str(m.get("content", ""))})
        else:
            user_parts.append({"role": "user", "content": str(m.get("content", ""))})
    body: Dict[str, Any] = {"messages": user_parts}
    if system_parts:
        body["system"] = "\n".join(system_parts)
    if "temperature" in payload:
        try:
            body["temperature"] = float(payload["temperature"])
        except (TypeError, ValueError):
            pass
    if "max_tokens" in payload:
        try:
            body["max_output_tokens"] = int(payload["max_tokens"])
        except (TypeError, ValueError):
            pass

    endpoint = f"{api_base.rstrip('/')}/{model}?access_token={access_token}"

    try:
        import httpx
    except Exception as e:
        return {"ok": False, "code": "missing_dependency",
                "error": f"httpx not available: {e}"}

    timeout_val = float(payload.get("timeout_ms", 60000) / 1000.0)
    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(endpoint, json=body)
        if resp.status_code >= 400:
            return {"ok": False, "code": "api_error",
                    "error": str(resp.text)[:2000],
                    "status_code": resp.status_code}
        raw = resp.json()
    except Exception as e:
        return {"ok": False, "code": "request_failed", "error": str(e)[:2000]}

    # Convert Baidu response to OpenAI-ish shape
    text = str(raw.get("result", "") or "")
    usage = raw.get("usage") or {}
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    return {
        "ok": True,
        "data": {
            "id": f"ernie-{model}-{pt + ct}",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {"index": 0,
                 "message": {"role": "assistant", "content": text},
                 "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": pt,
                      "completion_tokens": ct,
                      "total_tokens": pt + ct},
            "raw": raw,
        },
        "provider_id": provider.get("id") or "baidu",
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
    "DEFAULT_OAUTH_BASE", "DEFAULT_API_BASE", "DEFAULT_MODEL",
    "PRICE_INPUT_USD_PER_1K", "PRICE_OUTPUT_USD_PER_1K",
    "DEFAULT_CHAT_MODELS", "DEFAULT_VISION_MODELS",
    "BaiduProvider", "call_baidu", "compute_cost_usd",
    "_fetch_access_token", "clear_token_cache",
]