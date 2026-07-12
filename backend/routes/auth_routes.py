"""
Nanobot Factory - 认证路由
文件: routes/auth_routes.py
功能: 登录/注册/令牌刷新/用户管理 API
兼容: FastAPI + unified_auth
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query, Request
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ---- 内部：懒加载统一认证 ----

_auth = None

def _get_auth():
    global _auth
    if _auth is None:
        from auth.unified_auth import get_unified_auth
        _auth = get_unified_auth()
    return _auth


# ---- Pydantic Models ----

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="viewer")
    email: str = Field(default="")
    display_name: str = Field(default="")
    team: str = Field(default="")

class RefreshRequest(BaseModel):
    refresh_token: str = Field(...)

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(...)
    new_password: str = Field(..., min_length=6, max_length=128)


class LogoutRequest(BaseModel):
    """登出请求 — 可选传 token 显式吊销 (默认从 Authorization header 取)."""
    revoke_refresh_token: bool = Field(
        default=True,
        description="是否同时吊销 refresh token (强烈建议 True)",
    )
    reason: str = Field(default="user_logout", max_length=64)


# ---- 认证依赖 ----

async def get_current_user(request: Request) -> Dict[str, Any]:
    """从 Authorization header 提取并验证当前用户"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    auth = _get_auth()
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = auth.get_user(user_id=payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user.to_dict()


async def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求管理员权限"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


# ---- API 路由 ----

@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """用户登录 → 返回 JWT token pair"""
    auth = _get_auth()
    result = auth.authenticate(
        username=body.username,
        password=body.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    if not result:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return result


@router.post("/register")
async def register(body: RegisterRequest):
    """注册新用户"""
    auth = _get_auth()
    user = auth.register_user(
        username=body.username,
        password=body.password,
        role=body.role,
        email=body.email,
        display_name=body.display_name,
        team=body.team,
    )
    if not user:
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"message": "User registered successfully", "user": user.to_dict()}


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    """刷新 access token"""
    auth = _get_auth()
    result = auth.refresh_access_token(body.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return result


@router.get("/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取当前用户信息"""
    return {"user": current_user}


@router.post("/logout")
async def logout(
    request: Request,
    body: Optional[LogoutRequest] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    用户登出 — 立即吊销当前 access token (P10R4-1 / HIDDEN-2).

    OWASP A07 对标: 登出必须使旧 token 立即失效, 不能依赖客户端删除.
    流程:
      1. 从 Authorization header 提取 access token
      2. 调用 mgr.revoke_token(token, reason="user_logout")
      3. 可选: 同时吊销 refresh token (防止凭 refresh 续命)
      4. 审计日志记录
    """
    auth = _get_auth()
    body = body or LogoutRequest()

    # 1. 提取 access token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None

    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # 2. 吊销 access token
    metadata = {
        "user_id": current_user.get("user_id"),
        "username": current_user.get("username"),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent", "")[:200],
        "reason_detail": body.reason,
    }
    revoked = auth.revoke_token(token, reason=body.reason, metadata=metadata)

    # 3. 审计日志
    auth._audit(
        action="auth.logout",
        user_id=current_user.get("user_id", ""),
        result="success" if revoked else "already_revoked",
        ip_address=request.client.host if request.client else None,
        details={
            "token_revoked": revoked,
            "reason": body.reason,
        },
    )

    return {
        "message": "Logged out successfully",
        "token_revoked": revoked,
    }


@router.get("/users")
async def list_users(
    role: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(require_admin),
):
    """列出所有用户 (仅管理员)"""
    auth = _get_auth()
    users = auth.list_users(role=role, team=team)
    return {"users": users, "count": len(users)}


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """获取指定用户信息"""
    auth = _get_auth()
    user = auth.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.to_dict()}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_admin),
):
    """删除用户 (仅管理员)"""
    auth = _get_auth()
    if not auth.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """修改当前用户密码"""
    auth = _get_auth()
    if not auth.change_password(current_user["user_id"], body.old_password, body.new_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    return {"message": "Password changed successfully"}


@router.get("/permissions")
async def get_my_permissions(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """获取当前用户的权限列表"""
    auth = _get_auth()
    perms = auth.get_user_permissions(current_user["user_id"])
    return {"permissions": perms, "role": current_user["role"]}
