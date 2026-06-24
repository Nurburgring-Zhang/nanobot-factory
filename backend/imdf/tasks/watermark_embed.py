"""
Async watermark embedding tasks (P2-1-W2)
==========================================

Tasks:
- ``add_text_watermark``  — overlay text on a video file (ffmpeg drawtext).
- ``add_image_watermark`` — overlay a PNG/JPG logo on a video (ffmpeg overlay).
- ``verify_watermark``    — re-probe a video to confirm the embedded watermark.

These are CPU/IO bound wrappers around ``engines.watermark_engine.WatermarkEngine``.
When ffmpeg isn't available the underlying engine raises
``WatermarkEngineUnavailable``; the task catches it and returns a structured
``{"ok": False, "error": "..."}`` payload rather than crashing the worker.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


def _result_to_dict(rec) -> Dict[str, Any]:
    """``WatermarkRecord`` is a dataclass — serialise via __dict__."""
    if rec is None:
        return {"ok": False, "error": "watermark_engine_returned_none"}
    if hasattr(rec, "__dict__"):
        return {"ok": True, **dict(rec.__dict__)}
    return {"ok": True, "value": str(rec)}


@shared_task(name="imdf.tasks.watermark_embed.add_text_watermark", bind=True, acks_late=True)
def add_text_watermark(
    self,
    input_path: str,
    output_path: str,
    text: str,
    position: str = "bottomright",
    font_size: int = 24,
    color: str = "white",
    opacity: float = 0.85,
) -> Dict[str, Any]:
    """Add a text watermark to a video file.

    Note: the underlying engine kwarg is ``font_color`` (not ``color``) — we
    accept ``color`` from callers (more natural) and translate.
    """
    try:
        from engines.watermark_engine import WatermarkEngine
        engine = WatermarkEngine()
        if not engine.available:
            return {"ok": False, "error": "ffmpeg_unavailable", "task_id": self.request.id}

        record = engine.add_text_watermark(
            input_path=input_path,
            output_path=output_path,
            text=text,
            position=position,
            opacity=float(opacity),
            font_size=int(font_size),
            font_color=color,
        )
        return {**_result_to_dict(record), "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        logger.exception("add_text_watermark failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.watermark_embed.add_image_watermark", bind=True, acks_late=True)
def add_image_watermark(
    self,
    input_path: str,
    output_path: str,
    logo_path: str,
    position: str = "bottomright",
    scale: float = 0.15,
    opacity: float = 0.9,
) -> Dict[str, Any]:
    """Overlay a PNG/JPG logo on a video."""
    try:
        from engines.watermark_engine import WatermarkEngine
        engine = WatermarkEngine()
        if not engine.available:
            return {"ok": False, "error": "ffmpeg_unavailable", "task_id": self.request.id}

        record = engine.add_image_watermark(
            input_path=input_path,
            output_path=output_path,
            logo_path=logo_path,
            position=position,
            scale=float(scale),
            opacity=float(opacity),
        )
        return {**_result_to_dict(record), "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        logger.exception("add_image_watermark failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.watermark_embed.verify_watermark", bind=True)
def verify_watermark(self, video_path: str, watermark_id: Optional[str] = None) -> Dict[str, Any]:
    """Verify that a video carries the expected watermark id."""
    try:
        from engines.watermark_engine import WatermarkEngine
        engine = WatermarkEngine()
        if not engine.available:
            return {"ok": False, "error": "ffmpeg_unavailable", "task_id": self.request.id}
        ok = engine.verify_watermark(video_path=video_path, watermark_id=watermark_id)
        return {
            "ok": bool(ok),
            "video_path": video_path,
            "watermark_id": watermark_id,
            "verified": bool(ok),
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}
