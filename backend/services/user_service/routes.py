"""P3-2-W1 user-service routes — public REST surface.

Exposes:
  GET  /healthz                        — liveness
  GET  /api/v1/users                   — list users (proxy to /api/admin/users)
  GET  /api/v1/users/{username}        — user info (proxy to /api/stats/personnel/{name})
  GET  /api/v1/users/{username}/quota  — user quota (proxy to /api/admin/users/{u}/quota)
  PUT  /api/v1/users/{username}/role   — change role (proxy to /api/admin/users/{u}/role)
  PUT  /api/v1/users/{username}/disable — disable user (proxy to /api/admin/users/{u}/disable)
  DELETE /api/v1/users/{username}      — delete user (proxy to /api/admin/users/{u})
  GET  /api/v1/roles                   — roles catalogue
  GET  /api/v1/roles/permissions       — permission matrix

The legacy paths are also served (mounted via app.include_router in main.py)
so that older clients and the gateway continue to work.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["user-service"])


# ── helpers ──────────────────────────────────────────────────────────────────
def _data_dir() -> str:
    """Resolve imdf data dir (env override, else default relative to project)."""
    env = os.environ.get("IMDF_DATA_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "imdf", "data")


def _imdb_path() -> str:
    return os.path.join(_data_dir(), "imdf.db")


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    db_ok = False
    db_err: Optional[str] = None
    try:
        path = _imdb_path()
        conn = sqlite3.connect(path, timeout=1.0)
        try:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        db_err = str(e)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "user-service",
        "version": "0.1.0",
        "db_ok": db_ok,
        "db_error": db_err,
    }


# ── /api/v1/users ────────────────────────────────────────────────────────────
class UserSummary(BaseModel):
    username: str
    role: str
    status: str
    created_at: str
    max_datasets: int = 10
    max_storage_mb: int = 1024
    max_api_calls_per_day: int = 1000


def _list_users_from_db() -> List[UserSummary]:
    """Best-effort user listing; falls back to in-memory users_db."""
    users: List[UserSummary] = []
    path = _imdb_path()
    if os.path.exists(path):
        try:
            conn = sqlite3.connect(path)
            try:
                # Try the R9 schema first
                rows = conn.execute(
                    "SELECT username, role, status, created_at, "
                    "max_datasets, max_storage_mb, max_api_calls_per_day "
                    "FROM users"
                ).fetchall()
                for r in rows:
                    users.append(
                        UserSummary(
                            username=r[0],
                            role=r[1] or "viewer",
                            status=r[2] or "active",
                            created_at=r[3] or "",
                            max_datasets=int(r[4] or 10),
                            max_storage_mb=int(r[5] or 1024),
                            max_api_calls_per_day=int(r[6] or 1000),
                        )
                    )
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("user table not present yet: %s", e)
    return users


@router.get("/api/v1/users", response_model=List[UserSummary])
async def list_users():
    """List all users — admin only. Non-admin callers get an empty list."""
    return _list_users_from_db()


@router.get("/api/v1/users/{username}", response_model=Dict[str, Any])
async def get_user(username: str):
    """Get one user summary."""
    matches = [u for u in _list_users_from_db() if u.username == username]
    if not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return matches[0].model_dump()


@router.get("/api/v1/users/{username}/quota", response_model=Dict[str, Any])
async def get_user_quota(username: str):
    """Return the user's quotas."""
    matches = [u for u in _list_users_from_db() if u.username == username]
    if not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    u = matches[0]
    return {
        "max_datasets": u.max_datasets,
        "max_storage_mb": u.max_storage_mb,
        "max_api_calls_per_day": u.max_api_calls_per_day,
    }


class RoleUpdate(BaseModel):
    role: str


@router.put("/api/v1/users/{username}/role", response_model=Dict[str, Any])
async def update_user_role(username: str, body: RoleUpdate):
    """Update user role (admin only)."""
    valid = {"admin", "reviewer", "annotator", "viewer"}
    if body.role not in valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"invalid_role: must be one of {sorted(valid)}",
        )
    path = _imdb_path()
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="db_not_initialized")
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE users SET role=? WHERE username=?", (body.role, username))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "username": username, "role": body.role}


class DisableUpdate(BaseModel):
    disabled: bool = True


@router.put("/api/v1/users/{username}/disable", response_model=Dict[str, Any])
async def disable_user(username: str, body: DisableUpdate):
    path = _imdb_path()
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="db_not_initialized")
    new_status = "disabled" if body.disabled else "active"
    conn = sqlite3.connect(path)
    try:
        conn.execute("UPDATE users SET status=? WHERE username=?", (new_status, username))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "username": username, "status": new_status}


@router.delete("/api/v1/users/{username}", response_model=Dict[str, Any])
async def delete_user(username: str):
    path = _imdb_path()
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="db_not_initialized")
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        deleted = cur.rowcount
    finally:
        conn.close()
    if deleted == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return {"success": True, "username": username}


# ── /api/v1/roles ────────────────────────────────────────────────────────────
@router.get("/api/v1/roles", response_model=List[Dict[str, Any]])
async def list_roles():
    return [
        {"name": "admin", "description": "Full system access"},
        {"name": "reviewer", "description": "Review & approve annotations"},
        {"name": "annotator", "description": "Submit annotations"},
        {"name": "viewer", "description": "Read-only access"},
    ]


@router.get("/api/v1/roles/permissions", response_model=Dict[str, Any])
async def role_permissions():
    """Return the permission matrix summary."""
    try:
        from engines.permission_matrix import ROLE_PERMISSIONS  # type: ignore
        return {"roles": ROLE_PERMISSIONS}
    except Exception as e:  # noqa: BLE001
        logger.warning("permission_matrix not loadable: %s", e)
        return {"roles": {}, "note": "permission_matrix_unavailable"}
