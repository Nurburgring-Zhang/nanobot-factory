"""P19-A1 + P19-A2: Unified invoke() entry for the providers package.

Exposes three top-level helpers so callers don't need to import the
underlying provider modules:

- ``invoke(...)`` — call a registered provider by family or id.
- ``list_all_providers()`` — list every provider currently registered.
- ``get_provider_by_family(family)`` — return the active provider for a
  given family.

This module is intentionally small — the heavy lifting (rate limiting,
circuit breaking, audit chain) still happens in
``engines.provider_registry.call_provider_smart``. When that is
unavailable we fall back to a thin per-provider dispatch.

P19-A2 batch 2 keeps the surface unchanged; the batch 2 providers
(gemini / kimi / zhipu / baidu / tencent) are dispatched via the
fallback path when ``engines.provider_registry`` is not importable.

Two invoke() signatures are supported for backwards compatibility:

  * **Batch-1 alias form** (preferred for P19-A1 tests)::
        await invoke("claude-3-5-sonnet", prompt="hi", fallback=False)
        await invoke("claude:custom-model-xyz", prompt="hi", fallback=False)
        await invoke("claude", prompt="hi", fallback=True)
    Returns ``{"success": bool, "provider": str, "model": str,
    "fallback_used": bool, "data"?: dict, "error"?: str}``.

  * **Batch-2 dict form**::
        await invoke(provider_dict, model, prompt, messages=..., kind=...)
    Returns ``{"ok": bool, "data"?: dict, "code"?: str, "error"?: str,
    "provider_id": str}``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ─── Alias resolution ────────────────────────────────────────────────────────
# Map short model aliases → (family, model_name). Used by invoke() when the
# caller passes a string instead of a provider dict.
_ALIAS_TO_FAMILY: Dict[str, str] = {
    # Claude
    "claude": "claude", "claude-3-5-sonnet": "claude", "claude-opus-4": "claude",
    "claude-3-5-haiku": "claude",
    # DeepSeek
    "deepseek": "deepseek", "deepseek-chat": "deepseek", "deepseek-coder": "deepseek",
    "deepseek-reasoner": "deepseek",
    # Qwen
    "qwen": "qwen", "qwen-plus": "qwen", "qwen-max": "qwen", "qwen-vl-plus": "qwen",
    # Doubao (火山方舟)
    "doubao": "doubao", "doubao-seed-1-6": "doubao", "doubao-pro": "doubao",
    "doubao-seedream": "doubao", "doubao-seedance": "doubao",
    # Agnes
    "agnes": "agnes", "agnes-2.0-flash": "agnes",
    # P19-A2 batch 2
    "gemini": "gemini", "gemini-2.0-flash": "gemini", "gemini-2.5-pro": "gemini",
    "gemini-2.0-flash-vision": "gemini",
    "kimi": "kimi", "kimi-k2.7": "kimi", "moonshot-v1-128k": "kimi",
    "zhipu": "zhipu", "glm-4-plus": "zhipu", "glm-4v-plus": "zhipu",
    "baidu": "baidu", "ernie-4.0-turbo": "baidu", "ernie-4.0-8k": "baidu",
    "tencent": "tencent", "hunyuan-pro": "tencent", "hunyuan-standard": "tencent",
    "hunyuan-vision": "tencent",
    # P19-B2 batch 3
    "mistral": "mistral", "mistral-large": "mistral", "mistral-large-latest": "mistral",
    "mistral-small": "mistral", "mistral-small-latest": "mistral",
    "mixtral-8x7b": "mistral", "mixtral": "mistral",
    "cohere": "cohere", "command-r-plus": "cohere", "command-r": "cohere",
    "command": "cohere", "embed-english-v3.0": "cohere",
    "minimax": "minimax", "abab-6.5s": "minimax", "abab-6.5-chat": "minimax",
    "abab": "minimax",
    "stepfun": "stepfun", "step-1-8k": "stepfun", "step-1-32k": "stepfun",
    "step-1v-8k": "stepfun", "step-1": "stepfun",
    "nova": "nova", "yi-34b": "nova", "yi-6b": "nova", "yi-vl-6b": "nova",
    "yi": "nova", "lingyiwanwu": "nova",
}

_FALLBACK_FAMILIES = ["claude", "deepseek", "qwen", "doubao", "agnes",
                       "gemini", "kimi", "zhipu", "baidu", "tencent",
                       "mistral", "cohere", "minimax", "stepfun", "nova"]


def _resolve_alias(alias_or_model: str) -> Dict[str, str]:
    """Resolve ``alias_or_model`` into ``{family, model}``."""
    s = str(alias_or_model or "").strip()
    # ``family:model`` form — explicit
    if ":" in s:
        family, _, model = s.partition(":")
        return {"family": family.strip().lower(),
                "model": model.strip() or None}
    family = _ALIAS_TO_FAMILY.get(s.lower(), s.lower())
    model = s if (":" not in s and s != family) else None
    # If alias IS the family name (e.g. "claude"), default model comes from registry
    return {"family": family, "model": model}


# ─── list_all_providers ──────────────────────────────────────────────────────

def list_all_providers() -> List[Any]:
    """Return every provider currently registered.

    Returns a list of ``id`` strings so callers can do ``"claude" in
    list_all_providers()`` (matches the P19-A1 contract).
    """
    try:
        from providers.registry import get_registry
        return [p.id for p in get_registry().list()]
    except Exception as e:
        logger.warning(f"list_all_providers fallback: {e}")
        return []


# ─── get_provider_by_family ──────────────────────────────────────────────────

def get_provider_by_family(family: str, prefer: str = "cost") -> Optional[Any]:
    """Return the active provider for ``family``.

    Returns the underlying provider **descriptor instance** (e.g.
    ``ClaudeProvider``, ``AgnesProvider``) so callers can introspect
    class-specific fields; falls back to the registry ``Provider`` row
    when no descriptor module is available for the family.
    """
    family = str(family or "").lower()
    # Try to import the family-specific module and instantiate its default descriptor.
    module_name = family if family in {"claude", "deepseek", "qwen", "doubao_extended",
                                        "agnes", "gemini", "kimi", "zhipu", "baidu", "tencent",
                                        "mistral", "cohere", "minimax", "stepfun", "nova"} else None
    if module_name:
        try:
            mod = __import__(f"providers.{module_name}", fromlist=["*"])
            # Look for a class ending in 'Provider'
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and name.endswith("Provider"):
                    try:
                        return obj()
                    except Exception:
                        continue
        except Exception:
            pass
    # Registry fallback — return the ``Provider`` dataclass instance.
    try:
        from providers.registry import get_registry
        p = get_registry().route(family=family, prefer=prefer)
        return p
    except Exception as e:
        logger.warning(f"get_provider_by_family fallback: {e}")
        return None


# ─── invoke ──────────────────────────────────────────────────────────────────

async def invoke(*args, **kwargs) -> Dict[str, Any]:
    """Polymorphic invoke — see module docstring for both signatures."""
    # Dispatch on positional args + types.
    if args and isinstance(args[0], dict):
        # Batch-2 dict form: invoke(provider_dict, model, prompt, ...)
        return await _invoke_dict_form(*args, **kwargs)
    # Batch-1 alias form: invoke(alias_or_provider, prompt=..., fallback=...)
    return await _invoke_alias_form(*args, **kwargs)


async def _invoke_dict_form(
    provider: Dict[str, Any],
    model: str,
    prompt: str = "",
    *,
    messages: Optional[List[Dict[str, Any]]] = None,
    kind: str = "chat",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Batch-2 dict-form invoke — full provider descriptor in hand."""
    if messages is None and prompt:
        messages = [{"role": "user", "content": prompt}]

    # Prefer engines.provider_registry.call_provider_smart for prod paths
    # (rate-limit + circuit-breaker + mock degrade + audit).
    try:
        from engines.provider_registry import call_provider_smart
        payload: Dict[str, Any] = {"model": model, "messages": messages or []}
        payload.update(kwargs)
        return await call_provider_smart(provider, payload, kind=kind)
    except Exception as e:
        logger.debug(f"engines.provider_registry unavailable: {e}")

    # Fallback — dispatch by family to the matching adapter module.
    payload = {"model": model, "messages": messages or []}
    payload.update(kwargs)
    family = str(provider.get("family") or "").lower()
    pid = provider.get("id") or family or "unknown"
    adapter = _pick_adapter(family)
    if adapter is None:
        return {"ok": False, "code": "unknown_family",
                "error": f"no adapter for family={family}",
                "provider_id": pid}
    return await adapter(provider, payload, kind=kind)


async def _invoke_alias_form(
    alias_or_provider: str,
    *,
    prompt: str = "",
    fallback: bool = False,
    messages: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Batch-1 alias-form invoke — resolve alias, optionally fallback."""
    resolved = _resolve_alias(alias_or_provider)
    family = resolved["family"]
    explicit_model = resolved["model"]

    # Get the active provider for the family
    provider_dict = None
    descriptor = None
    try:
        from providers.registry import get_registry, SAMPLE_PROVIDERS
        # 1) Prefer the descriptor's class-level defaults (api_base, model list)
        descriptor = get_provider_by_family(family)
        # 2) Get the registry row (carries persisted price/latency fields)
        reg_row = get_registry().route(family=family, prefer="cost")
        if reg_row is not None:
            provider_dict = reg_row.to_dict()
    except Exception as e:
        logger.warning(f"invoke: registry lookup failed for family={family}: {e}")

    if provider_dict is None:
        return {"success": False, "provider": family, "model": explicit_model or "",
                "fallback_used": False,
                "error": f"unknown provider family: {family}"}

    # Pick the model — explicit one wins, else default from provider
    model = explicit_model or provider_dict.get("default_model") or ""
    if not model:
        cfg = provider_dict.get("config") or {}
        models = cfg.get("models") or []
        model = models[0] if models else family

    if messages is None and prompt:
        messages = [{"role": "user", "content": prompt}]

    # Try primary
    primary_result = await _invoke_dict_form(
        provider_dict, model, prompt=prompt, messages=messages, **kwargs,
    )

    success = bool(primary_result.get("ok"))
    provider_used = provider_dict.get("id") or family
    model_used = model

    if success or not fallback:
        return {
            "success": success,
            "provider": provider_used,
            "model": model_used,
            "fallback_used": False,
            "data": primary_result.get("data"),
            "error": primary_result.get("error"),
            "code": primary_result.get("code"),
        }

    # Fallback chain — try other chat families in cost order
    for fb_family in _FALLBACK_FAMILIES:
        if fb_family == family:
            continue
        try:
            fb_row = get_provider_by_family_via_registry(fb_family)
        except Exception:
            continue
        if fb_row is None:
            continue
        fb_dict = fb_row.to_dict() if hasattr(fb_row, "to_dict") else fb_row
        fb_model = explicit_model or fb_dict.get("default_model") or fb_family
        fb_result = await _invoke_dict_form(
            fb_dict, fb_model, prompt=prompt, messages=messages, **kwargs,
        )
        if fb_result.get("ok"):
            return {
                "success": True,
                "provider": fb_dict.get("id") or fb_family,
                "model": fb_model,
                "fallback_used": True,
                "data": fb_result.get("data"),
            }

    return {
        "success": False,
        "provider": family,
        "model": model_used,
        "fallback_used": False,
        "error": primary_result.get("error"),
        "code": primary_result.get("code"),
    }


def get_provider_by_family_via_registry(family: str):
    """Internal helper — registry row only (no descriptor class lookup)."""
    try:
        from providers.registry import get_registry
        return get_registry().route(family=family, prefer="cost")
    except Exception:
        return None


# ─── Adapter dispatch helpers ────────────────────────────────────────────────

def _pick_adapter(family: str):
    """Return ``call_<family>`` adapter coroutine, or None."""
    name = str(family or "").lower()
    if name == "gemini":
        from providers.gemini import call_gemini
        return call_gemini
    if name == "kimi":
        from providers.kimi import call_kimi
        return call_kimi
    if name == "zhipu":
        from providers.zhipu import call_zhipu
        return call_zhipu
    if name == "baidu":
        from providers.baidu import call_baidu
        return call_baidu
    if name == "tencent":
        from providers.tencent import call_tencent
        return call_tencent
    if name == "claude":
        try:
            from providers.claude import call_claude  # type: ignore
            return call_claude
        except Exception:
            return None
    if name == "deepseek":
        try:
            from providers.deepseek import call_deepseek  # type: ignore
            return call_deepseek
        except Exception:
            return None
    if name == "qwen":
        try:
            from providers.qwen import call_qwen  # type: ignore
            return call_qwen
        except Exception:
            return None
    if name in ("doubao", "doubao_extended", "volcengine"):
        try:
            from providers.doubao_extended import call_doubao  # type: ignore
            return call_doubao
        except Exception:
            return None
    if name == "agnes":
        try:
            from providers.agnes import call_agnes  # type: ignore
            return call_agnes
        except Exception:
            return None
    # P19-B2 batch 3
    if name == "mistral":
        from providers.mistral import call_mistral
        return call_mistral
    if name == "cohere":
        from providers.cohere import call_cohere
        return call_cohere
    if name == "minimax":
        from providers.minimax import call_minimax
        return call_minimax
    if name == "stepfun":
        from providers.stepfun import call_stepfun
        return call_stepfun
    if name == "nova":
        from providers.nova import call_nova
        return call_nova
    return None


__all__ = ["invoke", "list_all_providers", "get_provider_by_family",
           "_resolve_alias", "get_provider_by_family_via_registry"]