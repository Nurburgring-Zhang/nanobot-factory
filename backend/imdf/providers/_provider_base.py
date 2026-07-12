"""P20-B: BaseProvider ABC + ProviderResponse Pydantic v2 model.

Shared foundation for P20-B batch of providers:
    - FalProvider       (fal.ai)          — image/video generation
    - ReplicateProvider (replicate.com)   — open-source inference
    - ComfyUIProvider   (local ComfyUI)   — workflow + WebSocket
    - LocalProvider     (llama.cpp)       — offline Llama-3

Each provider class inherits :class:`BaseProvider` and implements:
    - :meth:`list_models` returning ``List[str]``
    - :meth:`invoke(prompt, params, **opts) -> ProviderResponse`
    - :meth:`health_check() -> ProviderResponse`

The base type also exposes a default ``stream_chunks()`` for providers that
support server-sent events via ``httpx.AsyncClient.stream``.

Pydantic v2 ``ProviderResponse`` is the canonical return shape so callers
(``providers.invoke()`` dispatch, registry selection, billing) get a
consistent contract across the four providers.
"""
from __future__ import annotations

import abc
import time
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Union

import httpx
from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════
# ProviderResponse — canonical return shape (Pydantic v2)
# ═══════════════════════════════════════════════════════════════════════════


class ProviderResponse(BaseModel):
    """Unified response envelope for all P20-B providers.

    Every concrete provider's ``invoke()`` / ``health_check()`` returns one
    of these. Field defaults make partial failures (no error key raises) safe
    to inspect, but successful paths populate the ``content`` / ``images`` /
    ``videos`` fields.

    ``model_config`` enables ``extra='allow'`` so provider-specific metadata
    (e.g. fal's ``seed``, replicate's ``version``, comfyui's ``prompt_id``)
    can be added without subclassing.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    provider: str = ""
    model: str = ""
    content: str = ""
    images: List[str] = Field(default_factory=list)
    videos: List[str] = Field(default_factory=list)
    audio: List[str] = Field(default_factory=list)
    usage: Dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str = ""
    error_code: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)
    mock: bool = False
    is_placeholder: bool = False
    task_id: str = ""          # for async providers (comfyui / replicate async / fal async)
    status: str = ""           # queued / running / succeeded / failed / canceled

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=False)


# ═══════════════════════════════════════════════════════════════════════════
# BaseProvider — abstract interface
# ═══════════════════════════════════════════════════════════════════════════


class BaseProvider(abc.ABC):
    """Abstract base for all P20-B providers.

    Subclasses MUST define:
      - :attr:`provider_name` (str): canonical short id used in invoke()
      - :attr:`family` (str): same as provider_name for most providers
      - :meth:`invoke` → :class:`ProviderResponse`
      - :meth:`list_models` → list of model ids
      - :meth:`health_check` → :class:`ProviderResponse`

    Optional helpers come with default impls:
      - :meth:`has_credentials`: check api_key present
      - :meth:`cost_estimate_usd`: flat 0 (override in priced providers)
      - :meth:`stream_chunks`: not implemented by default
    """

    provider_name: str = "base"
    family: str = "base"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.api_key: str = (api_key or "").strip()
        self.base_url: str = (base_url or self._default_base_url()).rstrip("/")
        self.timeout: float = timeout

    @classmethod
    def _default_base_url(cls) -> str:
        return ""

    # ── Required abstract interface ──────────────────────────────────────
    @abc.abstractmethod
    async def invoke(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Run the provider's main capability and return a :class:`ProviderResponse`."""

    @abc.abstractmethod
    async def list_models(self) -> List[str]:
        """Return available model ids this provider can serve."""

    @abc.abstractmethod
    async def health_check(self) -> ProviderResponse:
        """Return a ProviderResponse describing service health."""

    # ── Optional helpers ────────────────────────────────────────────────
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def cost_estimate_usd(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> float:
        return 0.0

    async def stream_chunks(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Optional streaming helper — yields text chunks. Default: one-shot invoke."""
        resp = await self.invoke(prompt, params=params, **kwargs)
        if not resp.success:
            return
        yield resp.content

    # ── Internal helpers (protected) ────────────────────────────────────
    def _now(self) -> float:
        return time.time()

    def _latency_ms(self, t0: float) -> float:
        return round((time.time() - t0) * 1000.0, 2)

    def _auth_headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Key {self.api_key}"}  # fal-style

    def _bearer_headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}


def make_client(timeout: Optional[float] = None) -> httpx.AsyncClient:
    """Factory for a default httpx.AsyncClient used by concrete providers."""
    return httpx.AsyncClient(timeout=timeout or 60.0)


__all__ = ["BaseProvider", "ProviderResponse"]
