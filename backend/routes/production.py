"""Production pipeline API routes — multi-tenant batch data production.

P21 P2 P1 — security P0 fix (R2-09 / R2-NEW-06):
  All state-changing endpoints now require admin role via
  ``common.auth.require_role_dep("admin")``. Previously, ``POST /api/v2/users``
  had **no auth check** at all, allowing unauthenticated callers to mint
  themselves an admin user and obtain a long-lived ``api_key`` (full tenant
  takeover). The unauthenticated ``create_user`` reproducer now returns 401
  with no DB write and no api_key leak.
"""

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# P21 P2 P1: Admin guard for state-changing endpoints.
# require_role_dep("admin") → 401 if no/invalid Authorization header,
# 403 if role is not "admin", otherwise injects the user dict.
from common.auth import require_role_dep

_admin_required = require_role_dep("admin")
_authenticated_only = require_role_dep("admin", "team_lead", "annotator", "reviewer", "viewer")

# 延迟导入避免循环依赖
def _get_user_mgr():
    from core.multi_tenant import UserManager
    return UserManager()

def _get_batch_engine():
    from core.batch_engine import BatchEngine, PipelineType
    return BatchEngine()

def _get_data_mgr():
    from core.data_manager import DataManager
    # DataManager的base_path指向backend/data目录
    import os
    return DataManager(os.path.join(os.path.dirname(__file__), "..", "data"))

# ---- 用户管理 ----

@router.get("/api/v2/users")
async def list_users(_user: Dict[str, Any] = Depends(_admin_required)):
    um = _get_user_mgr()
    users = um.get_all_users()
    return [{"id": u.id, "username": u.username, "role": u.role.value, "is_active": u.is_active, "created_at": u.created_at} for u in users]

@router.post("/api/v2/users")
async def create_user(
    body: dict = Body(...),
    _user: Dict[str, Any] = Depends(_admin_required),
):
    """P21 P2 P1: now requires admin auth (R2-09 / R2-NEW-06 fix).

    Before: anyone (no Authorization header) could POST
    ``{"username":"x","role":"admin"}`` and receive 200 with a long-lived
    ``api_key``. After: 401 without auth, 403 for non-admin, 200 only for
    legitimate admin callers.
    """
    from core.multi_tenant import UserRole
    um = _get_user_mgr()
    role_str = body.get("role", "viewer")
    try:
        role = UserRole(role_str)
    except ValueError:
        role = UserRole.VIEWER
    user = um.create_user(body.get("username", "unknown"), role)
    return {"id": user.id, "username": user.username, "role": user.role.value, "api_key": user.api_key}

@router.get("/api/v2/users/{user_id}")
async def get_user(user_id: str, _user: Dict[str, Any] = Depends(_authenticated_only)):
    um = _get_user_mgr()
    user = um.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "username": user.username, "role": user.role.value}

# ---- 项目管理 ----

@router.get("/api/v2/projects")
async def list_projects(user_id: str = Query(...), _user: Dict[str, Any] = Depends(_authenticated_only)):
    um = _get_user_mgr()
    projects = um.get_user_projects(user_id)
    return [{"id": p.id, "name": p.name, "dataset_count": p.dataset_count, "created_at": p.created_at} for p in projects]

@router.post("/api/v2/projects")
async def create_project(
    body: dict = Body(...),
    _user: Dict[str, Any] = Depends(_admin_required),
):
    um = _get_user_mgr()
    project = um.create_project(body.get("user_id", ""), body.get("name", "unnamed"), body.get("description", ""))
    if not project:
        raise HTTPException(status_code=400, detail="Project creation failed (check quota)")
    return {"id": project.id, "name": project.name}

# ---- 数据集管理 ----

@router.get("/api/v2/datasets")
async def list_datasets(project_id: str = Query(...), _user: Dict[str, Any] = Depends(_authenticated_only)):
    dm = _get_data_mgr()
    datasets = dm.get_project_datasets(project_id)
    return [{"id": d.id, "name": d.name, "data_type": d.data_type.value, "row_count": d.row_count, "version": d.current_version} for d in datasets]

@router.post("/api/v2/datasets")
async def create_dataset(
    body: dict = Body(...),
    _user: Dict[str, Any] = Depends(_admin_required),
):
    from core.data_manager import DataType
    dm = _get_data_mgr()
    ds = dm.create_dataset(
        body.get("project_id", ""),
        body.get("name", "unnamed"),
        DataType(body.get("data_type", "image_text")),
        body.get("description", ""),
    )
    return {"id": ds.id, "name": ds.name, "root_path": ds.root_path}

@router.post("/api/v2/datasets/{dataset_id}/data")
async def add_data(
    dataset_id: str,
    body: dict = Body(...),
    _user: Dict[str, Any] = Depends(_admin_required),
):
    dm = _get_data_mgr()
    records = body.get("records", [])
    count = dm.add_data(dataset_id, records)
    if count == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"added": count}

@router.post("/api/v2/datasets/{dataset_id}/version")
async def create_version(
    dataset_id: str,
    notes: str = "",
    _user: Dict[str, Any] = Depends(_admin_required),
):
    dm = _get_data_mgr()
    v = dm.create_version(dataset_id, notes)
    if not v:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"version": v.version, "row_count": v.row_count, "total_size_mb": v.total_size_mb}

@router.get("/api/v2/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: str,
    format: str = Query("llava_json"),
    output_path: str = Query(""),
    _user: Dict[str, Any] = Depends(_authenticated_only),
):
    from core.data_manager import ExportFormat
    dm = _get_data_mgr()
    try:
        fmt = ExportFormat(format)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
    result = dm.export_dataset(dataset_id, fmt, output_path or f"/tmp/export_{dataset_id}.json")
    if not result:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"export_path": result, "format": format}

# ---- 批量生产 ----

@router.post("/api/v2/production/tasks")
async def create_task(
    body: dict = Body(...),
    _user: Dict[str, Any] = Depends(_admin_required),
):
    from core.batch_engine import PipelineType
    be = _get_batch_engine()
    try:
        pt = PipelineType(body.get("pipeline_type", "custom"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline type")

    task = be.create_task(
        body.get("project_id", ""),
        body.get("user_id", ""),
        pt,
        body.get("input_paths", []),
        body.get("output_dir", "/tmp/batch_output"),
        body.get("params", {}),
        body.get("worker_count", 2),
    )
    return {"id": task.id, "pipeline_type": pt.value, "status": task.status.value}

@router.get("/api/v2/tasks/{task_id}")
async def get_task_status(task_id: str, _user: Dict[str, Any] = Depends(_authenticated_only)):
    be = _get_batch_engine()
    task = be.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id, "status": task.status.value,
        "progress": {"total": task.progress.total, "completed": task.progress.completed, "failed": task.progress.failed},
        "elapsed": round(task.progress.elapsed, 1)
    }

@router.post("/api/v2/tasks/{task_id}/start")
async def start_task(task_id: str, _user: Dict[str, Any] = Depends(_admin_required)):
    be = _get_batch_engine()
    task = be.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # 同步触发异步 (FastAPI背景任务)
    from fastapi.concurrency import run_in_threadpool
    import asyncio
    asyncio.create_task(be.start_task(task_id))
    return {"status": "started", "task_id": task_id}

@router.post("/api/v2/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, _user: Dict[str, Any] = Depends(_admin_required)):
    be = _get_batch_engine()
    ok = be.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found or already completed")
    return {"status": "cancelled"}

@router.get("/api/v2/production/stats/{project_id}")
async def get_project_stats(project_id: str, _user: Dict[str, Any] = Depends(_authenticated_only)):
    dm = _get_data_mgr()
    stats = dm.get_project_stats(project_id)
    return stats
