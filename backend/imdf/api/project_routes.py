"""P5-R1-T1 ProjectCenter API 路由 — ``/api/v1/projects``

端点清单 (10 个):
  GET    /api/v1/projects                   列表 (status/owner_id/keyword/priority/page/page_size)
  POST   /api/v1/projects                   创建
  GET    /api/v1/projects/{id}              详情 (含 stats)
  PUT    /api/v1/projects/{id}              更新
  DELETE /api/v1/projects/{id}              删除
  POST   /api/v1/projects/{id}/members      添加成员
  DELETE /api/v1/projects/{id}/members/{user_id} 移除成员
  PATCH  /api/v1/projects/{id}/status       状态机转换
  GET    /api/v1/projects/{id}/stats        统计
  GET    /api/v1/projects/{id}/timeline     时间线

鉴权:
  - 所有 GET 走 ``Depends(get_current_user)`` (P11-B RFC 7519 标准声明已就位)
  - 所有写操作额外要求 role ∈ {admin, owner} 或 project 的 owner
  - 失败用 ``BusinessError`` 抛 4xx, 经 ``error_handler.register_exception_handlers`` 统一响应
  - 测试模式 (``IMDF_TEST_MODE=1``) 下 ``X-User`` header 也能通过, 便于 curl smoke
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

# ── 把 ``backend/imdf`` 加入 sys.path, 这样 ``from db import ...`` / ``from models import ...`` 才走得通
_BACKEND_IMDF = Path(__file__).resolve().parent.parent
if str(_BACKEND_IMDF) not in sys.path:
    sys.path.insert(0, str(_BACKEND_IMDF))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["project-center"])


# ════════════════════════════════════════════════════════════════════════════
# 鉴权依赖
# ════════════════════════════════════════════════════════════════════════════

async def get_optional_user(
    authorization: Optional[str] = Header(None),
    x_user: Optional[str] = Header(None, alias="X-User"),
) -> Optional[Dict[str, Any]]:
    """可选登录 — 测试模式下 ``X-User`` 也接受, 缺登录时返回 None。"""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            from common.auth import _decode_token, _resolve_user  # type: ignore
            import os
            if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
                # 直接走 test path
                user = _resolve_user(x_user) if x_user else None
                if user:
                    return user
            payload = _decode_token(token)
            username = payload.get("sub")
            user = _resolve_user(username) if username else None
            return user
        except Exception:
            return None
    if x_user:
        try:
            from common.auth import _resolve_user  # type: ignore
            import os
            if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
                user = _resolve_user(x_user) or {
                    "username": x_user, "role": "admin", "enabled": True,
                }
                return user
        except Exception:
            pass
    return None


async def require_user(user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    """必须登录 — 否则 401。"""
    if not user:
        raise HTTPException(status_code=401, detail="missing_authorization")
    return user


async def require_admin_or_owner(
    project_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_user),
) -> Dict[str, Any]:
    """写操作权限: admin / project owner / 测试模式下任意用户。"""
    role = (user.get("role") or "").lower()
    username = user.get("username") or ""
    if role == "admin":
        return user
    if project_id:
        # 检查 project.owner == username
        try:
            from engines.project_engine import ProjectEngine  # type: ignore
            eng = ProjectEngine(actor=username)
            proj = eng.get_project(project_id)
            if proj.owner_id == username:
                return user
        except Exception:
            pass
    # 测试模式 fallback — 让所有登录用户都能改
    import os
    if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
        return user
    raise HTTPException(status_code=403, detail="forbidden: requires admin or project owner")


# ════════════════════════════════════════════════════════════════════════════
# Pydantic 请求体
# ════════════════════════════════════════════════════════════════════════════

class _ProjectCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    description: str = Field("", max_length=4000)
    priority: str = Field("P1", pattern=r"^(P0|P1|P2|P3)$")
    tags: List[str] = Field(default_factory=list, max_length=50)
    members: List[str] = Field(default_factory=list, max_length=200)
    start_date: str = Field("", max_length=32, description="ISO date YYYY-MM-DD")
    due_date: str = Field("", max_length=32)
    status: str = Field("planning", pattern=r"^(planning|active|paused|closed)$")


class _ProjectUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    priority: Optional[str] = Field(None, pattern=r"^(P0|P1|P2|P3)$")
    tags: Optional[List[str]] = Field(None, max_length=50)
    members: Optional[List[str]] = Field(None, max_length=200)
    start_date: Optional[str] = Field(None, max_length=32)
    due_date: Optional[str] = Field(None, max_length=32)


class _ProjectMemberBody(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    role: str = Field("member", pattern=r"^(owner|admin|member|viewer)$")


class _ProjectStatusBody(BaseModel):
    status: str = Field(..., pattern=r"^(planning|active|paused|closed)$")
    reason: str = Field("", max_length=500)


# ════════════════════════════════════════════════════════════════════════════
# 响应构造 helpers
# ════════════════════════════════════════════════════════════════════════════

def _ok(data: Any, message: str = "") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def _err(message: str, code: str = "error", status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# ════════════════════════════════════════════════════════════════════════════
# 端点 — 10 个
# ════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=Dict[str, Any])
async def list_projects(
    status: Optional[str] = Query(None, pattern=r"^(planning|active|paused|closed)$"),
    owner_id: Optional[str] = Query(None, max_length=64),
    keyword: Optional[str] = Query(None, max_length=200),
    priority: Optional[str] = Query(None, pattern=r"^(P0|P1|P2|P3)$"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    _: Dict[str, Any] = Depends(require_user),
):
    """项目列表 — 支持 status/owner/keyword/priority/page/page_size 过滤。"""
    from engines.project_engine import ProjectEngine, ProjectValidationError  # type: ignore

    try:
        eng = ProjectEngine(actor="api:list")
        items, total = eng.list_projects(
            status=status,
            owner_id=owner_id,
            keyword=keyword,
            priority=priority,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        return _ok({
            "items": [p.to_dict() for p in items],
            "projects": [p.to_dict() for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_more": page * page_size < total,
        })
    except ProjectValidationError as exc:
        raise _err(str(exc), code="validation_error", status_code=422)


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_project(
    body: _ProjectCreateBody,
    user: Dict[str, Any] = Depends(require_user),
):
    """创建项目 — 鉴权: 任意登录用户可创建 (默认成为 owner)。"""
    from engines.project_engine import (  # type: ignore
        ProjectEngine,
        ProjectValidationError,
    )

    owner_id = user.get("username") or "unknown"
    try:
        eng = ProjectEngine(actor=owner_id)
        proj = eng.create_project(
            name=body.name,
            description=body.description,
            owner_id=owner_id,
            members=body.members,
            priority=body.priority,
            tags=body.tags,
            start_date=body.start_date,
            due_date=body.due_date,
            status=body.status,
            actor=owner_id,
        )
        return _ok(proj.to_dict(), message=f"project {proj.id} created")
    except ProjectValidationError as exc:
        raise _err(str(exc), code="validation_error", status_code=422)


@router.get("/{project_id}", response_model=Dict[str, Any])
async def get_project(
    project_id: str,
    _: Dict[str, Any] = Depends(require_user),
):
    """项目详情 — 含 members + timeline summary。"""
    from engines.project_engine import ProjectEngine, ProjectNotFoundError  # type: ignore

    try:
        eng = ProjectEngine(actor="api:get")
        proj = eng.get_project(project_id)
        members = eng.list_members(project_id)
        # 取最近 10 条 timeline (摘要)
        timeline = eng.get_timeline(project_id, limit=10)
        data = proj.to_dict()
        data["members_detail"] = members
        data["recent_timeline"] = timeline
        return _ok(data)
    except ProjectNotFoundError as exc:
        raise _err(f"project {project_id} not found", code="not_found", status_code=404)


@router.put("/{project_id}", response_model=Dict[str, Any])
async def update_project(
    project_id: str,
    body: _ProjectUpdateBody,
    user: Dict[str, Any] = Depends(require_user),
):
    """更新项目 — 鉴权: admin 或 project owner。"""
    from engines.project_engine import (  # type: ignore
        ProjectEngine,
        ProjectNotFoundError,
        ProjectValidationError,
    )

    await require_admin_or_owner(project_id=project_id, user=user)

    try:
        eng = ProjectEngine(actor=user.get("username") or "api")
        kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
        proj = eng.update_project(project_id, actor=user.get("username") or "api", **kwargs)
        return _ok(proj.to_dict(), message="updated")
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)
    except ProjectValidationError as exc:
        raise _err(str(exc), code="validation_error", status_code=422)


@router.delete("/{project_id}", response_model=Dict[str, Any])
async def delete_project(
    project_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """删除项目 — admin 或 project owner。"""
    from engines.project_engine import ProjectEngine, ProjectNotFoundError  # type: ignore

    await require_admin_or_owner(project_id=project_id, user=user)

    try:
        eng = ProjectEngine(actor=user.get("username") or "api")
        ok = eng.delete_project(project_id)
        if not ok:
            raise _err(f"project {project_id} not found", code="not_found", status_code=404)
        return _ok({"id": project_id, "deleted": True}, message="deleted")
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)


@router.post("/{project_id}/members", response_model=Dict[str, Any])
async def add_member(
    project_id: str,
    body: _ProjectMemberBody,
    user: Dict[str, Any] = Depends(require_user),
):
    """添加成员 — admin 或 project owner。"""
    from engines.project_engine import (  # type: ignore
        ProjectEngine,
        ProjectNotFoundError,
        ProjectValidationError,
    )

    await require_admin_or_owner(project_id=project_id, user=user)

    try:
        eng = ProjectEngine(actor=user.get("username") or "api")
        proj = eng.add_member(
            project_id, body.user_id, role=body.role,
            actor=user.get("username") or "api",
        )
        return _ok(proj.to_dict(), message=f"member {body.user_id} added")
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)
    except ProjectValidationError as exc:
        raise _err(str(exc), code="validation_error", status_code=422)


@router.delete("/{project_id}/members/{user_id}", response_model=Dict[str, Any])
async def remove_member(
    project_id: str,
    user_id: str,
    user: Dict[str, Any] = Depends(require_user),
):
    """移除成员 — admin 或 project owner。"""
    from engines.project_engine import ProjectEngine, ProjectNotFoundError  # type: ignore

    await require_admin_or_owner(project_id=project_id, user=user)

    try:
        eng = ProjectEngine(actor=user.get("username") or "api")
        proj = eng.remove_member(project_id, user_id)
        return _ok(proj.to_dict(), message=f"member {user_id} removed")
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)


@router.patch("/{project_id}/status", response_model=Dict[str, Any])
async def update_status(
    project_id: str,
    body: _ProjectStatusBody,
    user: Dict[str, Any] = Depends(require_user),
):
    """状态机转换 — admin 或 project owner。非法转换 → 422。"""
    from engines.project_engine import (  # type: ignore
        ProjectEngine,
        ProjectNotFoundError,
        ProjectStatusTransitionError,
        ProjectValidationError,
    )

    await require_admin_or_owner(project_id=project_id, user=user)

    try:
        eng = ProjectEngine(actor=user.get("username") or "api")
        proj = eng.transition_status(
            project_id, body.status,
            reason=body.reason,
            actor=user.get("username") or "api",
        )
        return _ok(proj.to_dict(), message=f"status → {body.status}")
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)
    except ProjectStatusTransitionError as exc:
        raise _err(
            f"invalid transition: {exc.old} → {exc.new}",
            code="invalid_status_transition",
            status_code=422,
        )
    except ProjectValidationError as exc:
        raise _err(str(exc), code="validation_error", status_code=422)


@router.get("/{project_id}/stats", response_model=Dict[str, Any])
async def get_stats(
    project_id: str,
    _: Dict[str, Any] = Depends(require_user),
):
    """项目统计 — requirements/tasks/datasets/deliveries 数量 + progress。"""
    from engines.project_engine import ProjectEngine, ProjectNotFoundError  # type: ignore

    try:
        eng = ProjectEngine(actor="api:stats")
        stats = eng.get_project_stats(project_id)
        return _ok(stats)
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)


@router.get("/{project_id}/timeline", response_model=Dict[str, Any])
async def get_timeline(
    project_id: str,
    limit: int = Query(100, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_user),
):
    """项目时间线 — 按 ts DESC。"""
    from engines.project_engine import ProjectEngine, ProjectNotFoundError  # type: ignore

    try:
        eng = ProjectEngine(actor="api:timeline")
        # 先确认 project 存在
        eng.get_project(project_id)
        events = eng.get_timeline(project_id, limit=limit)
        return _ok({
            "project_id": project_id,
            "events": events,
            "total": len(events),
        })
    except ProjectNotFoundError as exc:
        raise _err(str(exc), code="not_found", status_code=404)


# ════════════════════════════════════════════════════════════════════════════
# Health probe (用于 canvas_web 启动验证 / e2e 测试 ready-wait)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/_health", response_model=Dict[str, Any], include_in_schema=False)
async def health_probe():
    """项目中心模块健康检查 — 不需要鉴权, 用于 e2e ready-wait。"""
    return _ok({
        "module": "project_center",
        "status": "ok",
        "engine": "ProjectEngine",
    })


__all__ = ["router"]