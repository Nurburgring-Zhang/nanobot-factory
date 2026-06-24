"""P4-8-W1: Multimodal adapter for the skills framework.

Lets a Skill accept multimodal inputs (image / audio / video / file)
through the platform's :class:`MultimodalAdapter`.  Adapters are added
to :data:`MULTIMODAL_ADAPTERS` keyed by mime-type prefix.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


MULTIMODAL_ADAPTERS: Dict[str, Any] = {}


def register_skill_multimodal() -> None:
    """Register handlers for image / audio / video / file MIME prefixes."""
    # Lazy import — multimodal_adapter may not be present in minimal envs.
    try:
        from common.multimodal_adapter import (  # type: ignore
            MultimodalAdapter,
            register_modality_handler,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("multimodal_adapter not available: %s", exc)
        return

    def _image_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "image",
            "size_bytes": len(base64.b64decode(payload.get("data", b"") or b"") or b""),
            "mime": payload.get("mime", "image/*"),
            "caption": payload.get("caption", ""),
        }

    def _audio_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "audio",
            "duration_s": float(payload.get("duration", 0.0)),
            "transcript": payload.get("transcript", ""),
        }

    def _video_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "video",
            "duration_s": float(payload.get("duration", 0.0)),
            "fps": float(payload.get("fps", 30)),
        }

    def _file_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "file",
            "path": payload.get("path", ""),
            "size": payload.get("size", 0),
        }

    for prefix, handler in (
        ("image/", _image_handler),
        ("audio/", _audio_handler),
        ("video/", _video_handler),
        ("file/", _file_handler),
    ):
        try:
            register_modality_handler(prefix, handler)
            MULTIMODAL_ADAPTERS[prefix] = handler
            logger.info("registered skill multimodal handler for %s", prefix)
        except Exception as exc:  # noqa: BLE001
            logger.warning("multimodal register failed for %s: %s", prefix, exc)


__all__ = ["register_skill_multimodal", "MULTIMODAL_ADAPTERS"]