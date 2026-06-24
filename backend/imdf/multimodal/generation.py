"""P4-7-W2: CrossModalGeneration — text (+ optional reference images) → media.

Reuses the 4 providers wired up in P2-3 (openai_compatible / volcengine /
comfyui / jimeng_cli) and the 18 generators from P4-5.  Heavy model
dependencies are imported lazily — tests exercise the deterministic stub path.

Public API:
* ``generate(req) -> GenerationResponse``   — single call
* ``generate_batch(reqs)``                  — fan out
* ``available_providers()``                 — list of provider names that loaded
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .embedders import CLIPEmbedder
from .types import (
    GenerationCandidate,
    GenerationRequest,
    GenerationResponse,
    GenerationTarget,
    MediaRef,
    ModalKind,
)

logger = logging.getLogger(__name__)


# ── provider registry (lazy import of P2-3 / P4-5 integrations) ────────────
@dataclass
class _ProviderSpec:
    name: str
    supported: List[GenerationTarget]
    load: Callable[[], Optional[Any]]  # returns a callable (text, ref_images, params) -> [{url, mime, ...}]


def _try_load_openai_compatible():
    try:  # pragma: no cover - depends on P2-3 / P4-5 files
        from imdf.providers.openai_compatible import generate as _g  # type: ignore
        return _g
    except Exception as exc:
        logger.debug("openai_compatible provider not available: %s", exc)
        return None


def _try_load_volcengine():
    try:
        from imdf.providers.volcengine import generate as _g  # type: ignore
        return _g
    except Exception as exc:
        logger.debug("volcengine provider not available: %s", exc)
        return None


def _try_load_comfyui():
    try:
        from imdf.providers.comfyui import generate as _g  # type: ignore
        return _g
    except Exception as exc:
        logger.debug("comfyui provider not available: %s", exc)
        return None


def _try_load_jimeng_cli():
    try:
        from imdf.providers.jimeng_cli import generate as _g  # type: ignore
        return _g
    except Exception as exc:
        logger.debug("jimeng_cli provider not available: %s", exc)
        return None


_PROVIDERS: List[_ProviderSpec] = [
    _ProviderSpec("openai_compatible", [GenerationTarget.IMAGE, GenerationTarget.AUDIO], _try_load_openai_compatible),
    _ProviderSpec("volcengine", [GenerationTarget.IMAGE, GenerationTarget.VIDEO], _try_load_volcengine),
    _ProviderSpec("comfyui", [GenerationTarget.IMAGE, GenerationTarget.VIDEO], _try_load_comfyui),
    _ProviderSpec("jimeng_cli", [GenerationTarget.IMAGE], _try_load_jimeng_cli),
]


def _stub_candidates(req: GenerationRequest) -> List[GenerationCandidate]:
    """Deterministic stub: emit 1-4 candidates keyed by request_id + target."""
    n = max(1, min(int(req.params.get("n", 1)), 4))
    out: List[GenerationCandidate] = []
    for i in range(n):
        seed = (hash((req.request_id, i)) & 0xFFFFFFFF)
        if req.target == GenerationTarget.IMAGE:
            w, h = 1024, 1024
            url = f"stub://image/{req.request_id}/{i}.png?seed={seed}&w={w}&h={h}"
            out.append(GenerationCandidate(modality=GenerationTarget.IMAGE, url=url, mime="image/png", seed=seed, width=w, height=h))
        elif req.target == GenerationTarget.VIDEO:
            url = f"stub://video/{req.request_id}/{i}.mp4?seed={seed}"
            out.append(GenerationCandidate(modality=GenerationTarget.VIDEO, url=url, mime="video/mp4", seed=seed, duration_sec=4.0))
        elif req.target == GenerationTarget.AUDIO:
            url = f"stub://audio/{req.request_id}/{i}.wav?seed={seed}"
            out.append(GenerationCandidate(modality=GenerationTarget.AUDIO, url=url, mime="audio/wav", seed=seed, duration_sec=10.0))
        else:  # TEXT
            url = f"stub://text/{req.request_id}/{i}.txt"
            out.append(GenerationCandidate(modality=GenerationTarget.TEXT, url=url, mime="text/plain"))
    return out


# ── main engine ────────────────────────────────────────────────────────────
class CrossModalGeneration:
    def __init__(self) -> None:
        self.clip = CLIPEmbedder()
        self._cache: Dict[str, GenerationResponse] = {}
        self._providers: Dict[str, Any] = {}
        # In test mode, skip provider import scans entirely — they're heavy and
        # not needed for the deterministic stub fallback used in unit tests.
        if os.environ.get("MULTIMODAL_GENERATION_DISABLE_PROVIDERS") == "1":
            return
        for spec in _PROVIDERS:
            try:
                impl = spec.load()
                if impl is not None:
                    self._providers[spec.name] = impl
            except Exception as exc:
                logger.debug("provider %s load raised: %s", spec.name, exc)

    def available_providers(self) -> List[Dict[str, Any]]:
        return [
            {"name": s.name, "supported": [t.value for t in s.supported], "loaded": s.name in self._providers}
            for s in _PROVIDERS
        ]

    # ── core entry ──────────────────────────────────────────────────────
    def generate(self, req: GenerationRequest) -> GenerationResponse:
        t0 = time.time()
        provider_name = req.provider or self._default_provider_for(req.target)
        impl = self._providers.get(provider_name) if provider_name else None
        cands: List[GenerationCandidate] = []
        if impl is not None:
            try:
                raw = impl(
                    text=req.text,
                    ref_images=[m.to_dict() for m in req.ref_images],
                    target=req.target.value,
                    params=req.params,
                )
                # provider is expected to return a list of dicts
                if isinstance(raw, dict) and "candidates" in raw:
                    raw = raw["candidates"]
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            cands.append(GenerationCandidate(
                                modality=req.target,
                                url=item.get("url", ""),
                                mime=item.get("mime", ""),
                                seed=item.get("seed"),
                                width=item.get("width"),
                                height=item.get("height"),
                                duration_sec=item.get("duration_sec"),
                                meta=item.get("meta", {}),
                            ))
                elif isinstance(raw, dict) and raw.get("url"):
                    cands.append(GenerationCandidate(modality=req.target, url=raw["url"], mime=raw.get("mime", "")))
            except Exception as exc:
                logger.warning("provider %s failed, falling back to stub: %s", provider_name, exc)
        if not cands:
            cands = _stub_candidates(req)
            provider_name = provider_name or "stub"
        resp = GenerationResponse(
            request_id=req.request_id,
            target=req.target,
            candidates=cands,
            provider=provider_name or "stub",
            elapsed_ms=round((time.time() - t0) * 1000, 2),
        )
        self._cache[req.request_id] = resp
        return resp

    def generate_batch(self, reqs: List[GenerationRequest]) -> List[GenerationResponse]:
        return [self.generate(r) for r in reqs]

    # ── helpers ─────────────────────────────────────────────────────────
    def _default_provider_for(self, target: GenerationTarget) -> str:
        # prefer already-loaded provider in stable order
        order = [s for s in _PROVIDERS if target in s.supported]
        for spec in order:
            if spec.name in self._providers:
                return spec.name
        return "stub"