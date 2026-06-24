"""
IMDF 3D Canvas API — 3D API Endpoints
====================================
Backend data API for frontend Three.js 3D panorama/pose/motion interaction

Endpoints:
  GET    /api/3d/scenes          — List all scenes
  POST   /api/3d/scenes          — Create new scene
  GET    /api/3d/scenes/{id}     — Get single scene
  PUT    /api/3d/scenes/{id}     — Update scene
  DELETE /api/3d/scenes/{id}     — Delete scene

  POST   /api/3d/scenes/{id}/avatars       — Add avatar
  DELETE /api/3d/scenes/{id}/avatars/{aid} — Delete avatar
  POST   /api/3d/scenes/{id}/cameras       — Add camera view
  DELETE /api/3d/scenes/{id}/cameras/{cid} — Delete camera view
  POST   /api/3d/scenes/{id}/hotspots      — Add hotspot
  POST   /api/3d/scenes/{id}/keyframes     — Add keyframe
  POST   /api/3d/scenes/{id}/masks         — Add occlusion mask

  GET    /api/3d/poses           — Pose list
  GET    /api/3d/poses/tags      — Pose tags
  POST   /api/3d/poses/infer     — Natural language pose inference
  POST   /api/3d/actions/parse   — Parse action plan
  POST   /api/3d/actions/keyframes — Generate keyframe sequence

  GET    /api/3d/cameras/presets — Preset camera list
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines.data.data_3d import Data3DEngine, PosePreset, Avatar, CameraView, Hotspot, Keyframe, OcclusionMask

from api._common.body_schemas import (
    CreateSceneRequest,
    UpdateSceneRequest,
    AddAvatarRequest,
    AddCameraRequest,
    AddHotspotRequest,
    AddKeyframeRequest,
    AddMaskRequest,
    InferPoseRequest,
    ParseActionRequest,
    BuildKeyframesRequest,
)
# R2.5-W3: 路径参数校验
from api._common.validators import validate_id

router = APIRouter(prefix="/api/3d", tags=["3d"])

# 全局3D引擎实例
_engine: Optional[Data3DEngine] = None


def get_engine() -> Data3DEngine:
    global _engine
    if _engine is None:
        _engine = Data3DEngine()
    return _engine


# ============================================================================
# Request/Response Models (R2: moved to api._common.body_schemas)
# ============================================================================


# ============================================================================
# 场景 CRUD
# ============================================================================

@router.get("/scenes")
async def list_scenes(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取所有3D场景"""
    engine = get_engine()
    scenes = engine.list_scenes()
    if q:
        scenes = [s for s in scenes if q.lower() in (s.get("name", "") or "").lower()]
    total = len(scenes)
    if sort_by:
        scenes = sorted(
            scenes, key=lambda s: s.get(sort_by) or "",
            reverse=(order == "desc"),
        )
    page = scenes[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/scenes")
async def create_scene(req: CreateSceneRequest):
    """创建新3D场景"""
    engine = get_engine()
    scene = engine.create_scene(req.name)
    return {"success": True, "data": scene.to_dict()}


@router.get("/scenes/{scene_id}")
async def get_scene(scene_id: str):
    """Get single scene"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    scene = engine.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": scene.to_dict()}


@router.put("/scenes/{scene_id}")
async def update_scene(scene_id: str, req: UpdateSceneRequest):
    """Update scene"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    updates = {k: v for k, v in req.dict(exclude_none=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="无更新字段")
    scene = engine.update_scene(scene_id, updates)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": scene.to_dict()}


@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    """Delete scene"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    ok = engine.delete_scene(scene_id)
    if not ok:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "message": "场景已删除"}


# ============================================================================
# 人物管理
# ============================================================================

@router.post("/scenes/{scene_id}/avatars")
async def add_avatar(scene_id: str, req: AddAvatarRequest):
    """向场景Add avatar"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    avatar = engine.add_avatar(scene_id, req.name, req.color)
    if not avatar:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": avatar.to_dict()}


@router.delete("/scenes/{scene_id}/avatars/{avatar_id}")
async def remove_avatar(scene_id: str, avatar_id: str):
    """从场景Delete avatar"""
    validate_id(scene_id, "scene_id")
    validate_id(avatar_id, "avatar_id")
    engine = get_engine()
    ok = engine.remove_avatar(scene_id, avatar_id)
    if not ok:
        raise HTTPException(status_code=404, detail="场景或人物不存在")
    return {"success": True, "message": "人物已删除"}


# ============================================================================
# 摄像机管理
# ============================================================================

@router.get("/cameras/presets")
async def list_camera_presets(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取Preset camera list"""
    engine = get_engine()
    presets = engine.list_camera_presets()
    if q:
        presets = [p for p in presets if q.lower() in (p.get("name", "") or "").lower()]
    total = len(presets)
    if sort_by:
        presets = sorted(
            presets, key=lambda p: p.get(sort_by) or "",
            reverse=(order == "desc"),
        )
    page = presets[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/scenes/{scene_id}/cameras")
async def add_camera(scene_id: str, req: AddCameraRequest):
    """Add camera view"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    view = engine.add_camera_view(scene_id, req.name, req.yaw, req.pitch, req.fov)
    if not view:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": view.to_dict()}


@router.delete("/scenes/{scene_id}/cameras/{camera_id}")
async def remove_camera(scene_id: str, camera_id: str):
    """Delete camera view"""
    validate_id(scene_id, "scene_id")
    validate_id(camera_id, "camera_id")
    engine = get_engine()
    scene = engine.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    scene.camera_views.pop(camera_id, None)
    engine.scene_manager.save_scene(scene)
    return {"success": True, "message": "视角已删除"}


# ============================================================================
# 热点/关键帧/遮挡板
# ============================================================================

@router.post("/scenes/{scene_id}/hotspots")
async def add_hotspot(scene_id: str, req: AddHotspotRequest):
    """Add hotspot"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    hotspot = Hotspot(label=req.label, yaw=req.yaw, pitch=req.pitch,
                       fov=req.fov, target_scene_id=req.target_scene_id)
    result = engine.scene_manager.add_hotspot(scene_id, hotspot)
    if not result:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": result.to_dict()}


@router.post("/scenes/{scene_id}/keyframes")
async def add_keyframe(scene_id: str, req: AddKeyframeRequest):
    """Add keyframe"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    kf = Keyframe(frame_index=req.frame_index, timestamp=req.timestamp,
                   avatar_states=req.avatar_states)
    result = engine.scene_manager.add_keyframe(scene_id, kf)
    if not result:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": result.to_dict()}


@router.post("/scenes/{scene_id}/masks")
async def add_mask(scene_id: str, req: AddMaskRequest):
    """Add occlusion mask"""
    validate_id(scene_id, "scene_id")
    engine = get_engine()
    mask = engine.add_occlusion_mask(scene_id, req.avatar_id, req.mask_type)
    if not mask:
        raise HTTPException(status_code=404, detail="场景不存在")
    return {"success": True, "data": mask.to_dict()}


# ============================================================================
# 姿势库
# ============================================================================

@router.get("/poses")
async def list_poses(
    tag: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="姿势 tag 过滤",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取Pose list"""
    engine = get_engine()
    poses = engine.list_poses(tag)
    if q:
        poses = [p for p in poses if q.lower() in (p.get("name", "") or "").lower()]
    total = len(poses)
    if sort_by:
        poses = sorted(
            poses, key=lambda p: p.get(sort_by) or "",
            reverse=(order == "desc"),
        )
    page = poses[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "tag": tag,
        "limit": limit,
        "offset": offset,
    }


@router.get("/poses/tags")
async def list_pose_tags(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取Pose tags"""
    engine = get_engine()
    tags = engine.list_pose_tags()
    if q:
        tags = [t for t in tags if q.lower() in t.lower()]
    total = len(tags)
    if sort_by:
        tags = sorted(tags, reverse=(order == "desc"))
    page = tags[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/poses/infer")
async def infer_pose(req: InferPoseRequest):
    """从Natural language pose inference"""
    engine = get_engine()
    pose_id = engine.infer_pose(req.text, req.lang)
    return {"success": True, "data": {"pose_id": pose_id}}


# ============================================================================
# 动作生成
# ============================================================================

@router.post("/actions/parse")
async def parse_action(req: ParseActionRequest):
    """解析自然语言动作规划"""
    engine = get_engine()
    actions = engine.parse_action(req.text, req.lang)
    return {"success": True, "data": actions}


@router.post("/actions/keyframes")
async def build_keyframes(req: BuildKeyframesRequest):
    """构建关键帧序列"""
    engine = get_engine()
    keyframes = engine.build_keyframes(req.actions, req.frame_count, req.fps)
    return {"success": True, "data": keyframes}
