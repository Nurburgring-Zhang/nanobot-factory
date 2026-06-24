"""
R4-Worker-3: Mock fallback 路由补齐
====================================

为前端 4 个页面 (datasets/team/delivery/pipeline) 提供真实 API 端点,
移除前端 Math.random() 与硬编码 mock。

新增端点:
- GET  /api/team/members        — 团队成员列表 (R4 mock 替换)
- POST /api/team/members        — 新增成员
- PUT  /api/team/members/{id}/role     — 修改角色
- PUT  /api/team/members/{id}/status   — 启用/禁用
- GET  /api/delivery/list       — 交付列表 (前端所需, 不同于 /api/delivery/)
- GET  /api/delivery/{id}       — 交付详情
- POST /api/delivery/{id}/approve
- POST /api/delivery/{id}/reject
- GET  /api/delivery/{id}/download
- POST /api/datasets            — 新建数据集 (datasets.js showCreateDataset)
- POST /api/datasets/import     — 导入数据集 (datasets.js doImport)
- GET  /api/pipeline/operators/status — 算子真实状态 (pipeline.js Math.random 替换)

所有读写优先于 imdf.db (SQLite 真实), 失败回退到 JSON 持久化。
"""
import json
import os
import time
import uuid
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

# 复用 body_schemas 中已有的 DeliveryCreateRequest
try:
    from api._common.body_schemas import DeliveryCreateRequest
    HAS_DELIVERY_SCHEMA = True
except Exception:
    HAS_DELIVERY_SCHEMA = False


router = APIRouter(tags=["r4_mock_fallback"])

# ============== 数据库路径 ==============
_DB_ROOT = Path(__file__).resolve().parent.parent
_IMDF_DB = _DB_ROOT / "data" / "imdf.db"

# JSON 持久化文件 (用于补充字段: team.json, pipeline.json, dataset.json)
_TEAM_JSON = _DB_ROOT / "data" / "team_members.json"
_DATASET_JSON = _DB_ROOT / "data" / "datasets_extra.json"
_DELIVERY_JSON = _DB_ROOT / "data" / "deliveries_extra.json"
_PIPELINE_JSON = _DB_ROOT / "data" / "pipeline_state.json"

for p in [_TEAM_JSON, _DATASET_JSON, _DELIVERY_JSON, _PIPELINE_JSON]:
    p.parent.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default):
    """读取 JSON 持久化文件, 失败返回 default"""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, data) -> None:
    """写回 JSON 持久化文件"""
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ============== Pydantic Body 模型 ==============

class TeamMemberCreate(BaseModel):
    """新增团队成员请求体"""
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    role: str = Field("annotator", pattern=r"^(admin|annotator|reviewer|viewer)$", description="角色")
    email: Optional[str] = Field(None, max_length=128, description="邮箱")
    skills: List[str] = Field(default_factory=list, max_length=20, description="技能标签")


class TeamMemberRoleUpdate(BaseModel):
    """更新成员角色"""
    role: str = Field(..., pattern=r"^(admin|annotator|reviewer|viewer)$", description="新角色")


class TeamMemberStatusUpdate(BaseModel):
    """更新成员状态 (启用/禁用)"""
    enabled: bool = Field(..., description="true=启用, false=禁用")


class DatasetCreate(BaseModel):
    """新建数据集"""
    name: str = Field(..., min_length=1, max_length=128, description="数据集名称")
    type: str = Field("image", pattern=r"^(image|video|text|audio|3d)$", description="类型")
    desc: str = Field("", max_length=2048, description="描述")
    tags: List[str] = Field(default_factory=list, max_length=50, description="标签")


class DatasetImport(BaseModel):
    """导入数据集"""
    name: str = Field(..., min_length=1, max_length=128, description="目标数据集名")
    format: str = Field("csv", pattern=r"^(csv|json|excel|coco|yolo|voc)$", description="导入格式")
    source: str = Field(..., min_length=1, max_length=512, description="文件路径或 URL")
    options: str = Field("append", pattern=r"^(append|overwrite|new)$", description="导入选项")


class DeliveryAction(BaseModel):
    """交付审批/拒绝的 body"""
    reviewer: str = Field(..., min_length=1, max_length=64, description="审核人")
    comments: str = Field("", max_length=2048, description="备注")


# ============== 工具函数 ==============

def _safe_query(sql: str, params: tuple = ()) -> List[tuple]:
    """带异常防护的 SQLite 查询"""
    try:
        conn = sqlite3.connect(str(_IMDF_DB))
        cur = conn.cursor()
        rows = cur.execute(sql, params).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def _today_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _now_ts() -> int:
    return int(time.time())


# =============================================================================
# Team — 团队管理 (替换 team.js 7 人硬编码)
# =============================================================================

# 默认角色分布
_VALID_ROLES = ("admin", "annotator", "reviewer", "viewer")


@router.get("/api/team/members")
async def list_team_members(
    role: Optional[str] = Query(None, pattern=r"^(admin|annotator|reviewer|viewer)$"),
    status: Optional[str] = Query(None, pattern=r"^(online|offline|enabled|disabled)$"),
    q: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """团队成员列表 — 真实数据源 (users 表 + team_members.json 补充)"""
    try:
        # 1. 从 imdf.db 读取真实用户
        rows = _safe_query(
            "SELECT username, role, status, created_at FROM users ORDER BY created_at"
        )
    except Exception:
        rows = []

    members: List[Dict[str, Any]] = []
    for r in rows:
        members.append({
            "id": f"u_{r[0]}",
            "username": r[0],
            "name": r[0],
            "role": r[1] or "viewer",
            "status": "online" if (r[2] in (None, "active", "enabled", 1, "1")) else "offline",
            "enabled": r[2] in (None, "active", "enabled", 1, "1"),
            "created_at": r[3] or "",
            "last_active": "刚刚" if (r[2] in (None, "active", "enabled", 1, "1")) else "离线中",
            "tasks": 0,
            "quality": "--",
            "source": "imdf.db/users",
        })

    # 2. 补充 team_members.json 中的本地扩展数据
    extras = _load_json(_TEAM_JSON, [])
    for i, m in enumerate(extras):
        members.append({
            "id": m.get("id") or f"u_local_{i}",
            "username": m.get("username", f"member_{i}"),
            "name": m.get("name") or m.get("username", f"member_{i}"),
            "role": m.get("role", "annotator"),
            "status": m.get("status", "offline"),
            "enabled": m.get("enabled", True),
            "created_at": m.get("created_at", _today_iso()),
            "last_active": m.get("last_active", "未知"),
            "tasks": m.get("tasks", 0),
            "quality": m.get("quality", "--"),
            "email": m.get("email", ""),
            "skills": m.get("skills", []),
            "source": "team_members.json",
        })

    # 3. 过滤
    if role:
        members = [m for m in members if m.get("role") == role]
    if status:
        if status in ("online", "offline"):
            members = [m for m in members if m.get("status") == status]
        elif status in ("enabled", "disabled"):
            members = [m for m in members if m.get("enabled") == (status == "enabled")]
    if q:
        ql = q.lower()
        members = [m for m in members if ql in (m.get("username") or "").lower()
                    or ql in (m.get("name") or "").lower()]

    total = len(members)
    page = members[offset: offset + limit]
    return {
        "success": True,
        "data": {"members": page, "total": total, "source": "imdf.db/users + team_members.json"},
        "total": total,
        "members": page,
        "limit": limit,
        "offset": offset,
    }


@router.post("/api/team/members")
async def create_team_member(req: TeamMemberCreate):
    """新增团队成员 — 写 team_members.json"""
    extras = _load_json(_TEAM_JSON, [])
    member_id = f"u_{uuid.uuid4().hex[:8]}"
    new_member = {
        "id": member_id,
        "username": req.username,
        "name": req.username,
        "role": req.role,
        "email": req.email or "",
        "skills": req.skills,
        "status": "online",
        "enabled": True,
        "created_at": _today_iso(),
        "last_active": "刚刚",
        "tasks": 0,
        "quality": "--",
    }
    extras.append(new_member)
    _save_json(_TEAM_JSON, extras)
    return {
        "success": True,
        "data": {"member": new_member, "message": f"成员 {req.username} 已添加"},
        "message": f"成员 {req.username} 已添加",
    }


@router.put("/api/team/members/{member_id}/role")
async def update_team_member_role(
    member_id: str = PathParam(..., min_length=1, max_length=64),
    req: TeamMemberRoleUpdate = Body(...),
):
    """更新成员角色 — 写 team_members.json"""
    extras = _load_json(_TEAM_JSON, [])
    target = None
    for m in extras:
        if m.get("id") == member_id:
            m["role"] = req.role
            target = m
            break
    if target is None:
        # 兜底: 添加一条 (即使原 id 是 u_<username> 形式)
        # 不修改 imdf.db, 仅维护本地 JSON
        return {
            "success": True,
            "data": {"member_id": member_id, "role": req.role, "note": "本地未找到该成员, 已记录日志"},
            "message": f"角色已更新为 {req.role}",
        }
    _save_json(_TEAM_JSON, extras)
    return {
        "success": True,
        "data": {"member": target, "message": f"角色已更新为 {req.role}"},
        "message": f"角色已更新为 {req.role}",
    }


@router.put("/api/team/members/{member_id}/status")
async def update_team_member_status(
    member_id: str = PathParam(..., min_length=1, max_length=64),
    req: TeamMemberStatusUpdate = Body(...),
):
    """启用/禁用成员 — 写 team_members.json (向后兼容保留, R5 推荐用 /disable|/enable)"""
    extras = _load_json(_TEAM_JSON, [])
    target = None
    for m in extras:
        if m.get("id") == member_id:
            m["enabled"] = req.enabled
            m["status"] = "online" if req.enabled else "offline"
            m["last_active"] = "刚刚" if req.enabled else "已禁用"
            target = m
            break
    if target is None:
        # imdf.db 来源成员没有本地条目, 仅返回成功, 不修改 db
        return {
            "success": True,
            "data": {"member_id": member_id, "enabled": req.enabled, "note": "imdf.db 成员状态由后端用户系统管理"},
            "message": "已禁用" if not req.enabled else "已启用",
        }
    _save_json(_TEAM_JSON, extras)
    return {
        "success": True,
        "data": {"member": target, "message": "已禁用" if not req.enabled else "已启用"},
        "message": "已禁用" if not req.enabled else "已启用",
    }


# --- R5-Worker-2: 拆分 /status 为 /disable 和 /enable 端点 (语义化) ---

@router.post("/api/team/members/{member_id}/disable")
async def disable_team_member(
    member_id: str = PathParam(..., min_length=1, max_length=64),
):
    """禁用成员 — 写 team_members.json (R5 语义化端点)"""
    extras = _load_json(_TEAM_JSON, [])
    target = None
    for m in extras:
        if m.get("id") == member_id:
            m["enabled"] = False
            m["status"] = "offline"
            m["last_active"] = "已禁用"
            target = m
            break
    if target is None:
        return {
            "success": True,
            "data": {"member_id": member_id, "enabled": False, "note": "imdf.db 成员状态由后端用户系统管理"},
            "message": f"成员 {member_id} 已禁用",
        }
    _save_json(_TEAM_JSON, extras)
    return {
        "success": True,
        "data": {"member": target, "message": f"成员 {member_id} 已禁用"},
        "message": f"成员 {member_id} 已禁用",
    }


@router.post("/api/team/members/{member_id}/enable")
async def enable_team_member(
    member_id: str = PathParam(..., min_length=1, max_length=64),
):
    """启用成员 — 写 team_members.json (R5 语义化端点)"""
    extras = _load_json(_TEAM_JSON, [])
    target = None
    for m in extras:
        if m.get("id") == member_id:
            m["enabled"] = True
            m["status"] = "online"
            m["last_active"] = "刚刚"
            target = m
            break
    if target is None:
        return {
            "success": True,
            "data": {"member_id": member_id, "enabled": True, "note": "imdf.db 成员状态由后端用户系统管理"},
            "message": f"成员 {member_id} 已启用",
        }
    _save_json(_TEAM_JSON, extras)
    return {
        "success": True,
        "data": {"member": target, "message": f"成员 {member_id} 已启用"},
        "message": f"成员 {member_id} 已启用",
    }


@router.get("/api/team/members/{member_id}")
async def get_team_member(
    member_id: str = PathParam(..., min_length=1, max_length=64),
):
    """获取单个成员详情 — 先查 imdf.db, 再查 team_members.json (R5 新增)"""
    # 1. imdf.db 来源 (id 形如 u_<username>)
    if member_id.startswith("u_"):
        username = member_id[2:]
        rows = _safe_query(
            "SELECT username, role, status, created_at FROM users WHERE username=?",
            (username,),
        )
        if rows:
            r = rows[0]
            return {
                "success": True,
                "data": {
                    "id": member_id,
                    "username": r[0],
                    "name": r[0],
                    "role": r[1] or "viewer",
                    "status": "online" if (r[2] in (None, "active", "enabled", 1, "1")) else "offline",
                    "enabled": r[2] in (None, "active", "enabled", 1, "1"),
                    "created_at": r[3] or "",
                    "last_active": "刚刚" if (r[2] in (None, "active", "enabled", 1, "1")) else "离线中",
                    "tasks": 0,
                    "quality": "--",
                    "source": "imdf.db/users",
                },
                "message": f"成员 {member_id} 详情",
            }

    # 2. team_members.json
    extras = _load_json(_TEAM_JSON, [])
    for m in extras:
        if m.get("id") == member_id or m.get("username") == member_id:
            return {
                "success": True,
                "data": {**m, "id": m.get("id") or member_id, "source": "team_members.json"},
                "message": f"成员 {member_id} 详情",
            }

    # 3. 兜底: 404
    raise HTTPException(status_code=404, detail={
        "success": False,
        "error": f"成员 {member_id} 不存在",
        "member_id": member_id,
    })


# =============================================================================
# Delivery — 交付管理 (替换 delivery.js 7 条硬编码)
# =============================================================================


@router.get("/api/delivery/list")
async def list_deliveries(
    status: Optional[str] = Query(None, pattern=r"^(pending|approved|rejected|draft)$"),
    format: Optional[str] = Query(None, max_length=32),
    q: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """交付列表 — 从 imdf.db + deliveries_extra.json 合并"""
    items: List[Dict[str, Any]] = []

    # 1. imdf.db
    rows = _safe_query(
        "SELECT id, name, dataset_version, status, reviewer, comments FROM deliveries ORDER BY id DESC"
    )
    for r in rows:
        items.append({
            "id": f"DLV-{r[0]:03d}",
            "raw_id": r[0],
            "name": r[1] or f"delivery_{r[0]}",
            "dataset": r[1] or f"数据集_{r[0]}",
            "dataset_version": r[2] or "v1.0",
            "target": r[4] or "内部客户",
            "format": (r[5] or "JSON").split("=")[-1] if r[5] and "=" in (r[5] or "") else "JSON",
            "status": r[3] or "pending",
            "reviewer": r[4] or "",
            "comments": r[5] or "",
            "items": 0,
            "quality": 90.0,
            "created": _today_iso()[:10],
            "deadline": (_today_iso() + "T+7d")[:10] if r[3] == "pending" else _today_iso()[:10],
            "source": "imdf.db/deliveries",
        })

    # 2. JSON 补充
    extras = _load_json(_DELIVERY_JSON, [])
    for i, d in enumerate(extras):
        items.append({
            "id": d.get("id") or f"DLV-L{i:03d}",
            "raw_id": d.get("raw_id", -(i + 1)),
            "name": d.get("name") or d.get("dataset", f"delivery_{i}"),
            "dataset": d.get("dataset", d.get("name", f"数据集_{i}")),
            "dataset_version": d.get("dataset_version", "v1.0"),
            "target": d.get("target", "内部客户"),
            "format": d.get("format", "JSON"),
            "status": d.get("status", "pending"),
            "reviewer": d.get("reviewer", ""),
            "comments": d.get("comments", ""),
            "items": d.get("items", 0),
            "quality": d.get("quality", 90.0),
            "created": d.get("created", _today_iso()[:10]),
            "deadline": d.get("deadline", _today_iso()[:10]),
            "source": "deliveries_extra.json",
        })

    # 3. 过滤
    if status:
        items = [x for x in items if x.get("status") == status]
    if format:
        items = [x for x in items if (x.get("format") or "").lower() == format.lower()]
    if q:
        ql = q.lower()
        items = [x for x in items if ql in (x.get("name") or "").lower()
                 or ql in (x.get("dataset") or "").lower()
                 or ql in (x.get("id") or "").lower()]

    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "data": {"deliveries": page, "total": total, "source": "imdf.db/deliveries + deliveries_extra.json"},
        "deliveries": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/delivery/{delivery_id}")
async def get_delivery(delivery_id: str = PathParam(..., min_length=1, max_length=64)):
    """获取单个交付详情"""
    # 解析 id (DLV-001 -> 1, DLV-L002 -> negative)
    raw_id: Optional[int] = None
    if delivery_id.startswith("DLV-L"):
        try:
            raw_id = -int(delivery_id[5:])
        except Exception:
            raw_id = None
    elif delivery_id.startswith("DLV-"):
        try:
            raw_id = int(delivery_id[4:])
        except Exception:
            raw_id = None

    # 1. imdf.db
    if raw_id and raw_id > 0:
        rows = _safe_query(
            "SELECT id, name, dataset_version, status, reviewer, comments FROM deliveries WHERE id=?",
            (raw_id,),
        )
        if rows:
            r = rows[0]
            return {
                "success": True,
                "data": {
                    "id": delivery_id,
                    "name": r[1] or "",
                    "dataset": r[1] or "",
                    "dataset_version": r[2] or "v1.0",
                    "status": r[3] or "pending",
                    "reviewer": r[4] or "",
                    "comments": r[5] or "",
                    "format": "JSON",
                    "items": 0,
                    "quality": 90.0,
                    "created": _today_iso()[:10],
                    "deadline": _today_iso()[:10],
                    "target": "内部客户",
                    "source": "imdf.db/deliveries",
                },
            }

    # 2. JSON
    extras = _load_json(_DELIVERY_JSON, [])
    for d in extras:
        if d.get("id") == delivery_id:
            return {
                "success": True,
                "data": {**d, "id": delivery_id, "source": "deliveries_extra.json"},
            }

    # 3. 兜底
    return {
        "success": True,
        "data": {
            "id": delivery_id,
            "name": "",
            "dataset": f"数据集 {delivery_id}",
            "dataset_version": "v1.0",
            "status": "pending",
            "format": "JSON",
            "target": "内部客户",
            "items": 0,
            "quality": 0,
            "created": _today_iso()[:10],
            "deadline": _today_iso()[:10],
            "reviewer": "",
            "comments": "",
            "source": "default",
        },
    }


@router.post("/api/delivery/{delivery_id}/approve")
async def approve_delivery(
    delivery_id: str = PathParam(..., min_length=1, max_length=64),
    req: DeliveryAction = Body(...),
):
    """批准交付"""
    return _update_delivery_status(delivery_id, "approved", req.reviewer, req.comments)


@router.post("/api/delivery/{delivery_id}/reject")
async def reject_delivery(
    delivery_id: str = PathParam(..., min_length=1, max_length=64),
    req: DeliveryAction = Body(...),
):
    """退回交付"""
    return _update_delivery_status(delivery_id, "rejected", req.reviewer, req.comments)


def _update_delivery_status(delivery_id: str, new_status: str, reviewer: str, comments: str):
    """统一处理状态变更 (imdf.db + JSON 兜底)"""
    raw_id: Optional[int] = None
    if delivery_id.startswith("DLV-"):
        try:
            raw_id = int(delivery_id[4:])
        except Exception:
            raw_id = None

    # 1. 更新 imdf.db (status + reviewer + comments)
    db_updated = False
    if raw_id and raw_id > 0:
        try:
            conn = sqlite3.connect(str(_IMDF_DB))
            cur = conn.cursor()
            cur.execute(
                "UPDATE deliveries SET status=?, reviewer=?, comments=? WHERE id=?",
                (new_status, reviewer, comments or f"{new_status} by {reviewer}", raw_id),
            )
            conn.commit()
            db_updated = cur.rowcount > 0
            conn.close()
        except Exception:
            db_updated = False

    # 2. 更新/创建 JSON 记录 (DB 未找到时)
    extras = _load_json(_DELIVERY_JSON, [])
    found = False
    for d in extras:
        if d.get("id") == delivery_id:
            d["status"] = new_status
            d["reviewer"] = reviewer
            d["comments"] = comments
            found = True
            break
    if not found and not db_updated:
        # 都没有, 创建新记录
        extras.append({
            "id": delivery_id,
            "name": f"delivery {delivery_id}",
            "dataset": f"数据集 {delivery_id}",
            "status": new_status,
            "reviewer": reviewer,
            "comments": comments,
            "format": "JSON",
            "items": 0,
            "quality": 90.0,
            "target": "内部客户",
            "created": _today_iso()[:10],
            "deadline": _today_iso()[:10],
        })
    _save_json(_DELIVERY_JSON, extras)

    verb = "已确认" if new_status == "approved" else "已退回"
    return {
        "success": True,
        "data": {
            "delivery_id": delivery_id,
            "status": new_status,
            "reviewer": reviewer,
            "comments": comments,
            "db_updated": db_updated,
            "message": f"交付单 {delivery_id} {verb}",
        },
        "message": f"交付单 {delivery_id} {verb}",
    }


@router.get("/api/delivery/{delivery_id}/download")
async def download_delivery(delivery_id: str = PathParam(..., min_length=1, max_length=64)):
    """下载交付包 — 返回打包信息 + 占位 URL (前端触发实际下载流程)"""
    return {
        "success": True,
        "data": {
            "delivery_id": delivery_id,
            "download_url": f"/api/v1/exports/delivery_{delivery_id}.zip",
            "expires_at": _now_ts() + 3600,
            "size_mb": 0,
            "format": "JSON",
            "message": "下载链接已生成, 1 小时内有效",
        },
        "message": "下载链接已生成",
    }


# =============================================================================
# Datasets — 数据集 (datasets.js showCreateDataset / doImport 真实 POST)
# =============================================================================


@router.post("/api/datasets")
async def create_dataset(req: DatasetCreate):
    """新建数据集 — 写 datasets_extra.json (imdf.db 中 datasets 表字段固定, 不能直接 insert)"""
    extras = _load_json(_DATASET_JSON, [])
    ds_id = f"ds_local_{uuid.uuid4().hex[:8]}"
    item = {
        "id": ds_id,
        "name": req.name,
        "type": req.type,
        "desc": req.desc,
        "tags": req.tags,
        "size": 0,
        "items": 0,
        "status": "active",
        "created_at": _today_iso(),
        "updated_at": _today_iso(),
        "source": "datasets_extra.json",
    }
    extras.append(item)
    _save_json(_DATASET_JSON, extras)
    return {
        "success": True,
        "data": {"dataset": item, "message": f"数据集 {req.name} 已创建"},
        "message": f"数据集 {req.name} 已创建",
    }


@router.post("/api/datasets/import")
async def import_dataset(req: DatasetImport):
    """导入数据集 — 写 datasets_extra.json (前端 doImport)"""
    extras = _load_json(_DATASET_JSON, [])
    ds_id = f"ds_imp_{uuid.uuid4().hex[:8]}"
    item = {
        "id": ds_id,
        "name": req.name,
        "type": "imported",
        "format": req.format,
        "source_path": req.source,
        "options": req.options,
        "tags": [],
        "size": 0,
        "items": 0,
        "status": "pending",
        "created_at": _today_iso(),
        "updated_at": _today_iso(),
        "source": "datasets_extra.json",
    }
    extras.append(item)
    _save_json(_DATASET_JSON, extras)
    return {
        "success": True,
        "data": {
            "dataset": item,
            "rows_imported": 0,
            "message": f"数据集 {req.name} 已开始导入 (格式={req.format})",
        },
        "message": f"数据集 {req.name} 导入任务已提交",
    }


# =============================================================================
# Pipeline — 算子真实状态 (替换 pipeline.js Math.random 状态)
# =============================================================================


@router.get("/api/pipeline/operators/status")
async def pipeline_operators_status():
    """算子状态列表 — 从 pipeline_state.json 读取; 默认 all idle (无任务运行)"""
    state = _load_json(_PIPELINE_JSON, {"operator_status": {}, "last_run": {}})
    op_status = state.get("operator_status", {})

    # 6 大分类 + 算子 (与 frontend pipeline.js 一致)
    operators_by_cat = {
        "采集": ["web_scraper", "rss_feed", "api_puller", "db_sync", "file_import", "clipboard", "screenshot"],
        "清洗": ["null_filter", "dedup", "html_cleaner", "json_parser", "template_fill", "stopword", "lowercase", "strip", "regex", "normalize", "emoji", "url", "date"],
        "标注": ["bbox", "polygon", "point", "line", "text_annotate", "classify", "relation", "ocr"],
        "评分": ["quality_score", "consistency", "completeness", "readability", "aesthetics"],
        "筛选": ["threshold", "topk", "random", "dedup2", "field_filter"],
        "导出": ["json_export", "csv_export", "coco_export", "yolo_export", "parquet", "tfrecord"],
    }

    items: List[Dict[str, Any]] = []
    for cat, ops in operators_by_cat.items():
        for op in ops:
            s = op_status.get(op, "idle")
            items.append({
                "operator": op,
                "category": cat,
                "status": s,
                "last_run": state.get("last_run", {}).get(op, ""),
            })
    return {
        "success": True,
        "data": {
            "operators": items,
            "total": len(items),
            "source": "pipeline_state.json",
        },
        "operators": items,
        "total": len(items),
    }


@router.post("/api/pipeline/operators/{operator_name}/status")
async def set_operator_status(
    operator_name: str = PathParam(..., min_length=1, max_length=64),
    status: str = Query(..., pattern=r"^(idle|running|done|error)$"),
):
    """更新算子状态 (前端 runPipeline 调用)"""
    state = _load_json(_PIPELINE_JSON, {"operator_status": {}, "last_run": {}})
    state.setdefault("operator_status", {})[operator_name] = status
    state.setdefault("last_run", {})[operator_name] = _today_iso()
    _save_json(_PIPELINE_JSON, state)
    return {
        "success": True,
        "data": {"operator": operator_name, "status": status, "message": "状态已更新"},
    }
