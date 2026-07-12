"""P20-B / ReplicateProvider — replicate.com host of open-source models.

Replicate exposes every model in the form::

    POST   /v1/predictions        # create
    GET    /v1/predictions/{id}   # poll
    GET    /v1/models             # list catalogue (paginated)

Auth: ``Authorization: Token <REPLICATE_API_TOKEN>`` (r8_...).
Most model calls return a ``prediction.urls.get`` URL once ``status="succeeded"``.

Models exposed in :func:`list_models` cover the most common open-source
modalities: SDXL, FLUX, Llama 3, Mixtral, Whisper, Stable Video Diffusion.

Public interface (matches P20-A contract): see ``_provider_base``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Mapping, Optional

import httpx

from ._provider_base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


REPLICATE_BASE_URL = "https://api.replicate.com/v1"
ENV_VAR = "REPLICATE_API_TOKEN"

DEFAULT_CHAT_MODEL = "meta/meta-llama-3-8b-instruct"
DEFAULT_IMAGE_MODEL = "black-forest-labs/flux-schnell"

DEFAULT_MODELS: List[str] = [
    # chat
    "meta/meta-llama-3-8b-instruct",
    "meta/meta-llama-3-70b-instruct",
    "meta/llama-2-70b-chat",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    # image
    "black-forest-labs/flux-schnell",
    "black-forest-labs/flux-dev",
    "stability-ai/sdxl",
    "stability-ai/stable-diffusion-3",
    # video
    "stability-ai/stable-video-diffusion",
    # audio
    "openai/whisper",
    "meta/musicgen",
]


# ─── Provider ────────────────────────────────────────────────────────────────
class ReplicateProvider(BaseProvider):
    """replicate.com open-source inference provider."""

    provider_name = "replicate"
    family = "replicate"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 90.0,
    ):
        super().__init__(
            api_key=api_key or os.environ.get(ENV_VAR, ""),
            base_url=base_url or REPLICATE_BASE_URL,
            timeout=timeout,
        )

    @classmethod
    def _default_base_url(cls) -> str:
        return REPLICATE_BASE_URL

    # ── BaseProvider impl ──────────────────────────────────────────────
    async def list_models(self) -> List[str]:
        """Return curated catalogue. Use ``list_models_remote`` for full catalogue."""
        return list(DEFAULT_MODELS)

    async def list_models_remote(self, limit: int = 50) -> List[str]:
        """Fetch model handles from /v1/models (paginated; default first page)."""
        if not self.has_credentials():
            return list(DEFAULT_MODELS)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    params={"limit": limit},
                    headers=self._bearer_headers(),
                )
            if resp.status_code != 200:
                return list(DEFAULT_MODELS)
            data = resp.json() if hasattr(resp, "json") else {}
            items = data.get("results") or []
            out: List[str] = []
            for it in items:
                owner = (it.get("owner") or "").strip()
                name = (it.get("name") or "").strip()
                if not name:
                    continue
                if owner and "/" not in name:
                    out.append(f"{owner}/{name}")
                else:
                    out.append(name)
            return out or list(DEFAULT_MODELS)
        except Exception as exc:
            logger.warning("replicate list_models_remote failed: %s", exc)
            return list(DEFAULT_MODELS)

    async def invoke(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Submit prediction, poll until terminal, return unified response."""
        params = dict(params or {})
        model: str = str(
            params.get("model") or kwargs.get("model") or DEFAULT_CHAT_MODEL,
        )
        kind: str = str(params.get("kind") or kwargs.get("kind") or self._kind_of(model))

        if not self.has_credentials():
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                is_placeholder=True,
                mock=True,
                status="placeholder",
                error="REPLICATE_API_TOKEN 未配置 — 走占位",
                raw={"placeholder_url": "https://via.placeholder.com/512.png?text=replicate-placeholder",
                     "kind": kind, "prompt": prompt},
            )

        # Replicate versioned model: model may be "owner/name" or include version hash.
        url, body = self._build_request(model, prompt, params)
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                sub = await client.post(
                    url, headers=self._bearer_headers(), json=body,
                )
            if sub.status_code not in (200, 201, 202):
                err_text = getattr(sub, "text", "")[:500]
                return ProviderResponse(
                    success=False,
                    provider=self.provider_name,
                    model=model,
                    error=f"replicate submit HTTP {sub.status_code}: {err_text}",
                    error_code=str(sub.status_code),
                    latency_ms=self._latency_ms(t0),
                )
            sub_payload = sub.json() if hasattr(sub, "json") else {}
            prediction_id = sub_payload.get("id") or ""
            # Sync completion: replicate returns both ``id`` AND ``output``
            # simultaneously when the model is fast / sync-mode enabled.
            inline_ready = (
                "output" in sub_payload
                and sub_payload.get("status") in ("", None, "succeeded")
            )
            if inline_ready or not prediction_id:
                images, videos = self._extract_media(sub_payload)
                return ProviderResponse(
                    success=True,
                    provider=self.provider_name,
                    model=model,
                    content=self._extract_text(sub_payload),
                    images=images,
                    videos=videos,
                    raw=sub_payload,
                    task_id=prediction_id,
                    status=sub_payload.get("status") or "succeeded",
                    latency_ms=self._latency_ms(t0),
                )
            return await self._poll_prediction(prediction_id, model, t0)
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"replicate 异常: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    async def health_check(self) -> ProviderResponse:
        """Verify replicate token by listing account models (1 item)."""
        if not self.has_credentials():
            return ProviderResponse(
                success=True,
                provider=self.provider_name,
                status="placeholder",
                is_placeholder=True,
                error="REPLICATE_API_TOKEN 未配置",
            )
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    params={"limit": 1},
                    headers=self._bearer_headers(),
                )
            ok = resp.status_code == 200
            return ProviderResponse(
                success=ok,
                provider=self.provider_name,
                status="ok" if ok else "error",
                error="" if ok else f"replicate /models HTTP {resp.status_code}",
                error_code="" if ok else str(resp.status_code),
                latency_ms=self._latency_ms(t0),
            )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                status="error",
                error=f"replicate health 异常: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    # ── Internal: poll a prediction until terminal ────────────────────
    async def _poll_prediction(
        self,
        prediction_id: str,
        model: str,
        t0: float,
        max_wait_s: float = 60.0,
        interval_s: float = 0.5,
    ) -> ProviderResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            elapsed = 0.0
            while elapsed < max_wait_s:
                await asyncio.sleep(interval_s)
                elapsed += interval_s
                resp = await client.get(
                    f"{self.base_url}/predictions/{prediction_id}",
                    headers=self._bearer_headers(),
                )
                if resp.status_code != 200:
                    continue
                pdata = resp.json() if hasattr(resp, "json") else {}
                status = pdata.get("status") or ""
                if status == "succeeded":
                    images, videos = self._extract_media(pdata)
                    return ProviderResponse(
                        success=True,
                        provider=self.provider_name,
                        model=model,
                        task_id=prediction_id,
                        content=self._extract_text(pdata),
                        images=images,
                        videos=videos,
                        status="succeeded",
                        raw=pdata,
                        latency_ms=self._latency_ms(t0),
                    )
                if status in ("failed", "canceled"):
                    err = (pdata.get("error") or "")
                    return ProviderResponse(
                        success=False,
                        provider=self.provider_name,
                        model=model,
                        task_id=prediction_id,
                        status=status,
                        error=str(err) if err else f"replicate {status}",
                        raw=pdata,
                        latency_ms=self._latency_ms(t0),
                    )
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                task_id=prediction_id,
                status="timeout",
                error=f"replicate 轮询超时 ({max_wait_s}s)",
                latency_ms=self._latency_ms(t0),
            )

    # ── Helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _kind_of(model: str) -> str:
        m = model.lower()
        if any(s in m for s in ("sdxl", "flux", "stable-video", "imagen")):
            return "image" if "video" not in m else "video"
        if "video" in m:
            return "video"
        if any(s in m for s in ("whisper", "musicgen", "audio", "kokoro", "bark")):
            return "audio"
        return "chat"

    def _build_request(
        self,
        model: str,
        prompt: str,
        params: Mapping[str, Any],
    ) -> tuple:
        """Choose POST URL + body based on model form (``owner/name`` vs id+version)."""
        version = params.get("version") or kwargs if False else None  # never used
        # pythonic: scope the version optional to inside the kwargs dict
        version = params.get("version")  # type: ignore[var-annotated]

        if model.startswith("http"):  # explicit URL override
            return model, params.get("input") or {"prompt": prompt}

        if ":" in model:  # name:version / name:hash
            name, _, ver = model.partition(":")
            return (
                f"{self.base_url}/predictions",
                {"version": ver.strip(), "input": self._build_input(name, prompt, params)},
            )

        if "/" in model:
            # owner/name → POST /v1/models/{owner}/{name}/predictions
            return (
                f"{self.base_url}/models/{model}/predictions",
                {"input": self._build_input(model, prompt, params)},
            )

        if version:
            return (
                f"{self.base_url}/predictions",
                {"version": version, "input": self._build_input(model, prompt, params)},
            )

        # Fallback: classic version-id endpoint
        return (
            f"{self.base_url}/predictions",
            {"version": model, "input": self._build_input(model, prompt, params)},
        )

    @staticmethod
    def _build_input(model: str, prompt: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        m = model.lower()
        if any(s in m for s in ("llama", "mixtral", "mistral", "qwen")):
            return {
                "prompt": prompt,
                "max_tokens": params.get("max_tokens", 512),
                "temperature": params.get("temperature", 0.7),
                **{k: v for k, v in params.items() if k not in ("model", "kind")},
            }
        if any(s in m for s in ("sdxl", "flux", "stable-diffusion")):
            return {
                "prompt": prompt,
                "width": params.get("width", 1024),
                "height": params.get("height", 1024),
                "num_outputs": params.get("n", 1),
                **{k: v for k, v in params.items() if k not in ("model", "kind")},
            }
        # default input shape (chat / embedding / generic)
        return {
            "prompt": prompt,
            **{k: v for k, v in params.items() if k not in ("model", "kind")},
        }

    @staticmethod
    def _extract_media(payload: Mapping[str, Any]) -> tuple:
        images: List[str] = []
        videos: List[str] = []
        if not isinstance(payload, Mapping):
            return images, videos
        out = payload.get("output")
        if isinstance(out, list):
            for item in out:
                if isinstance(item, str):
                    low = item.lower()
                    if any(ext in low for ext in (".mp4", ".webm", ".mov")):
                        videos.append(item)
                    elif any(ext in low for ext in (".png", ".jpg", ".jpeg", ".webp")):
                        images.append(item)
                    elif item.startswith("http"):
                        images.append(item)
        elif isinstance(out, str) and out.startswith("http"):
            images.append(out)
        return images, videos

    @staticmethod
    def _extract_text(payload: Mapping[str, Any]) -> str:
        out = payload.get("output")
        if isinstance(out, list):
            text_pieces = []
            for item in out:
                if isinstance(item, str) and not item.startswith("http"):
                    text_pieces.append(item)
            return "\n".join(text_pieces)
        if isinstance(out, str):
            return out
        return ""


__all__ = ["ReplicateProvider"]
