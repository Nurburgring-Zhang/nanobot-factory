"""
Async rendering tasks for VideoEngine (P2-1-W2)
=================================================

`render_project` — process a full VideoProject (multiple segments) asynchronously.
`render_segment` — render a single segment.
`render_html_segment` — convenience task used by the FastAPI endpoint that
                        takes the pre-built HTML and the seg metadata.

All tasks return JSON-serialisable dicts so Celery's JSON serializer can handle
the results without unpickling.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import shared_task

# Make sure imdf/ and backend/ are on sys.path so `from engines.X import ...`
# (i.e. ``imdf.engines.X`` via the imdf package) and `from imdf.engines.X import ...`
# both work, regardless of which directory celery was launched from.
_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


def _project_from_dict(d: Dict[str, Any]):
    """Materialise a VideoProject from a JSON-friendly dict."""
    from engines.video_engine import (
        VideoProject,
        VideoSegment,
        VideoEngineType,
        AspectRatio,
        TTSProvider,
    )

    aspect = d.get("aspect_ratio")
    if isinstance(aspect, str):
        try:
            aspect = AspectRatio(aspect)
        except ValueError:
            aspect = AspectRatio.LANDSCAPE_16_9
    elif aspect is None:
        aspect = AspectRatio.LANDSCAPE_16_9

    tts = d.get("tts_provider")
    if isinstance(tts, str):
        try:
            tts = TTSProvider(tts)
        except ValueError:
            tts = TTSProvider.MINIMAX
    elif tts is None:
        tts = TTSProvider.MINIMAX

    segments: List[VideoSegment] = []
    for raw in d.get("segments", []) or []:
        engine_raw = raw.get("engine", "html-video")
        try:
            engine = VideoEngineType(engine_raw)
        except ValueError:
            engine = VideoEngineType.HTML_VIDEO
        segments.append(
            VideoSegment(
                segment_id=raw.get("segment_id", ""),
                name=raw.get("name", ""),
                engine=engine,
                duration=float(raw.get("duration", 5.0) or 5.0),
                narration=raw.get("narration", "") or "",
                subtitle=raw.get("subtitle", "") or "",
                html_content=raw.get("html_content", "") or "",
                template_id=raw.get("template_id", "") or "",
                visual_style=raw.get("visual_style", "") or "",
                bgm_cue=raw.get("bgm_cue", "") or "",
                tts_voice=raw.get("tts_voice", "") or "",
                transition_in=raw.get("transition_in", "cut") or "cut",
                transition_out=raw.get("transition_out", "cut") or "cut",
                characters=list(raw.get("characters", []) or []),
                assets=dict(raw.get("assets", {}) or {}),
                vars_dict=dict(raw.get("vars_dict", {}) or {}),
            )
        )

    return VideoProject(
        title=d.get("title", "") or "",
        description=d.get("description", "") or "",
        aspect_ratio=aspect,
        total_duration=float(d.get("total_duration", 0.0) or 0.0),
        segments=segments,
        tts_provider=tts,
        background_music=d.get("background_music", "") or "",
        output_path=d.get("output_path", "") or "",
        status=d.get("status", "draft") or "draft",
    )


@shared_task(name="imdf.tasks.render_video.render_project", bind=True, acks_late=True)
def render_project(self, project_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Render every segment of a VideoProject.

    Args:
        project_dict: JSON-serialisable VideoProject.

    Returns:
        dict with keys: project_title, total_segments, successes, failures, results.
    """
    from engines.video_engine import VideoEngine

    try:
        project = _project_from_dict(project_dict or {})
        engine = VideoEngine()
        results = engine.render_segments(project)
        successes = sum(1 for r in results if r.get("status") == "success")
        failures = sum(1 for r in results if r.get("status") == "failed")
        return {
            "ok": True,
            "project_title": project.title,
            "total_segments": len(results),
            "successes": successes,
            "failures": failures,
            "results": results,
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("render_project failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.render_video.render_segment", bind=True, acks_late=True)
def render_segment(self, project_dict: Dict[str, Any], segment_index: int = 0) -> Dict[str, Any]:
    """Render a single segment identified by its index in the project."""
    from engines.video_engine import VideoEngine, VideoSegment

    try:
        project = _project_from_dict(project_dict or {})
        engine = VideoEngine()
        segments: List[VideoSegment] = project.segments
        if not segments:
            return {"ok": False, "error": "no segments", "task_id": self.request.id}
        idx = max(0, min(int(segment_index), len(segments) - 1))
        seg = segments[idx]
        html = engine._build_segment_html(seg, project.aspect_ratio) if hasattr(engine, "_build_segment_html") else ""
        # Prefer engine.render_with_html_video as the real path
        try:
            output = engine.render_with_html_video(seg)
        except Exception as inner_exc:
            logger.warning("render_with_html_video failed, falling back: %s", inner_exc)
            output = engine._fallback_html_screenshot(html or "<html></html>", seg.segment_id)
        return {
            "ok": True,
            "segment_id": seg.segment_id,
            "engine": seg.engine.value,
            "output_path": output,
            "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("render_segment failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.render_video.render_html_snapshot", bind=True)
def render_html_snapshot(self, html_content: str, segment_id: str = "anon") -> Dict[str, Any]:
    """Take a single HTML snapshot — used as a low-risk smoke task during bring-up."""
    from engines.video_engine import VideoEngine
    try:
        engine = VideoEngine()
        out_path = engine._fallback_html_screenshot(html_content or "<html></html>", segment_id)
        return {"ok": True, "output_path": out_path, "segment_id": segment_id, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}


def submit_render(project_dict: Dict[str, Any]) -> str:
    """Helper: enqueue render_project and return the Celery task id (sync API)."""
    return render_project.delay(project_dict).id