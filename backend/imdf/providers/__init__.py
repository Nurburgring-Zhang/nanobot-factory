"""VDP-2026 R6 — AI Provider public API.

合并 P19-A1 (claude/deepseek/qwen/doubao_extended/agnes) + P19-A2 batch 2
(gemini/kimi/zhipu/baidu/tencent) + P19-B2 batch 3 (mistral/cohere/
minimax/stepfun/nova) + P20-B (fal/replicate/comfyui/local) — 共 19 个
provider + 1 个 invoke 入口。
"""
from .registry import (
    ProviderRegistry, Provider, ProviderFamily,
    SAMPLE_PROVIDERS, get_registry, reset_registry_for_test, configure_db,
)
from .routes import router

# ─── P19-A1: 5 个 provider 模块 ──────────────────────────────────────────
from .claude import ClaudeProvider
from .deepseek import DeepSeekProvider
from .qwen import QwenProvider
from .doubao_extended import DoubaoProvider, DoubaoExtendedProvider
from .agnes import AgnesProvider, call_agnes

# ─── D-wire (P19-B1): 切到 _invoke (合并 A1 + A2 + B2 全部 15 family) ──
# P19-A1 创建 providers.invoke() 入口 (走 p19a1_entry,只 5 family)
# P19-A2 创建 _invoke.py shim (含全部 10 family) 但没把 __init__ 切过来
# P19-B1: 1-line wire 之后 A2 的 5 个 family (gemini/kimi/zhipu/baidu/tencent)
# 通过 providers.invoke / list_all_providers / get_provider_by_family 全部可见。
# P19-B2: 加 5 个新 family (mistral/cohere/minimax/stepfun/nova) → 15 family
from . import _invoke as _invoke_mod
invoke = _invoke_mod.invoke
list_all_providers = _invoke_mod.list_all_providers
get_provider_by_family = _invoke_mod.get_provider_by_family

# ─── P19-A2 batch 2: 5 个 provider 子包(占位 re-export)──────────────────
from . import gemini, kimi, zhipu, baidu, tencent  # batch 2

# ─── P19-B2 batch 3: 5 个 provider 子包(占位 re-export)──────────────────
from . import mistral, cohere, minimax, stepfun, nova  # batch 3

# ─── P20-B: 4 个 Pydantic-v2 BaseProvider 实现 ─────────────────────────────
# fal (fal.ai) / replicate / comfyui (REAL WebSocket 集成) / local (llama.cpp).
# 接口与 P20-A 对齐: invoke() / list_models() / health_check().
try:
    from ._provider_base import BaseProvider, ProviderResponse
    from .fal import FalProvider
    from .replicate import ReplicateProvider
    from .comfyui import ComfyUIProvider
    from .local import LocalProvider
    _P20B_AVAILABLE = True
except Exception:
    _P20B_AVAILABLE = False  # 容忍并发写冲突时的回退

# ─── P20-A: 4 个新 provider 类 (groq / together / fireworks / perplexity) ──
# 接口: BaseProvider 抽象 + invoke() / list_models() / health_check() + streaming.
# Pydantic v2 (P20-A 风格), 与 P20-B (fal/replicate/comfyui/local) 并存不冲突.
# 别名 BaseProviderV2 / ProviderResponseV2 避免与 P20-B 顶层同名符号碰撞.
try:
    from .base import (
        BaseProvider as BaseProviderV2,
        InvokeParams,
        ProviderResponse as ProviderResponseV2,
        ProviderChunk,
        HealthStatus,
    )
    from .groq import GroqProvider
    from .together import TogetherProvider
    from .fireworks import FireworksProvider
    from .perplexity import PerplexityProvider
    _P20A_AVAILABLE = True
except Exception:
    _P20A_AVAILABLE = False


__all__ = [
    # 已有 R6 API
    "ProviderRegistry", "Provider", "ProviderFamily",
    "SAMPLE_PROVIDERS", "get_registry", "reset_registry_for_test",
    "configure_db", "router",
    # P19-A1: provider classes
    "ClaudeProvider", "DeepSeekProvider", "QwenProvider",
    "DoubaoProvider", "DoubaoExtendedProvider", "AgnesProvider",
    # P19-A1: 入口
    "invoke", "list_all_providers", "get_provider_by_family",
    # P19-A2 batch 2
    "gemini", "kimi", "zhipu", "baidu", "tencent",
    # P19-B2 batch 3
    "mistral", "cohere", "minimax", "stepfun", "nova",
]

# P20-B exports (4 new providers + BaseProvider/ProviderResponse schema).
# 在并发 P20-A 也可能改写同一文件时, 本 try/except 保证旧 15 family 仍然可见.
if _P20B_AVAILABLE:
    __all__ += [
        "BaseProvider", "ProviderResponse",
        "FalProvider", "ReplicateProvider", "ComfyUIProvider", "LocalProvider",
    ]

# P20-A exports: BaseProviderV2 + InvokeParams + 4 new providers.
# 与 P20-B BaseProvider (v1) 不冲突: 这里别名是 BaseProviderV2 / ProviderResponseV2.
if _P20A_AVAILABLE:
    __all__ += [
        "BaseProviderV2", "InvokeParams", "ProviderResponseV2", "ProviderChunk", "HealthStatus",
        "GroqProvider", "TogetherProvider", "FireworksProvider", "PerplexityProvider",
        "call_agnes",
    ]
