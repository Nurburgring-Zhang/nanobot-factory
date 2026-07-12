"""P20-B / FalProvider — fal.ai (https://fal.run) integration.

fal.ai hosts hosted versions of many SDXL / Flux / Sora-style image + video
models behind a simple queue + submit + status REST API. The flow is:

    1. POST /{model_id}            → returns ``request_id`` + optional immediate result
    2. GET  /{model_id}/requests/{request_id}/status  → queue-position polling
    3. GET  /{model_id}/requests/{request_id}        → final payload with URLs

Auth: ``Authorization: Key <FAL_KEY>`` (free tier ``FAL_KEY_ID`` / ``FAL_KEY_SECRET``
also accepted; we just use a single API key here).

Models exposed (subset):
    - fal-ai/flux/schnell         (fast image, free tier)
    - fal-ai/flux/dev             (best quality image)
    - fal-ai/sdxl-turbo           (legacy turbo image)
    - fal-ai/lcm                 (latent consistency)
    - fal-ai/kokoro              (TTS)
    - fal-ai/wan-video           (video gen)
    - fal-ai/animatediff       (motion)

Public interface (matches P20-A contract): see ``_provider_base``.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Mapping, Optional

import httpx

from ._provider_base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


# ─── Defaults ────────────────────────────────────────────────────────────────
FAL_BASE_URL = "https://fal.run"
FAL_QUEUE_BASE_URL = "https://queue.fal.run"
ENV_VAR = "FAL_KEY"

DEFAULT_IMAGE_MODEL = "fal-ai/flux/schnell"
DEFAULT_VIDEO_MODEL = "fal-ai/wan-video"

DEFAULT_MODELS: List[str] = [
    "fal-ai/flux/schnell",
    "fal-ai/flux/dev",
    "fal-ai/sdxl-turbo",
    "fal-ai/lcm",
    "fal-ai/animatediff",
    "fal-ai/wan-video",
    "fal-ai/kokoro",
]


# ─── Provider ────────────────────────────────────────────────────────────────
class FalProvider(BaseProvider):
    """fal.ai hosted inference provider."""

    provider_name = "fal"
    family = "fal"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 90.0,
    ):
        super().__init__(
            api_key=api_key or os.environ.get(ENV_VAR, ""),
            base_url=base_url or FAL_BASE_URL,
            timeout=timeout,
        )
        self._queue_url = FAL_QUEUE_BASE_URL

    @classmethod
    def _default_base_url(cls) -> str:
        return FAL_BASE_URL

    # ── BaseProvider impl ──────────────────────────────────────────────
    async def list_models(self) -> List[str]:
        """Return list of known fal model ids.

        Note: real fal model list comes from fal.ai's ``/models`` endpoint
        (returns a large catalogue). For predictability + testability we
        expose a curated known-good list. On environment with credentials
        you can call ``list_models_remote()`` instead.
        """
        return list(DEFAULT_MODELS)

    async def list_models_remote(self) -> List[str]:
        """Optional: fetch the full catalogue from fal.run /models."""
        if not self.has_credentials():
            return list(DEFAULT_MODELS)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._auth_headers(),
                )
            if resp.status_code != 200:
                return list(DEFAULT_MODELS)
            data = resp.json() if hasattr(resp, "json") else {}
            items = data if isinstance(data, list) else data.get("models") or []
            out = []
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    out.append(str(it["id"]))
                elif isinstance(it, str):
                    out.append(it)
            return out or list(DEFAULT_MODELS)
        except Exception as exc:  # pragma: no cover - network path
            logger.warning("fal list_models_remote failed: %s", exc)
            return list(DEFAULT_MODELS)

    async def invoke(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Submit the prompt to fal and return a unified response.

        If no api key is configured, returns a placeholder response marked
        ``is_placeholder=True``.
        """
        params = dict(params or {})
        model: str = str(params.get("model") or kwargs.get("model") or DEFAULT_IMAGE_MODEL)
        kind: str = str(params.get("kind") or kwargs.get("kind") or self._kind_of(model))

        if not self.has_credentials():
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                content="",
                error="FAL_KEY 未配置 — 走占位 URL",
                is_placeholder=True,
                mock=True,
                status="placeholder",
                raw={"placeholder_url": "https://via.placeholder.com/512.png?text=fal-placeholder",
                     "kind": kind, "prompt": prompt},
            )

        t0 = self._now()
        body = self._build_body(prompt, params, kind)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                submit = await client.post(
                    f"{self.base_url}/{model}",
                    headers=self._auth_headers(),
                    json=body,
                )
            latency_ms = self._latency_ms(t0)
            if submit.status_code in (200, 201):
                payload = submit.json() if hasattr(submit, "json") else {}
                images, videos = self._extract_media(payload)
                return ProviderResponse(
                    success=True,
                    provider=self.provider_name,
                    model=model,
                    content=str(payload.get("text") or payload.get("output") or ""),
                    images=images,
                    videos=videos,
                    latency_ms=latency_ms,
                    raw=payload,
                    status="succeeded",
                    usage={
                        "prompt_tokens": int(payload.get("prompt_tokens") or 0),
                        "completion_tokens": int(payload.get("completion_tokens") or 0),
                        "total_tokens": int(payload.get("total_tokens") or 0),
                    },
                )
            err_text = getattr(submit, "text", "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"fal submit HTTP {submit.status_code}: {err_text}",
                error_code=str(submit.status_code),
                latency_ms=latency_ms,
                raw={"status_code": submit.status_code},
            )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"fal 异常: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    async def health_check(self) -> ProviderResponse:
        """Verify fal connection by listing known models (cheap)."""
        if not self.has_credentials():
            return ProviderResponse(
                success=True,
                provider=self.provider_name,
                model="",
                content="placeholder",
                status="placeholder",
                is_placeholder=True,
                error="FAL_KEY 未配置 — placeholder 模式",
            )
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._auth_headers(),
                )
            latency_ms = self._latency_ms(t0)
            ok = resp.status_code == 200
            return ProviderResponse(
                success=ok,
                provider=self.provider_name,
                status="ok" if ok else "error",
                latency_ms=latency_ms,
                error="" if ok else f"fal /models HTTP {resp.status_code}",
                error_code="" if ok else str(resp.status_code),
            )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                status="error",
                error=f"fal health 异常: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    # ── Async helper: submit + poll queue (advanced) ───────────────────
    async def submit_and_poll(
        self,
        model: str,
        body: Dict[str, Any],
        max_wait_s: float = 60.0,
        interval_s: float = 0.5,
    ) -> ProviderResponse:
        """Submit to queue mode (``queue.fal.run``), poll status, return final result."""
        if not self.has_credentials():
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                is_placeholder=True,
                error="FAL_KEY 未配置",
            )
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                sub = await client.post(
                    f"{self._queue_url}/{model}",
                    headers=self._auth_headers(),
                    json=body,
                )
                if sub.status_code not in (200, 202):
                    return ProviderResponse(
                        success=False,
                        provider=self.provider_name,
                        model=model,
                        error=f"fal queue submit HTTP {sub.status_code}",
                        error_code=str(sub.status_code),
                    )
                req_id = (sub.json() or {}).get("request_id") or ""
                if not req_id:
                    return ProviderResponse(
                        success=True,
                        provider=self.provider_name,
                        model=model,
                        raw=sub.json() or {},
                        status="succeeded",
                        latency_ms=self._latency_ms(t0),
                    )
                # poll
                import asyncio
                elapsed = 0.0
                while elapsed < max_wait_s:
                    await asyncio.sleep(interval_s)
                    elapsed += interval_s
                    st = await client.get(
                        f"{self._queue_url}/{model}/requests/{req_id}/status",
                        headers=self._auth_headers(),
                    )
                    if st.status_code != 200:
                        continue
                    st_payload = st.json() if hasattr(st, "json") else {}
                    status = st_payload.get("status")
                    if status == "COMPLETED":
                        final = await client.get(
                            f"{self._queue_url}/{model}/requests/{req_id}",
                            headers=self._auth_headers(),
                        )
                        payload = final.json() if final.status_code == 200 else st_payload
                        images, videos = self._extract_media(payload)
                        return ProviderResponse(
                            success=True,
                            provider=self.provider_name,
                            model=model,
                            task_id=req_id,
                            images=images,
                            videos=videos,
                            status="succeeded",
                            raw=payload,
                            latency_ms=self._latency_ms(t0),
                        )
                    if status in ("FAILED", "CANCELED"):
                        return ProviderResponse(
                            success=False,
                            provider=self.provider_name,
                            model=model,
                            task_id=req_id,
                            status=status.lower(),
                            error=f"fal queue {status}",
                            latency_ms=self._latency_ms(t0),
                            raw=st_payload,
                        )
                return ProviderResponse(
                    success=False,
                    provider=self.provider_name,
                    model=model,
                    task_id=req_id,
                    status="timeout",
                    error=f"fal queue 轮询超时 ({max_wait_s}s)",
                    latency_ms=self._latency_ms(t0),
                )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"fal queue 异常: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    # ── Helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _kind_of(model: str) -> str:
        m = model.lower()
        if "video" in m or "wan" in m or "animate" in m:
            return "video"
        if "kokoro" in m or "tts" in m or "whisper" in m:
            return "audio"
        if "sdxl" in m or "flux" in m or "lcm" in m:
            return "image"
        return "image"

    @staticmethod
    def _build_body(prompt: str, params: Mapping[str, Any], kind: str) -> Dict[str, Any]:
        body: Dict[str, Any] = {"prompt": prompt}
        if kind == "image":
            body.setdefault("image_size", params.get("image_size", "square_hd"))
            body.setdefault("num_images", params.get("n", 1))
        elif kind == "video":
            body.setdefault("num_frames", params.get("num_frames", 24))
            body.setdefault("fps", params.get("fps", 8))
        for k, v in params.items():
            if k not in ("model", "kind"):
                body[k] = v
        return body

    @staticmethod
    def _extract_media(payload: Dict[str, Any]) -> tuple:
        images: List[str] = []
        videos: List[str] = []
        if not isinstance(payload, dict):
            return images, videos
        # fal common shapes: {"images":[{"url":...}], "video":{"url":...}}
        for img in payload.get("images") or []:
            if isinstance(img, dict):
                u = img.get("url")
                if u:
                    images.append(u)
            elif isinstance(img, str):
                images.append(img)
        v = payload.get("video")
        if isinstance(v, dict):
            u = v.get("url")
            if u:
                videos.append(u)
        elif isinstance(v, str):
            videos.append(v)
        for k in ("output", "result"):
            val = payload.get(k)
            if isinstance(val, str) and val.startswith("http"):
                if any(ext in val.lower() for ext in (".mp4", ".webm")):
                    videos.append(val)
                else:
                    images.append(val)
        return images, videos


__all__ = ["FalProvider"]
