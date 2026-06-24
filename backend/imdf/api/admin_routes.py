"""
Admin User Management Routes
============================
管理员用户管理 — 仅 admin 角色可访问。

GET    /api/admin/users                   — 查看所有用户列表
PUT    /api/admin/users/{username}/role    — 修改角色
PUT    /api/admin/users/{username}/disable — 禁用/启用用户
DELETE /api/admin/users/{username}        — 删除用户
GET    /api/admin/stats                   — 用户统计
GET    /api/admin/users/{username}/quota  — 查看用户配额
PUT    /api/admin/users/{username}/quota  — 设置用户配额
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.auth_routes import get_current_user, users_db
from engines.permission_matrix import require_admin
# R2.5-W3: 路径参数校验 — 防 traversal / SQL 注入 / 非法字符
from api._common.validators import validate_id
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Try to import DB session for persistence ──────────────────────────────
try:
    from api.db_models import get_db as get_sql_db, User as UserModel
    HAS_DB = True
except Exception:
    HAS_DB = False


# ─── Models ─────────────────────────────────────────────────────────────────

class UserInfo(BaseModel):
    username: str
    role: str
    status: str
    created_at: str
    max_datasets: int = 10
    max_storage_mb: int = 1024
    max_api_calls_per_day: int = 1000


class RoleUpdateRequest(BaseModel):
    role: str


class DisableRequest(BaseModel):
    disabled: bool = True


class QuotaUpdateRequest(BaseModel):
    max_datasets: Optional[int] = None
    max_storage_mb: Optional[int] = None
    max_api_calls_per_day: Optional[int] = None


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_user_quotas(username: str) -> dict:
    """Get quotas from in-memory store first, then DB, else defaults."""
    # Check in-memory store first
    user = users_db.get(username, {})
    mem_quotas = {}
    for k in ["max_datasets", "max_storage_mb", "max_api_calls_per_day"]:
        if k in user:
            mem_quotas[k] = user[k]

    if mem_quotas:
        return {
            "max_datasets": mem_quotas.get("max_datasets", 10),
            "max_storage_mb": mem_quotas.get("max_storage_mb", 1024),
            "max_api_calls_per_day": mem_quotas.get("max_api_calls_per_day", 1000),
        }

    if not HAS_DB:
        return {"max_datasets": 10, "max_storage_mb": 1024, "max_api_calls_per_day": 1000}
    try:
        # R7-W1: 读缓存 — 避免在循环里反复访问 DB
        from api._common.cache import get as cache_get, set as cache_set, DEFAULT_DETAIL_TTL
        cache_key = f"quota:{username}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        db = next(get_sql_db())
        db_user = db.query(UserModel).filter(UserModel.username == username).first()
        db.close()
        if db_user:
            result = {
                "max_datasets": db_user.max_datasets or 10,
                "max_storage_mb": db_user.max_storage_mb or 1024,
                "max_api_calls_per_day": db_user.max_api_calls_per_day or 1000,
            }
        else:
            result = {"max_datasets": 10, "max_storage_mb": 1024, "max_api_calls_per_day": 1000}
        cache_set(cache_key, result, ttl_seconds=DEFAULT_DETAIL_TTL)
        return result
    except Exception:
        return {"max_datasets": 10, "max_storage_mb": 1024, "max_api_calls_per_day": 1000}


def _get_all_user_quotas_bulk() -> dict:
    """R7-W1: 批量拉取所有用户配额, 单次查询 (替代 list_users 中的 N+1 循环)。

    Returns:
        dict[username] -> {"max_datasets": int, "max_storage_mb": int, "max_api_calls_per_day": int}
    """
    result: dict = {}
    # 1) 优先从内存库读
    for username, user in users_db.items():
        if any(k in user for k in ["max_datasets", "max_storage_mb", "max_api_calls_per_day"]):
            result[username] = {
                "max_datasets": user.get("max_datasets", 10),
                "max_storage_mb": user.get("max_storage_mb", 1024),
                "max_api_calls_per_day": user.get("max_api_calls_per_day", 1000),
            }
    if not HAS_DB:
        return result
    try:
        db = next(get_sql_db())
        # 单次查询, 批量加载所有用户的配额 (代替循环里的 N 次查询)
        rows = db.query(UserModel).all()
        db.close()
        for row in rows:
            result.setdefault(row.username, {
                "max_datasets": row.max_datasets or 10,
                "max_storage_mb": row.max_storage_mb or 1024,
                "max_api_calls_per_day": row.max_api_calls_per_day or 1000,
            })
    except Exception:
        pass
    return result


def _set_user_quotas(username: str, quotas: QuotaUpdateRequest) -> dict:
    """Update quotas in both in-memory store and SQLite DB.

    R7-W1: 写后失效配额缓存 (post-mutate hook)。
    """
    # Update in-memory store
    user = users_db.get(username)
    if user:
        if quotas.max_datasets is not None:
            user["max_datasets"] = quotas.max_datasets
        if quotas.max_storage_mb is not None:
            user["max_storage_mb"] = quotas.max_storage_mb
        if quotas.max_api_calls_per_day is not None:
            user["max_api_calls_per_day"] = quotas.max_api_calls_per_day

    # Update SQLite DB if available
    if HAS_DB:
        try:
            db = next(get_sql_db())
            db_user = db.query(UserModel).filter(UserModel.username == username).first()
            if db_user:
                if quotas.max_datasets is not None:
                    db_user.max_datasets = quotas.max_datasets
                if quotas.max_storage_mb is not None:
                    db_user.max_storage_mb = quotas.max_storage_mb
                if quotas.max_api_calls_per_day is not None:
                    db_user.max_api_calls_per_day = quotas.max_api_calls_per_day
                db.commit()
            db.close()
        except Exception as e:
            pass  # DB sync is best-effort

    # R7-W1: 写后失效 — 让下次 _get_user_quotas 重新从 DB 读
    try:
        from api._common.cache import invalidate_key
        invalidate_key(f"quota:{username}")
    except Exception:
        pass

    return _get_user_quotas(username)


def _sync_user_to_db(username: str, role: str, status: str):
    """Try to keep the SQLite DB in sync with in-memory users_db."""
    if not HAS_DB:
        return
    try:
        db = next(get_sql_db())
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user:
            user.role = role
            user.status = status
            db.commit()
        else:
            # Create in DB if not exists
            from api.db_models import Base
            import os
            db.execute(
                """INSERT OR IGNORE INTO users (username, password_hash, role, status, created_at)
                   VALUES (:un, '', :role, :status, :now)""",
                {"un": username, "role": role, "status": status, "now": datetime.now(timezone.utc).isoformat()},
            )
            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Operation failed: {e}")  # DB sync is best-effort


def _delete_user_from_db(username: str):
    """Remove user from SQLite DB."""
    if not HAS_DB:
        return
    try:
        db = next(get_sql_db())
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if user:
            db.delete(user)
            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Operation failed: {e}")


def _get_role_counts() -> dict:
    """Get counts per role from in-memory store."""
    counts = {}
    for user in users_db.values():
        role = user.get("role", "viewer")
        status = user.get("status", "active")
        counts[role] = counts.get(role, 0) + 1
        key = f"{role}_{status}"
        counts[key] = counts.get(key, 0) + 1
    counts["total"] = len(users_db)
    counts["active"] = sum(1 for u in users_db.values() if u.get("status", "active") == "active")
    counts["disabled"] = sum(1 for u in users_db.values() if u.get("status", "active") == "disabled")
    return counts


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/users", response_model=dict)
async def list_users(current_user: dict = Depends(get_current_user)):
    """管理员查看所有用户列表

    R7-W1: 用 _get_all_user_quotas_bulk() 替代循环里的 N+1 配额查询。
    """
    require_admin(current_user)

    # R7-W1: 单次批量查询, 把 N 次 SELECT 收敛为 1 次
    quotas_by_user = _get_all_user_quotas_bulk()
    users = []
    for username, u in users_db.items():
        quotas = quotas_by_user.get(username, {
            "max_datasets": 10,
            "max_storage_mb": 1024,
            "max_api_calls_per_day": 1000,
        })
        users.append({
            "username": username,
            "role": u.get("role", "viewer"),
            "status": u.get("status", "active"),
            "created_at": u.get("created_at", ""),
            "max_datasets": quotas.get("max_datasets", 10),
            "max_storage_mb": quotas.get("max_storage_mb", 1024),
            "max_api_calls_per_day": quotas.get("max_api_calls_per_day", 1000),
        })

    return {
        "success": True,
        "data": users,
        "message": f"{len(users)} users found",
    }


@router.put("/users/{username}/role", response_model=dict)
async def change_user_role(
    username: str,
    req: RoleUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """管理员修改用户角色"""
    validate_id(username, "username")
    require_admin(current_user)

    valid_roles = ["admin", "reviewer", "annotator", "viewer"]
    if req.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}",
        )

    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admins from demoting themselves
    if username == current_user["username"] and req.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Cannot change your own admin role",
        )

    old_role = users_db[username].get("role", "viewer")
    users_db[username]["role"] = req.role
    _sync_user_to_db(username, req.role, users_db[username].get("status", "active"))

    return {
        "success": True,
        "data": {
            "username": username,
            "old_role": old_role,
            "new_role": req.role,
        },
        "message": f"Role updated: {old_role} → {req.role}",
    }


@router.put("/users/{username}/disable", response_model=dict)
async def toggle_user_status(
    username: str,
    req: DisableRequest,
    current_user: dict = Depends(get_current_user),
):
    """管理员禁用/启用用户"""
    validate_id(username, "username")
    require_admin(current_user)

    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-disable
    if username == current_user["username"] and req.disabled:
        raise HTTPException(
            status_code=403,
            detail="Cannot disable your own account",
        )

    new_status = "disabled" if req.disabled else "active"
    old_status = users_db[username].get("status", "active")
    users_db[username]["status"] = new_status
    _sync_user_to_db(username, users_db[username].get("role", "viewer"), new_status)

    return {
        "success": True,
        "data": {
            "username": username,
            "status": new_status,
        },
        "message": f"User {'disabled' if req.disabled else 'enabled'}",
    }


@router.delete("/users/{username}", response_model=dict)
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_user),
):
    """管理员删除用户"""
    validate_id(username, "username")
    require_admin(current_user)

    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-delete
    if username == current_user["username"]:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete your own account",
        )

    # Also revoke this user's API keys
    try:
        from api.api_key_routes import get_db as get_key_db
        conn = get_key_db()
        conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE owner = ?",
            (username,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Operation failed: {e}")

    del users_db[username]
    _delete_user_from_db(username)

    return {
        "success": True,
        "data": None,
        "message": f"User '{username}' deleted",
    }


@router.get("/stats", response_model=dict)
async def admin_stats(current_user: dict = Depends(get_current_user)):
    """管理员查看用户统计"""
    require_admin(current_user)

    counts = _get_role_counts()

    return {
        "success": True,
        "data": {
            "total_users": counts.get("total", 0),
            "active_users": counts.get("active", 0),
            "disabled_users": counts.get("disabled", 0),
            "by_role": {
                role: counts.get(role, 0)
                for role in ["admin", "reviewer", "annotator", "viewer"]
            },
        },
        "message": "ok",
    }


@router.get("/users/{username}/quota", response_model=dict)
async def get_user_quota(
    username: str,
    current_user: dict = Depends(get_current_user),
):
    """查看用户配额（管理员可查看任意用户，普通用户只能看自己）"""
    validate_id(username, "username")
    from engines.permission_matrix import check_permission

    role = current_user.get("role", "viewer")
    if username != current_user["username"] and not check_permission(role, "manage_users"):
        raise HTTPException(status_code=403, detail="Not authorized to view other users' quotas")

    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    quotas = _get_user_quotas(username)
    return {
        "success": True,
        "data": {
            "username": username,
            **quotas,
        },
        "message": "ok",
    }


@router.put("/users/{username}/quota", response_model=dict)
async def set_user_quota(
    username: str,
    req: QuotaUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """管理员设置用户配额"""
    validate_id(username, "username")
    require_admin(current_user)

    if username not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    if req.max_datasets is None and req.max_storage_mb is None and req.max_api_calls_per_day is None:
        raise HTTPException(status_code=400, detail="At least one quota field is required")

    updated = _set_user_quotas(username, req)
    return {
        "success": True,
        "data": {
            "username": username,
            **updated,
        },
        "message": "Quotas updated",
    }
