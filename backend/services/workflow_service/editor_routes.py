"""P4-6-W1 Editor Routes — FastAPI router for video editor.

Mounted at ``/api/v1/workflow/editor`` (singular 'workflow' to mirror
the existing ``/api/v1/workflow/templates`` surface from
``templates_routes.py``).

Endpoints:
  GET    /transitions                 list 12 transitions
  GET    /effects                     list 16 effects
  GET    /montages                    list 5 montages + time modes
  GET    /render/codecs               list codecs + resolutions
  POST   /cut                         execute a cut-batch
  POST   /detect_cuts                 auto-detect cut points
  POST   /detect_silence              VAD silence detection
  POST   /keyframes                   extract keyframes
  POST   /transition/{clip_id}        apply a transition
  POST   /effect/{clip_id}            apply an effect
  POST   /montage                     apply a montage plan
  POST   /bpm_sync                    BPM → cut points
  POST   /render                      start a render
  GET    /render/{id}/progress        get render progress
  POST   /render/{id}/cancel          cancel a render
  GET    /projects                    list projects
  POST   /projects                    create a project
  GET    /projects/{id}               get one project
  PUT    /projects/{id}               update project
  DELETE /projects/{id}               delete project
  POST   /projects/{id}/snapshot      take a snapshot
  POST   /projects/{id}/snapshot/{sid}/restore
                                       restore a snapshot
  POST   /projects/{id}/undo          undo
  POST   /projects/{id}/redo          redo
  POST   /projects/{id}/lock          acquire collab lock
  POST   /projects/{id}/unlock        release collab lock
  POST   /projects/{id}/heartbeat     refresh lock TTL
  POST   /projects/{id}/load_template load a workflow template
  WS     /render/{id}/ws              live progress WebSocket
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, BackgroundTasks, HTTPException, WebSocket,
                     WebSocketDisconnect, status)
from pydantic import BaseModel, Field, field_validator

from .editor.cut import (CUT_OPERATIONS, CutEngine, detect_cut_points,
                       detect_silence_segments, extract_keyframes,
                       list_cut_operations)
from .editor.effect import EFFECT_CATALOG, EffectEngine, list_effects
from .editor.montage import (MONTAGE_TIME_MODES, MONTAGE_TYPES,
                             MontageEngine, bpm_to_cut_points,
                             list_montage_types, list_time_modes)
from .editor.project import ProjectStore, get_project_store
from .editor.render import (RENDER_CODECS, RENDER_RESOLUTIONS,
                            RenderEngine, RenderStatus, get_render_engine)
from .editor.transition import (EASING_FUNCTIONS, TRANSITION_TYPES,
                                TransitionEngine, list_easing_functions,
                                list_transitions)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow/editor",
                   tags=["workflow-editor"])


# =====================================================================
# Pydantic models
# =====================================================================

class TimelineModel(BaseModel):
    clips: List[Dict[str, Any]] = Field(default_factory=list)
    cuts: List[Dict[str, Any]] = Field(default_factory=list)
    transitions: List[Dict[str, Any]] = Field(default_factory=list)
    effects: List[Dict[str, Any]] = Field(default_factory=list)


class CutOpModel(BaseModel):
    op: str
    params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("op")
    @classmethod
    def _v_op(cls, v: str) -> str:
        v = v.strip()
        if v not in CUT_OPERATIONS:
            raise ValueError(
                f"op must be one of {CUT_OPERATIONS}, got {v!r}")
        return v


class CutBatchModel(BaseModel):
    timeline: TimelineModel
    operations: List[CutOpModel] = Field(default_factory=list)


class DetectCutsModel(BaseModel):
    frames: List[float] = Field(..., min_length=1)
    threshold: float = Field(0.35, gt=0.0, le=1.0)


class DetectSilenceModel(BaseModel):
    amplitudes: List[float] = Field(..., min_length=1)
    min_silence_sec: float = Field(0.5, ge=0.0, le=600.0)
    threshold: float = Field(0.05, ge=0.0, le=1.0)


class KeyframesModel(BaseModel):
    timestamps: List[float] = Field(default_factory=list)
    method: str = Field(default="scene_change")
    interval_sec: float = Field(default=1.0, gt=0.0, le=600.0)

    @field_validator("method")
    @classmethod
    def _v_method(cls, v: str) -> str:
        v = v.strip()
        if v not in ("scene_change", "i_frame", "uniform"):
            raise ValueError("method must be scene_change/i_frame/uniform")
        return v


class TransitionModel(BaseModel):
    from_clip: str = Field(..., min_length=1, max_length=128)
    to_clip: str = Field(..., min_length=1, max_length=128)
    type: str = Field(default="fade")
    duration: float = Field(default=0.5, gt=0.0, le=10.0)
    easing: str = Field(default="ease-in-out")
    color: str = Field(default="black", max_length=32)
    direction: str = Field(default="left", max_length=32)

    @field_validator("type")
    @classmethod
    def _v_type(cls, v: str) -> str:
        v = v.strip()
        if v not in TRANSITION_TYPES:
            raise ValueError(
                f"type must be one of {TRANSITION_TYPES}")
        return v

    @field_validator("easing")
    @classmethod
    def _v_easing(cls, v: str) -> str:
        v = v.strip()
        if v not in EASING_FUNCTIONS:
            raise ValueError(
                f"easing must be one of {EASING_FUNCTIONS}")
        return v


class EffectModel(BaseModel):
    type: str
    intensity: Optional[float] = None
    params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _v_type(cls, v: str) -> str:
        v = v.strip()
        if v not in EFFECT_CATALOG:
            raise ValueError(
                f"type must be one of {list(EFFECT_CATALOG.keys())}")
        return v


class MontageModel(BaseModel):
    clips: List[str] = Field(..., min_length=1)
    type: str = Field(default="sequential")
    time_mode: str = Field(default="linear")
    layout: str = Field(default="split_screen")
    bpm: Optional[int] = Field(default=None, ge=20, le=300)
    per_clip_sec: float = Field(default=2.0, gt=0.0, le=600.0)

    @field_validator("type")
    @classmethod
    def _v_type(cls, v: str) -> str:
        v = v.strip()
        if v not in MONTAGE_TYPES:
            raise ValueError(f"type must be one of {MONTAGE_TYPES}")
        return v

    @field_validator("time_mode")
    @classmethod
    def _v_tm(cls, v: str) -> str:
        v = v.strip()
        if v not in MONTAGE_TIME_MODES:
            raise ValueError(
                f"time_mode must be one of {MONTAGE_TIME_MODES}")
        return v


class BPMSyncModel(BaseModel):
    bpm: int = Field(..., ge=20, le=300)
    clip_count: int = Field(..., ge=1, le=1000)
    offset: float = Field(default=0.0, ge=0.0, le=600.0)


class RenderModel(BaseModel):
    timeline: TimelineModel
    codec: str = Field(default="h264")
    resolution: str = Field(default="1080p")
    bitrate_kbps: int = Field(default=5000, ge=100, le=200000)
    output_name: Optional[str] = Field(default=None, max_length=128)
    sync: bool = Field(default=False, description="Wait for completion")
    use_ffmpeg: bool = Field(default=False,
                              description="Actually invoke ffmpeg")

    @field_validator("codec")
    @classmethod
    def _v_codec(cls, v: str) -> str:
        v = v.strip()
        if v not in RENDER_CODECS:
            raise ValueError(f"codec must be one of {list(RENDER_CODECS)}")
        return v

    @field_validator("resolution")
    @classmethod
    def _v_res(cls, v: str) -> str:
        v = v.strip()
        if v not in RENDER_RESOLUTIONS:
            raise ValueError(
                f"resolution must be one of {list(RENDER_RESOLUTIONS)}")
        return v


class ProjectCreateModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    owner: str = Field(default="system", max_length=64)
    template_id: Optional[str] = Field(default=None, max_length=128)
    timeline: Optional[TimelineModel] = None


class ProjectUpdateModel(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    timeline: Optional[TimelineModel] = None
    status: Optional[str] = Field(default=None, max_length=32)
    output_url: Optional[str] = Field(default=None, max_length=512)
    expected_version: Optional[int] = Field(default=None, ge=1)


class SnapshotModel(BaseModel):
    label: str = Field(default="", max_length=128)


class LockModel(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    ttl_sec: Optional[float] = Field(default=None, gt=0.0, le=86400.0)


class LoadTemplateModel(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=128)


# =====================================================================
# Singleton holders
# =====================================================================

def _cut() -> CutEngine:
    return CutEngine()


def _trans() -> TransitionEngine:
    return TransitionEngine()


def _eff() -> EffectEngine:
    return EffectEngine()


def _mont() -> MontageEngine:
    return MontageEngine()


def _store() -> ProjectStore:
    return get_project_store()


def _render() -> RenderEngine:
    return get_render_engine()


def _http_400(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=msg)


def _http_404(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=msg)


# =====================================================================
# Catalogue endpoints
# =====================================================================

@router.get("/transitions")
async def list_transitions_endpoint() -> Dict[str, Any]:
    return {
        "total": len(TRANSITION_TYPES),
        "items": list_transitions(),
        "easing_functions": list_easing_functions(),
    }


@router.get("/effects")
async def list_effects_endpoint() -> Dict[str, Any]:
    return {
        "total": len(EFFECT_CATALOG),
        "items": list_effects(),
    }


@router.get("/montages")
async def list_montages_endpoint() -> Dict[str, Any]:
    return {
        "total_montages": len(MONTAGE_TYPES),
        "total_time_modes": len(MONTAGE_TIME_MODES),
        "montages": list_montage_types(),
        "time_modes": list_time_modes(),
    }


@router.get("/render/codecs")
async def list_render_options() -> Dict[str, Any]:
    return {
        "codecs": [{"id": k, "ffmpeg_id": v}
                   for k, v in RENDER_CODECS.items()],
        "resolutions": [{"id": k, **v}
                        for k, v in RENDER_RESOLUTIONS.items()],
    }


@router.get("/cut/operations")
async def list_cut_ops() -> Dict[str, Any]:
    return {
        "total": len(CUT_OPERATIONS),
        "items": list_cut_operations(),
    }


# =====================================================================
# Cut engine
# =====================================================================

@router.post("/cut")
async def run_cut_batch(body: CutBatchModel) -> Dict[str, Any]:
    timeline = body.timeline.model_dump()
    ops = [o.model_dump() for o in body.operations]
    try:
        report = _cut().batch(timeline, ops)
    except (ValueError, KeyError) as e:
        raise _http_400(f"cut_failed: {e}") from e
    return {
        "operations": [
            {"op": o.op, "params": o.params,
             "result_clips": o.result_clips}
            for o in report.operations
        ],
        "timeline": report.timeline,
        "summary": {
            "clips": len(report.timeline.get("clips") or []),
            "cuts": len(report.timeline.get("cuts") or []),
        },
    }


@router.post("/detect_cuts")
async def detect_cuts_endpoint(body: DetectCutsModel) -> Dict[str, Any]:
    cuts = detect_cut_points(body.frames, threshold=body.threshold)
    return {"total": len(cuts), "items": cuts}


@router.post("/detect_silence")
async def detect_silence_endpoint(body: DetectSilenceModel) -> Dict[str, Any]:
    segs = detect_silence_segments(
        body.amplitudes, min_silence_sec=body.min_silence_sec,
        threshold=body.threshold)
    return {"total": len(segs), "items": segs,
            "total_silence_sec": round(sum(s["duration"] for s in segs), 3)}


@router.post("/keyframes")
async def keyframes_endpoint(body: KeyframesModel) -> Dict[str, Any]:
    try:
        kf = extract_keyframes(body.timestamps, method=body.method,
                               interval_sec=body.interval_sec)
    except ValueError as e:
        raise _http_400(f"keyframes_failed: {e}") from e
    return {"total": len(kf), "items": kf, "method": body.method}


# =====================================================================
# Transition / Effect / Montage
# =====================================================================

@router.post("/transition/{clip_id}")
async def apply_transition(clip_id: str,
                           body: TransitionModel) -> Dict[str, Any]:
    timeline = body.timeline.model_dump() if hasattr(body, "timeline") \
        else {"clips": [], "transitions": []}
    # The transition always uses the path-clip_id as ``from_clip``;
    # callers can override via body.from_clip.
    fc = body.from_clip or clip_id
    try:
        built = _trans().apply(
            timeline, from_clip=fc, to_clip=body.to_clip,
            type=body.type, duration=body.duration,
            easing=body.easing, color=body.color,
            direction=body.direction)
    except ValueError as e:
        raise _http_400(f"transition_failed: {e}") from e
    return built


class TransitionApplyModel(TransitionModel):
    timeline: TimelineModel = Field(default_factory=TimelineModel)


@router.post("/transition")
async def apply_transition_body(body: TransitionApplyModel) -> Dict[str, Any]:
    timeline = body.timeline.model_dump()
    try:
        built = _trans().apply(
            timeline, from_clip=body.from_clip, to_clip=body.to_clip,
            type=body.type, duration=body.duration,
            easing=body.easing, color=body.color,
            direction=body.direction)
    except ValueError as e:
        raise _http_400(f"transition_failed: {e}") from e
    return built


class EffectApplyModel(EffectModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    timeline: TimelineModel = Field(default_factory=TimelineModel)


@router.post("/effect")
async def apply_effect(body: EffectApplyModel) -> Dict[str, Any]:
    timeline = body.timeline.model_dump()
    params = dict(body.params)
    if body.intensity is not None:
        params.setdefault("intensity", body.intensity)
    try:
        built = _eff().apply(
            timeline, clip_id=body.clip_id, type=body.type, **params)
    except ValueError as e:
        raise _http_400(f"effect_failed: {e}") from e
    return built


@router.post("/effect/{clip_id}")
async def apply_effect_on_clip(clip_id: str,
                               body: EffectModel) -> Dict[str, Any]:
    params = dict(body.params)
    if body.intensity is not None:
        params.setdefault("intensity", body.intensity)
    timeline = params.pop("timeline", None) or {
        "clips": [], "effects": []}
    try:
        built = _eff().apply(
            timeline, clip_id=clip_id, type=body.type, **params)
    except ValueError as e:
        raise _http_400(f"effect_failed: {e}") from e
    return built


class MontageApplyModel(MontageModel):
    timeline: TimelineModel = Field(default_factory=TimelineModel)


@router.post("/montage")
async def apply_montage(body: MontageApplyModel) -> Dict[str, Any]:
    timeline = body.timeline.model_dump()
    params = {"per_clip_sec": body.per_clip_sec}
    try:
        plan = _mont().apply(
            timeline, clips=body.clips, type=body.type,
            time_mode=body.time_mode, layout=body.layout,
            bpm=body.bpm, params=params)
    except ValueError as e:
        raise _http_400(f"montage_failed: {e}") from e
    return plan


@router.post("/bpm_sync")
async def bpm_sync_endpoint(body: BPMSyncModel) -> Dict[str, Any]:
    try:
        cps = bpm_to_cut_points(body.bpm, body.clip_count,
                                offset=body.offset)
    except ValueError as e:
        raise _http_400(f"bpm_sync_failed: {e}") from e
    return {
        "bpm": body.bpm,
        "clip_count": body.clip_count,
        "offset": body.offset,
        "beat_sec": round(60.0 / body.bpm, 4),
        "cut_points": cps,
    }


# =====================================================================
# Render
# =====================================================================

@router.post("/render", status_code=status.HTTP_201_CREATED)
async def start_render(body: RenderModel,
                       bg: BackgroundTasks) -> Dict[str, Any]:
    timeline = body.timeline.model_dump()
    try:
        job = _render().create_job(
            timeline=timeline, codec=body.codec,
            resolution=body.resolution, bitrate_kbps=body.bitrate_kbps,
            output_name=body.output_name)
    except ValueError as e:
        raise _http_400(f"render_create_failed: {e}") from e
    if body.sync:
        _render().render(job.id, use_ffmpeg=body.use_ffmpeg)
        return _render().get_job(job.id).to_dict()
    bg.add_task(_render().render, job.id, 0.01, body.use_ffmpeg)
    return {
        "id": job.id,
        "status": RenderStatus.PENDING.value,
        "links": {
            "progress": f"/api/v1/workflow/editor/render/{job.id}/progress",
            "cancel": f"/api/v1/workflow/editor/render/{job.id}/cancel",
        },
    }


@router.get("/render/{rid}")
async def get_render(rid: str) -> Dict[str, Any]:
    job = _render().get_job(rid)
    if job is None:
        raise _http_404(f"render_not_found: {rid}")
    return job.to_dict()


@router.get("/render/{rid}/progress")
async def get_render_progress(rid: str) -> Dict[str, Any]:
    job = _render().get_job(rid)
    if job is None:
        raise _http_404(f"render_not_found: {rid}")
    d = job.to_dict()
    # Add a small projection tailored for progress polling
    return {
        "id": d["id"],
        "status": d["status"],
        "progress": d["progress"],
        "stage": d["stage"],
        "started_at": d["started_at"],
        "finished_at": d["finished_at"],
        "error": d["error"],
        "cancel_requested": d["cancel_requested"],
    }


@router.post("/render/{rid}/cancel")
async def cancel_render(rid: str) -> Dict[str, Any]:
    ok = _render().cancel(rid)
    if not ok:
        raise _http_404(f"render_not_found: {rid}")
    return {"success": True, "id": rid, "cancel_requested": True}


@router.websocket("/render/{rid}/ws")
async def render_ws(websocket: WebSocket, rid: str) -> None:
    """WebSocket: push render progress to the client until done."""
    await websocket.accept()
    job = _render().get_job(rid)
    if job is None:
        await websocket.send_json({"error": "render_not_found", "id": rid})
        await websocket.close()
        return
    last_stage = None
    last_progress = -1.0
    try:
        for _ in range(1000):  # safety cap
            j = _render().get_job(rid)
            if j is None:
                await websocket.send_json(
                    {"error": "render_not_found", "id": rid})
                break
            if (j.stage != last_stage
                    or abs(j.progress - last_progress) > 0.01
                    or j.status.value in ("completed", "failed",
                                          "cancelled")):
                await websocket.send_json({
                    "id": j.id,
                    "status": j.status.value,
                    "stage": j.stage,
                    "progress": round(j.progress, 3),
                })
                last_stage = j.stage
                last_progress = j.progress
            if j.status.value in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        logger.warning("render_ws error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


# =====================================================================
# Projects
# =====================================================================

@router.get("/projects")
async def list_projects(owner: Optional[str] = None,
                        limit: int = 50) -> Dict[str, Any]:
    items = _store().list(owner=owner, limit=limit)
    return {
        "total": len(items),
        "items": [p.to_dict() for p in items],
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreateModel) -> Dict[str, Any]:
    try:
        proj = _store().create(
            name=body.name, owner=body.owner,
            template_id=body.template_id,
            timeline=body.timeline.model_dump() if body.timeline else None)
    except ValueError as e:
        raise _http_400(f"project_create_failed: {e}") from e
    return proj.to_dict()


@router.get("/projects/{pid}")
async def get_project(pid: str) -> Dict[str, Any]:
    p = _store().get(pid)
    if p is None:
        raise _http_404(f"project_not_found: {pid}")
    return p.to_dict()


@router.put("/projects/{pid}")
async def update_project(pid: str,
                         body: ProjectUpdateModel) -> Dict[str, Any]:
    try:
        p = _store().update(
            pid, name=body.name,
            timeline=body.timeline.model_dump() if body.timeline else None,
            status=body.status, output_url=body.output_url,
            expected_version=body.expected_version)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        if "version_conflict" in msg:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=msg)
        raise _http_400(msg)
    return p.to_dict()


@router.delete("/projects/{pid}")
async def delete_project(pid: str) -> Dict[str, Any]:
    ok = _store().delete(pid)
    if not ok:
        raise _http_404(f"project_not_found: {pid}")
    return {"success": True, "id": pid}


@router.post("/projects/{pid}/snapshot")
async def take_snapshot(pid: str,
                        body: Optional[SnapshotModel] = None) -> Dict[str, Any]:
    label = (body.label if body else "") or ""
    try:
        p = _store().snapshot(pid, label=label)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/snapshot/{sid}/restore")
async def restore_snapshot(pid: str, sid: str) -> Dict[str, Any]:
    try:
        p = _store().restore_snapshot(pid, sid)
    except ValueError as e:
        msg = str(e)
        if "not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/undo")
async def undo_project(pid: str) -> Dict[str, Any]:
    try:
        p = _store().undo(pid)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/redo")
async def redo_project(pid: str) -> Dict[str, Any]:
    try:
        p = _store().redo(pid)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/lock")
async def lock_project(pid: str, body: LockModel) -> Dict[str, Any]:
    try:
        p = _store().acquire_lock(pid, body.user_id, ttl_sec=body.ttl_sec)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        if "project_locked_by" in msg:
            raise HTTPException(status.HTTP_423_LOCKED, detail=msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/unlock")
async def unlock_project(pid: str, body: LockModel) -> Dict[str, Any]:
    try:
        p = _store().release_lock(pid, body.user_id)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/heartbeat")
async def heartbeat_project(pid: str, body: LockModel) -> Dict[str, Any]:
    try:
        p = _store().heartbeat(pid, body.user_id)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


@router.post("/projects/{pid}/load_template")
async def load_template(pid: str,
                        body: LoadTemplateModel) -> Dict[str, Any]:
    try:
        p = _store().load_template(pid, body.template_id)
    except ValueError as e:
        msg = str(e)
        if "project_not_found" in msg:
            raise _http_404(msg)
        raise _http_400(msg)
    return p.to_dict()


__all__ = ["router"]
