"""P4-6-W2: Director studio REST surface.

Mounted at ``/api/v1/workflow/director`` by ``workflow_service.main``.

Endpoints
---------
* ``POST /api/v1/workflow/director/session``         — create a session (just the brief)
* ``GET  /api/v1/workflow/director/sessions``        — list sessions
* ``GET  /api/v1/workflow/director/session/{id}``    — get one
* ``POST /api/v1/workflow/director/session/{id}/story``  — run Story director
* ``POST /api/v1/workflow/director/session/{id}/visual`` — run Visual director
* ``POST /api/v1/workflow/director/session/{id}/assemble`` — run Assembly director
* ``POST /api/v1/workflow/director/run``             — full pipeline (story→visual→assembly)
* ``PUT  /api/v1/workflow/director/session/{id}/shots`` — user override shots
* ``GET  /api/v1/workflow/director/llm/info``        — LLM client info
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from . import (
    DirectorState,
    Shot,
    get_director_studio,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow/director", tags=["director"])


# =====================================================================
# Pydantic models
# =====================================================================

class ShotModel(BaseModel):
    shot_id: str = Field(..., min_length=1, max_length=64)
    index: int = 0
    title: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    duration_seconds: float = 5.0
    visual_prompt: str = ""
    voiceover: str = ""
    camera: str = ""
    mood: str = ""

    def to_shot(self) -> Shot:
        return Shot(
            shot_id=self.shot_id, index=self.index, title=self.title,
            description=self.description,
            duration_seconds=self.duration_seconds,
            visual_prompt=self.visual_prompt,
            voiceover=self.voiceover, camera=self.camera, mood=self.mood,
        )


class CreateSession(BaseModel):
    brief: str = Field(..., min_length=1, max_length=2048)
    shot_count: Optional[int] = Field(default=None, ge=1, le=50)

    @field_validator("brief")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("brief must be non-empty")
        return v


class RunFull(BaseModel):
    brief: str = Field(..., min_length=1, max_length=2048)
    shot_count: Optional[int] = Field(default=None, ge=1, le=50)


class OverrideShots(BaseModel):
    shots: List[ShotModel] = Field(..., min_length=1, max_length=100)


# =====================================================================
# Session CRUD
# =====================================================================

@router.post("/session", status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSession) -> Dict[str, Any]:
    studio = get_director_studio()
    sess = studio.create_session(body.brief, shot_count=body.shot_count)
    return sess.to_dict()


@router.get("/sessions")
async def list_sessions() -> Dict[str, Any]:
    studio = get_director_studio()
    return {
        "total": len(studio.list_sessions()),
        "items": [s.to_dict() for s in studio.list_sessions()],
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    studio = get_director_studio()
    sess = studio.get_session(session_id)
    if sess is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"session_not_found: {session_id}")
    return sess.to_dict()


@router.put("/session/{session_id}/shots")
async def override_shots(session_id: str,
                         body: OverrideShots) -> Dict[str, Any]:
    """User intervention: edit the storyboard before / after visual step."""
    studio = get_director_studio()
    ok = studio.update_shots(session_id, [s.to_shot() for s in body.shots])
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"session_not_found: {session_id}")
    sess = studio.get_session(session_id)
    return sess.to_dict()


# =====================================================================
# Story / Visual / Assembly (one-step endpoints)
# =====================================================================

@router.post("/session/{session_id}/story")
async def run_story(session_id: str) -> Dict[str, Any]:
    studio = get_director_studio()
    try:
        sess = await studio.run_story(session_id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"session_not_found: {session_id}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"story_failed: {e}")
    return sess.to_dict()


@router.post("/session/{session_id}/visual")
async def run_visual(session_id: str) -> Dict[str, Any]:
    studio = get_director_studio()
    try:
        sess = await studio.run_visual(session_id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"session_not_found: {session_id}")
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"visual_failed: {e}")
    return sess.to_dict()


@router.post("/session/{session_id}/assemble")
async def run_assembly(session_id: str) -> Dict[str, Any]:
    studio = get_director_studio()
    try:
        sess = await studio.run_assembly(session_id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"session_not_found: {session_id}")
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"assembly_failed: {e}")
    return sess.to_dict()


# =====================================================================
# Full pipeline (one-shot)
# =====================================================================

@router.post("/run")
async def run_full(body: RunFull) -> Dict[str, Any]:
    studio = get_director_studio()
    try:
        sess = await studio.run_full(body.brief, shot_count=body.shot_count)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"pipeline_failed: {e}")
    return sess.to_dict()


# =====================================================================
# Meta
# =====================================================================

@router.get("/llm/info")
async def llm_info() -> Dict[str, Any]:
    studio = get_director_studio()
    return {
        "model": studio.llm.model,
        "deterministic": True,
        "supported_directors": ["story", "visual", "assembly"],
        "supports_pause_resume": True,
        "supports_user_override": True,
    }


@router.get("/healthz")
async def director_health() -> Dict[str, Any]:
    studio = get_director_studio()
    sessions = studio.list_sessions()
    by_state: Dict[str, int] = {}
    for s in sessions:
        for k in ("state", "story_state", "visual_state", "assembly_state"):
            v = getattr(s, k).value
            by_state[v] = by_state.get(v, 0) + 1
    return {
        "service": "director-studio",
        "status": "ok",
        "sessions": len(sessions),
        "by_state": by_state,
    }


__all__ = ["router"]
