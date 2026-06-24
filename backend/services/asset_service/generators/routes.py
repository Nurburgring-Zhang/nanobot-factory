"""P4-5-W1: generator routes — REST surface for multi-modal generation.

Endpoints (all under ``/api/v1/assets``):

  GET  /models                                  — list all generators + models
  GET  /generate/image/models                   — image model catalog
  POST /generate/image                          — image generation (single)
  POST /generate/image/batch                    — image generation (batch)
  GET  /generate/video/models                   — video model catalog
  POST /generate/video                          — video generation
  POST /generate/video/edit/{video_id}          — single-frame edit
  POST /generate/video/extend/{video_id}        — extend video forward
  POST /generate/voice                          — TTS
  POST /voices/clone                            — voice cloning (5-10s sample)
  GET  /voices                                  — list cloned voices (?lang &tag &q)
  GET  /voices/{voice_id}                       — get voice
  DELETE /voices/{voice_id}                     — delete voice
  GET  /generate/music/models                   — music model catalog
  POST /generate/music                          — music generation
  POST /generate/storyboard                     — storyboard decomposition (5-20 shots)
  POST /storyboard/{storyboard_id}/render       — render storyboard (image/video)
  GET  /storyboard/{storyboard_id}              — get cached storyboard
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .image import (
    DEFAULT_MODEL as IMAGE_DEFAULT_MODEL,
    IMAGE_MODELS,
    ImageGenerateRequest,
    ImageGenerator,
)
from .music import (
    DEFAULT_MODEL as MUSIC_DEFAULT_MODEL,
    MUSIC_MODELS,
    MusicGenerateRequest,
    MusicGenerator,
)
from .storyboard import (
    StoryboardGenerateRequest,
    StoryboardGenerator,
    StoryboardRenderRequest,
)
from .video import (
    DEFAULT_MODEL as VIDEO_DEFAULT_MODEL,
    RESOLUTION_PRESETS,
    VIDEO_MODELS,
    VideoEditRequest,
    VideoExtendRequest,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoGenerator,
)
from .voice import (
    DEFAULT_MODEL as VOICE_DEFAULT_MODEL,
    SUPPORTED_LANGUAGES,
    VOICE_MODELS,
    VoiceCloneRequest,
    VoiceGenerator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets", tags=["asset-generators"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop empty / None keys so the request dataclasses can apply defaults."""
    return {k: v for k, v in payload.items() if v is not None and v != ""}


# ─── Meta ────────────────────────────────────────────────────────────────────

@router.get("/models", response_model=Dict[str, Any])
async def list_all_models() -> Dict[str, Any]:
    return {
        "image":  [{"name": n, **m} for n, m in IMAGE_MODELS.items()],
        "video":  [{"name": n, **m} for n, m in VIDEO_MODELS.items()],
        "voice":  [{"name": n, **m} for n, m in VOICE_MODELS.items()],
        "music":  [{"name": n, **m} for n, m in MUSIC_MODELS.items()],
        "defaults": {
            "image": IMAGE_DEFAULT_MODEL,
            "video": VIDEO_DEFAULT_MODEL,
            "voice": VOICE_DEFAULT_MODEL,
            "music": MUSIC_DEFAULT_MODEL,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Image
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/generate/image/models", response_model=List[Dict[str, Any]])
async def image_models() -> List[Dict[str, Any]]:
    return [{"name": n, **m} for n, m in IMAGE_MODELS.items()]


@router.post("/generate/image", response_model=Dict[str, Any])
async def generate_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        req = ImageGenerateRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = ImageGenerator()
    resp = gen.generate(req)
    return resp.to_dict()


@router.post("/generate/image/batch", response_model=List[Dict[str, Any]])
async def generate_image_batch(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payloads, list) or len(payloads) == 0:
        raise HTTPException(status_code=422, detail="payloads must be a non-empty list")
    if len(payloads) > 16:
        raise HTTPException(status_code=422, detail="batch size must be <= 16")
    reqs: List[ImageGenerateRequest] = []
    for p in payloads:
        try:
            reqs.append(ImageGenerateRequest.from_payload(_normalize_payload(p)))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"invalid item in batch: {e!s}")
    gen = ImageGenerator()
    results = gen.generate_batch(reqs)
    return [r.to_dict() for r in results]


# ═══════════════════════════════════════════════════════════════════════════════
# Video
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/generate/video/models", response_model=List[Dict[str, Any]])
async def video_models() -> List[Dict[str, Any]]:
    return [{"name": n, **m} for n, m in VIDEO_MODELS.items()]


@router.post("/generate/video", response_model=Dict[str, Any])
async def generate_video(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        req = VideoGenerateRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = VideoGenerator()
    resp = gen.generate(req)
    return resp.to_dict()


@router.post("/generate/video/edit/{video_id}", response_model=Dict[str, Any])
async def edit_video_frame(video_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"video_id": video_id, **(payload or {})}
    try:
        req = VideoEditRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = VideoGenerator()
    resp = gen.edit_frame(req)
    return resp.to_dict()


@router.post("/generate/video/extend/{video_id}", response_model=Dict[str, Any])
async def extend_video(video_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"video_id": video_id, **(payload or {})}
    try:
        req = VideoExtendRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = VideoGenerator()
    resp = gen.extend(req)
    return resp.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# Voice (TTS + clone + library)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/generate/voice/models", response_model=List[Dict[str, Any]])
async def voice_models() -> List[Dict[str, Any]]:
    return [{"name": n, **m} for n, m in VOICE_MODELS.items()]


@router.get("/generate/voice/languages", response_model=List[str])
async def voice_languages() -> List[str]:
    return sorted(SUPPORTED_LANGUAGES)


@router.post("/generate/voice", response_model=Dict[str, Any])
async def generate_voice(payload: Dict[str, Any]) -> Dict[str, Any]:
    from .voice import VoiceGenerateRequest
    try:
        req = VoiceGenerateRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = VoiceGenerator()
    resp = gen.generate(req)
    return resp.to_dict()


@router.post("/voices/clone", response_model=Dict[str, Any])
async def clone_voice(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        req = VoiceCloneRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = VoiceGenerator()
    owner_id = payload.get("owner_id")
    voice = gen.clone(req, owner_id=owner_id)
    return voice.to_dict()


@router.get("/voices", response_model=List[Dict[str, Any]])
async def list_voices(
    language: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[Dict[str, Any]]:
    gen = VoiceGenerator()
    return [v.to_dict() for v in gen.list_voices(
        language=language, tag=tag, query=query, limit=limit, offset=offset
    )]


@router.get("/voices/{voice_id}", response_model=Dict[str, Any])
async def get_voice(voice_id: str) -> Dict[str, Any]:
    gen = VoiceGenerator()
    v = gen.get_voice(voice_id)
    if v is None:
        raise HTTPException(status_code=404, detail=f"voice not found: {voice_id}")
    return v.to_dict()


@router.delete("/voices/{voice_id}", response_model=Dict[str, Any])
async def delete_voice(voice_id: str) -> Dict[str, Any]:
    gen = VoiceGenerator()
    ok = gen.delete_voice(voice_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"voice not found: {voice_id}")
    return {"deleted": True, "voice_id": voice_id}


# ═══════════════════════════════════════════════════════════════════════════════
# Music
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/generate/music/models", response_model=List[Dict[str, Any]])
async def music_models() -> List[Dict[str, Any]]:
    return [{"name": n, **m} for n, m in MUSIC_MODELS.items()]


@router.post("/generate/music", response_model=Dict[str, Any])
async def generate_music(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        req = MusicGenerateRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = MusicGenerator()
    resp = gen.generate(req)
    return resp.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# Storyboard
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/generate/storyboard", response_model=Dict[str, Any])
async def generate_storyboard(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        req = StoryboardGenerateRequest.from_payload(_normalize_payload(payload))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = StoryboardGenerator()
    resp = gen.generate(req)
    return resp.to_dict()


@router.post("/storyboard/{storyboard_id}/render", response_model=Dict[str, Any])
async def render_storyboard(storyboard_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = {"storyboard_id": storyboard_id, **(payload or {})}
    try:
        req = StoryboardRenderRequest.from_payload(_normalize_payload(body))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    gen = StoryboardGenerator()
    try:
        resp = gen.render(req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return resp.to_dict()


@router.get("/storyboard/{storyboard_id}", response_model=Dict[str, Any])
async def get_storyboard(storyboard_id: str) -> Dict[str, Any]:
    sb = StoryboardGenerator.get_cached(storyboard_id)
    if sb is None:
        raise HTTPException(status_code=404, detail=f"storyboard not found: {storyboard_id}")
    return sb.to_dict()


__all__ = ["router"]
