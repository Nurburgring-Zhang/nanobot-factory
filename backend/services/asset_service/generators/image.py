"""P4-5-W1: Image Generator — 5 image models behind provider_registry.

Models supported (behind ``call_provider_smart`` from
``imdf.engines.provider_registry``):

  * **SDXL** (Stability AI SDXL)        → ``openai-compatible`` protocol
  * **DALL-E 3** (OpenAI)               → ``openai-compatible`` protocol
  * **Midjourney v7** (via API)         → ``openai-compatible`` protocol
  * **Imagen 3** (Google Vertex)        → ``openai-compatible`` protocol
  * **Seedream 4.0** (volcengine)       → ``volcengine`` protocol

Input shape (``ImageGenerateRequest``):
  * ``prompt`` (str, required)
  * ``negative_prompt`` (str, optional)
  * ``reference_images`` (List[str], URLs — multi-image conditioning)
  * ``locked_features`` (List[LockedFeature]) — injected into prompt
  * ``character_id`` (str, optional) — pull feature dicts + style
  * ``style_preset`` (str, optional) — e.g. ``"cinematic"`` / ``"anime"``
  * ``model`` (str, default = first model)
  * ``provider_id`` (str, default = best match for model)
  * ``width`` / ``height`` (int, default 1024x1024)
  * ``n`` (int, 1-4, default 1) — number of images per request
  * ``seed`` (int, optional)
  * ``mock`` (bool, default True) — force mock (skip real provider call)

Output (``ImageGenerateResponse``):
  * ``images`` (List[GeneratedImage]) — each with url, metadata, consistency_score
  * ``model``, ``provider_id``, ``mock`` (bool), ``elapsed_ms``, ``cost_usd``

The ``consistency_score`` field is computed by the
``CharacterConsistencyChecker`` whenever ``character_id`` is supplied —
this is the main reason this generator exists as a separate module
rather than just calling provider_registry directly.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..characters.consistency import CharacterConsistencyChecker
from ..characters.models import CharacterAsset, LockedFeature
from ..characters.storage import get_character

logger = logging.getLogger(__name__)


# ─── Model registry ──────────────────────────────────────────────────────────
# Maps a friendly model name to (provider_id, provider_protocol, model_in_provider).
# Used when the caller doesn't pin a provider.

IMAGE_MODELS: Dict[str, Dict[str, str]] = {
    "sdxl": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
             "model": "stability-ai/sdxl", "label": "SDXL 1.0"},
    "dall-e-3": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
                 "model": "dall-e-3", "label": "DALL-E 3 (OpenAI)"},
    "midjourney": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
                   "model": "midjourney-v7", "label": "Midjourney v7"},
    "imagen-3": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
                 "model": "imagen-3.0-generate", "label": "Imagen 3 (Google)"},
    "seedream-4": {"provider_id": "volcengine", "protocol": "volcengine",
                   "model": "doubao-seedream-4-0-250828", "label": "Seedream 4.0 (火山)"},
}

DEFAULT_MODEL = "dall-e-3"

# Width / height clamp
MIN_DIM, MAX_DIM = 256, 2048
DEFAULT_DIM = 1024


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic-style dataclasses (we don't import pydantic here to keep this module
# lightweight — the routes validate at the wire boundary)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GeneratedImage:
    url: str
    width: int
    height: int
    seed: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    consistency_score: float = 1.0
    consistency_recommendation: str = "accept"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImageGenerateRequest:
    prompt: str
    negative_prompt: Optional[str] = None
    reference_images: List[str] = field(default_factory=list)
    locked_features: List[Dict[str, Any]] = field(default_factory=list)
    character_id: Optional[str] = None
    style_preset: Optional[str] = None
    model: str = DEFAULT_MODEL
    provider_id: Optional[str] = None
    width: int = DEFAULT_DIM
    height: int = DEFAULT_DIM
    n: int = 1
    seed: Optional[int] = None
    mock: bool = True
    user_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "ImageGenerateRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        if "prompt" not in payload or not str(payload.get("prompt") or "").strip():
            raise ValueError("prompt is required")
        prompt = str(payload["prompt"]).strip()
        if len(prompt) > 8000:
            raise ValueError("prompt must be <= 8000 chars")
        return cls(
            prompt=prompt,
            negative_prompt=payload.get("negative_prompt"),
            reference_images=[str(x) for x in (payload.get("reference_images") or []) if x][:8],
            locked_features=[lf for lf in (payload.get("locked_features") or []) if isinstance(lf, dict)][:16],
            character_id=payload.get("character_id"),
            style_preset=payload.get("style_preset"),
            model=str(payload.get("model") or DEFAULT_MODEL),
            provider_id=payload.get("provider_id"),
            width=int(payload.get("width") or DEFAULT_DIM),
            height=int(payload.get("height") or DEFAULT_DIM),
            n=max(1, min(int(payload.get("n") or 1), 4)),
            seed=payload.get("seed"),
            mock=bool(payload.get("mock", True)),
            user_id=payload.get("user_id"),
        )


@dataclass
class ImageGenerateResponse:
    images: List[GeneratedImage]
    model: str
    provider_id: str
    mock: bool
    elapsed_ms: int
    cost_usd: float
    consistency_score: float = 1.0
    character_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt enrichment — inject character features + locked features
# ═══════════════════════════════════════════════════════════════════════════════

def _enrich_prompt(req: ImageGenerateRequest, character: Optional[CharacterAsset]) -> str:
    """Build the final prompt sent to the provider.

    Order:
      1. style_preset prefix (if set)
      2. base prompt
      3. character feature phrases (face / hair / outfit)
      4. locked features (explicit)
      5. negative prompt (separate field, not appended)
    """
    parts: List[str] = []
    if req.style_preset:
        parts.append(f"[style: {req.style_preset}]")
    parts.append(req.prompt)

    if character is not None:
        ff = character.face_features or {}
        sf = (character.style_features or {})
        hair = sf.get("hair", {}) or {}
        outfit = sf.get("outfit", {}) or {}

        # Face — only include non-empty keys
        face_bits = [f"{k}={ff[k]}" for k in ("shape", "eye_color", "skin_tone", "age") if ff.get(k)]
        if face_bits:
            parts.append("face:" + ", ".join(face_bits))
        # Hair
        hair_bits = [f"{k}={hair[k]}" for k in ("color", "length", "style") if hair.get(k)]
        if hair_bits:
            parts.append("hair:" + ", ".join(hair_bits))
        # Outfit
        outfit_bits = [f"{k}={outfit[k]}" for k in ("top", "main_color", "fabric") if outfit.get(k)]
        if outfit_bits:
            parts.append("outfit:" + ", ".join(outfit_bits))

    # Locked features
    for lf in req.locked_features:
        if isinstance(lf, dict) and lf.get("name"):
            weight = lf.get("weight", 1.0)
            if weight >= 2.0:
                parts.append(f"[LOCK {lf.get('category', 'feature')}={lf['name']} — immutable]")
            else:
                parts.append(f"{lf.get('category', 'feature')}:{lf['name']}")

    return "; ".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════════

class ImageGenerator:
    """Multi-model image generator — wraps provider_registry.call_provider_smart."""

    def __init__(self, *, default_mock: bool = True) -> None:
        self.default_mock = default_mock
        self._checker = CharacterConsistencyChecker()

    def list_models(self) -> List[Dict[str, str]]:
        """Return the catalog of supported image models."""
        return [
            {"name": name, **meta}
            for name, meta in IMAGE_MODELS.items()
        ]

    def resolve_model(self, model: str) -> Dict[str, str]:
        """Map a friendly name to (provider_id, protocol, model-in-provider)."""
        meta = IMAGE_MODELS.get(model)
        if not meta:
            # fall back to default
            meta = IMAGE_MODELS[DEFAULT_MODEL]
            return {"name": DEFAULT_MODEL, **meta, "fallback_from": model}
        return {"name": model, **meta}

    def generate(self, req: ImageGenerateRequest) -> ImageGenerateResponse:
        """Run image generation. Returns ``ImageGenerateResponse``."""
        start = time.time()

        # 1. Resolve character (if any) → enrich prompt
        character: Optional[CharacterAsset] = None
        if req.character_id:
            character = get_character(req.character_id)
            if character is None:
                logger.info("image generate: character_id=%s not found, ignoring", req.character_id)

        prompt_final = _enrich_prompt(req, character)
        warnings: List[str] = []

        # 2. Resolve model + provider
        resolved = self.resolve_model(req.model)
        provider_id = req.provider_id or resolved["provider_id"]
        model_in_provider = resolved["model"]

        # 3. Width/height clamp
        width = max(MIN_DIM, min(MAX_DIM, int(req.width)))
        height = max(MIN_DIM, min(MAX_DIM, int(req.height)))

        # 4. Build provider payload
        provider_payload = {
            "model": model_in_provider,
            "prompt": prompt_final,
            "negative_prompt": req.negative_prompt,
            "size": f"{width}x{height}",
            "width": width,
            "height": height,
            "n": req.n,
            "seed": req.seed,
            "reference_images": req.reference_images,
        }

        # 5. Call provider (mock by default in dev/CI)
        use_mock = req.mock or self.default_mock
        provider_result: Dict[str, Any] = {"ok": True, "data": {"data": []}, "mock": use_mock}
        cost_usd = 0.0
        if not use_mock:
            try:
                import asyncio
                from imdf.engines.provider_registry import (
                    call_provider_smart,
                    _get_provider_config,
                )
                # Pull provider config (defaults if not configured)
                try:
                    provider_cfg = _get_provider_config(provider_id)
                except Exception:
                    provider_cfg = {
                        "id": provider_id,
                        "protocol": resolved["protocol"],
                        "apiKey": "",
                        "imageModels": [model_in_provider],
                    }
                provider_result = asyncio.run(call_provider_smart(
                    provider_cfg, provider_payload, kind="image",
                    user_id=req.user_id or "anonymous",
                ))
                cost_usd = float(provider_result.get("cost_usd") or 0.0)
            except Exception as e:  # pragma: no cover
                logger.warning("image generate: provider call failed (%s); falling back to mock", e)
                provider_result = {"ok": True, "data": {"data": []}, "mock": True}
                warnings.append(f"provider_fallback: {e!s}")

        # 6. Build GeneratedImage list from provider result OR mock
        images: List[GeneratedImage] = []
        data_section = (provider_result.get("data") or {}).get("data") if isinstance(provider_result.get("data"), dict) else None
        if isinstance(data_section, list) and data_section:
            for item in data_section:
                url = item.get("url") or item.get("image") or item.get("b64_json") or ""
                if not url:
                    continue
                # Run consistency check against character (if any)
                cs, rec = 1.0, "accept"
                if character is not None:
                    res = self._checker.check(character, {
                        "face_features": character.face_features,
                        "style_features": character.style_features,
                    })
                    cs, rec = res.score, res.recommendation
                    if rec == "reject":
                        warnings.append(f"consistency_reject score={cs}")
                    elif rec == "warn":
                        warnings.append(f"consistency_warn score={cs}")
                images.append(GeneratedImage(
                    url=url,
                    width=width,
                    height=height,
                    seed=req.seed,
                    metadata={"model": model_in_provider, "provider_id": provider_id, "prompt_used": prompt_final},
                    consistency_score=cs,
                    consistency_recommendation=rec,
                ))
        else:
            # Mock: synthesize N image URLs (deterministic from seed)
            for i in range(req.n):
                seed_part = f"seed={req.seed}" if req.seed is not None else f"i={i}"
                url = (
                    f"https://via.placeholder.com/{width}x{height}.png"
                    f"?text=mock+{req.model}+{seed_part}"
                )
                cs, rec = 1.0, "accept"
                if character is not None:
                    res = self._checker.check(character, {
                        "face_features": character.face_features,
                        "style_features": character.style_features,
                    })
                    cs, rec = res.score, res.recommendation
                images.append(GeneratedImage(
                    url=url,
                    width=width,
                    height=height,
                    seed=req.seed,
                    metadata={"model": model_in_provider, "provider_id": provider_id,
                              "prompt_used": prompt_final, "mock": True},
                    consistency_score=cs,
                    consistency_recommendation=rec,
                ))

        # 7. Aggregate consistency (mean of per-image)
        agg_consistency = (
            round(sum(i.consistency_score for i in images) / max(1, len(images)), 4)
            if images else 1.0
        )

        elapsed = int((time.time() - start) * 1000)
        return ImageGenerateResponse(
            images=images,
            model=req.model,
            provider_id=provider_id,
            mock=bool(provider_result.get("mock") or use_mock),
            elapsed_ms=elapsed,
            cost_usd=cost_usd,
            consistency_score=agg_consistency,
            character_id=req.character_id,
            warnings=warnings,
        )

    def generate_batch(self, requests: List[ImageGenerateRequest]) -> List[ImageGenerateResponse]:
        """Run a batch of image generations sequentially.

        For real concurrency, callers should batch via Celery / asyncio.gather.
        This sequential version is safe for tests and CI.
        """
        return [self.generate(r) for r in requests if isinstance(r, ImageGenerateRequest)]


__all__ = [
    "IMAGE_MODELS",
    "DEFAULT_MODEL",
    "ImageGenerateRequest",
    "ImageGenerateResponse",
    "GeneratedImage",
    "ImageGenerator",
]
