"""P4-5-W1: generators package — multi-modal asset generation.

Public surface (used by routes.py):
  * ``ImageGenerator`` / ``VideoGenerator`` / ``VoiceGenerator`` /
    ``MusicGenerator`` / ``StoryboardGenerator``
  * Request/Response dataclasses for each modality
  * Model registries (e.g. ``IMAGE_MODELS``) for ``/models`` endpoints
"""
from __future__ import annotations

from .image import (
    DEFAULT_MODEL as IMAGE_DEFAULT_MODEL,
    IMAGE_MODELS,
    GeneratedImage,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageGenerator,
)
from .music import (
    DEFAULT_MODEL as MUSIC_DEFAULT_MODEL,
    MUSIC_MODELS,
    MusicGenerateRequest,
    MusicGenerateResponse,
    MusicGenerator,
    MusicMetadata,
)
from .storyboard import (
    ALLOWED_SHOT_TYPES,
    ALLOWED_STYLE_PRESETS,
    ALLOWED_TRANSITIONS,
    MAX_SHOTS,
    MIN_SHOTS,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
    StoryboardGenerator,
    StoryboardRenderRequest,
    StoryboardRenderResponse,
    StoryboardShot,
)
from .routes import router
from .video import (
    DEFAULT_MODEL as VIDEO_DEFAULT_MODEL,
    RESOLUTION_PRESETS,
    VIDEO_MODELS,
    GeneratedVideo,
    VideoEditRequest,
    VideoEditResponse,
    VideoExtendRequest,
    VideoExtendResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoGenerator,
)
from .voice import (
    DEFAULT_MODEL as VOICE_DEFAULT_MODEL,
    SUPPORTED_LANGUAGES,
    VOICE_MODELS,
    ClonedVoice,
    VoiceCloneRequest,
    VoiceGenerateRequest,
    VoiceGenerateResponse,
    VoiceGenerator,
)

__all__ = [
    # image
    "ImageGenerator", "ImageGenerateRequest", "ImageGenerateResponse", "GeneratedImage",
    "IMAGE_MODELS", "IMAGE_DEFAULT_MODEL",
    # video
    "VideoGenerator", "VideoGenerateRequest", "VideoGenerateResponse", "GeneratedVideo",
    "VideoEditRequest", "VideoEditResponse", "VideoExtendRequest", "VideoExtendResponse",
    "VIDEO_MODELS", "VIDEO_DEFAULT_MODEL", "RESOLUTION_PRESETS",
    # voice
    "VoiceGenerator", "VoiceGenerateRequest", "VoiceGenerateResponse",
    "VoiceCloneRequest", "ClonedVoice",
    "VOICE_MODELS", "VOICE_DEFAULT_MODEL", "SUPPORTED_LANGUAGES",
    # music
    "MusicGenerator", "MusicGenerateRequest", "MusicGenerateResponse", "MusicMetadata",
    "MUSIC_MODELS", "MUSIC_DEFAULT_MODEL",
    # storyboard
    "StoryboardGenerator", "StoryboardGenerateRequest", "StoryboardGenerateResponse",
    "StoryboardRenderRequest", "StoryboardRenderResponse", "StoryboardShot",
    "ALLOWED_SHOT_TYPES", "ALLOWED_TRANSITIONS", "ALLOWED_STYLE_PRESETS",
    "MIN_SHOTS", "MAX_SHOTS",
    # router
    "router",
] 
