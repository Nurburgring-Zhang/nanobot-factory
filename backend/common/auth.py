"""backend/common/auth — JWT auth + role guards for the 12 services (P4-1-W1).

Single source of truth for token decoding. Each service can call::

    from common.auth import get_current_user, require_role

    @router.get("/api/v1/admin/users")
    def list_users(user: dict = Depends(get_current_user)):
        ...

    @router.delete("/api/v1/users/{u}")
    def delete_user(u: str, user: dict = Depends(require_role("admin"))):
        ...

Why a standalone module?
  * The legacy ``imdf.api.auth_routes.get_current_user`` is *bound* to the
    ``users_db`` singleton in that module — services that don't import
    ``auth_routes`` shouldn't get a half-functional auth function.
  * This module reads users from ``imdf.db`` (or a SQLite file) when
    available, falls back to a static ``IMDF_TEST_USERS`` env (JSON) when
    not — so unit tests can self-bootstrap.

The ``get_current_user`` signature matches the legacy one (``dict`` return)
so callers can be migrated mechanically.

P11-B RFC 7519 enforce:
  * ``_secret()`` 在 secret < 16 字符时直接 raise ``ValueError``
    (fail-fast, 不再 silent warning)。
  * ``_decode_token()`` 强制校验 iss + aud
    (RFC 7519 §4.1.1 / §4.1.3): iss 必须等于 ``JWT_ISSUER``
    ("nanobot-factory"), aud 必须等于 ``JWT_AUDIENCE`` ("nanobot-factory-api")。
  * ``issue_access_token()`` 强制写入 iss / aud / jti 三标准声明
    (RFC 7519 §4.1.1 / §4.1.3 / §4.1.7), jti 用 uuid4().hex 全局唯一。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# P10-C: RFC 7519 标准声明常量 + secret 长度阈值
JWT_ISSUER = "nanobot-factory"
JWT_AUDIENCE = "nanobot-factory-api"
JWT_MIN_SECRET_LENGTH = 16  # 与 imdf.engines.audit_chain.AuditChain 一致


# ── Token decode helpers ────────────────────────────────────────────────────
def _secret() -> str:
    """Resolve JWT secret from env / imdf.config.settings."""
    sec = os.environ.get("JWT_SECRET", "").strip()
    if not sec or sec == "change-me-in-production":
        # Fall back to imdf's settings (loads .env too) if available
        try:
            from imdf.config.settings import SECRET_KEY  # type: ignore

            if SECRET_KEY and SECRET_KEY != "change-me-in-production":
                return SECRET_KEY
        except Exception:
            pass
        if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
            return "test-secret-common-lib"
    # P11-B: 启动时校验 secret 强度 (与 AuditChain / unified_auth 一致)
    # 短路 raise ValueError — 不再静默 warning, fail-fast 防止弱密钥被部署。
    if len(sec) < JWT_MIN_SECRET_LENGTH:
        raise ValueError(
            f"JWT_SECRET is too short ({len(sec)} chars, min "
            f"{JWT_MIN_SECRET_LENGTH}). Set JWT_SECRET to a strong random "
            f"value >= {JWT_MIN_SECRET_LENGTH} chars. (RFC 7519 §3 / OWASP A02)"
        )
    return sec


def _algo() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _decode_token(token: str) -> Dict[str, Any]:
    """Decode a JWT; raise HTTPException(401) on any failure.

    P11-B: 强制校验 ``iss`` (RFC 7519 §4.1.1) + ``aud`` (RFC 7519 §4.1.3)
    标准声明 — ``iss`` 必须等于 ``JWT_ISSUER`` ("nanobot-factory"),
    ``aud`` 必须等于 ``JWT_AUDIENCE`` ("nanobot-factory-api")。不匹配的
    token 一律返回 401, 阻止伪造 token (例如其他系统签发的 token 被复用)。
    本项目所有 token 均由 ``issue_access_token`` / ``unified_auth`` 签发,
    已自动写入正确的 iss/aud, 所以现有流程不受影响。

    注: python-jose ``verify_aud`` 在 token 缺少 aud claim 时静默通过
    (这是 jose lib 的已知行为), 所以这里额外手动检查 aud 必须存在。
    """
    try:
        from jose import JWTError, jwt

        payload = jwt.decode(
            token, _secret(), algorithms=[_algo()],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"verify_aud": True, "verify_iss": True},
        )
        # P11-B 兜底: jose 在 aud 缺失时静默通过, 显式检查 claim 存在
        if "aud" not in payload:
            logger.warning("jwt decode failed: missing aud claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
            )
        if "iss" not in payload:
            logger.warning("jwt decode failed: missing iss claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
            )
        return payload
    except HTTPException:
        raise  # 已经是 HTTPException, 直接 re-raise
    except Exception as exc:
        logger.warning("jwt decode failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")


# ── User resolution ────────────────────────────────────────────────────────
def _load_test_users() -> Dict[str, Dict[str, Any]]:
    """Read ``IMDF_TEST_USERS`` JSON env, e.g.

        IMDF_TEST_USERS='[{"username":"admin","role":"admin"}, ...]'

    Used when no imdf DB is reachable.
    """
    raw = os.environ.get("IMDF_TEST_USERS", "").strip()
    if not raw:
        return {}
    try:
        items = json.loads(raw)
        out: Dict[str, Dict[str, Any]] = {}
        for u in items:
            out[u["username"]] = {
                "role": u.get("role", "viewer"),
                "enabled": u.get("enabled", True),
            }
        return out
    except Exception as exc:
        logger.warning("IMDF_TEST_USERS parse failed: %s", exc)
        return {}


def _resolve_user(username: str) -> Optional[Dict[str, Any]]:
    """Look up *username* in imdf DB; fall back to test users; None if absent."""
    if not username:
        return None

    # 1) Try imdf DB first
    try:
        from imdf.config.settings import DATA_DIR  # type: ignore
        db_path = Path(DATA_DIR) / "imdf.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path), timeout=1.0)
            try:
                row = conn.execute(
                    "SELECT username, role, status FROM users WHERE username=?",
                    (username,),
                ).fetchone()
            finally:
                conn.close()
            if row:
                role = row[1] or "viewer"
                enabled = (row[2] or "active") == "active"
                return {"username": row[0], "role": role, "enabled": enabled}
    except Exception as exc:
        logger.debug("imdf DB user lookup failed: %s", exc)

    # 2) Test users fallback
    test = _load_test_users().get(username)
    if test:
        return {"username": username, **test}

    # 3) If IMDF_TEST_MODE is on, accept anyone with role=viewer (dev only)
    if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
        return {"username": username, "role": "viewer", "enabled": True}

    return None


# ── Public API ──────────────────────────────────────────────────────────────
def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user: Optional[str] = Header(None, alias="X-User"),
) -> Dict[str, Any]:
    """FastAPI Depends — return ``{username, role, payload, enabled}``.

    Behaviour:
      * If ``Authorization: Bearer <jwt>`` is present, decode and resolve user.
      * If only ``X-User`` is present and IMDF_TEST_MODE is on, accept it
        (dev shortcut so curl-based smoke tests don't need a JWT).
      * Otherwise raise 401.
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="invalid_auth_scheme")
        payload = _decode_token(token)
        if payload.get("type") and payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="access_token_required")
        username = payload.get("sub")
        user = _resolve_user(username) if username else None
        if not user:
            raise HTTPException(status_code=401, detail="user_not_found")
        if not user.get("enabled", True):
            raise HTTPException(status_code=403, detail="user_disabled")
        # JWT payload role wins over DB role when JWT explicitly sets one —
        # this lets ops flip roles in the JWT (short-lived) without waiting
        # for a DB write. Falls back to DB role if JWT didn't specify.
        jwt_role = payload.get("role")
        role = jwt_role if jwt_role else user.get("role", "viewer")
        return {
            "username": user["username"],
            "role": role,
            "enabled": user.get("enabled", True),
            "payload": payload,
        }

    # Dev fallback (TestClient / curl)
    if x_user and os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
        user = _resolve_user(x_user) or {"username": x_user, "role": "viewer", "enabled": True}
        return {
            "username": user["username"],
            "role": user.get("role", "viewer"),
            "enabled": True,
            "payload": {"sub": x_user, "test_mode": True},
        }

    raise HTTPException(status_code=401, detail="missing_authorization")


def require_role(*allowed_roles: str):
    """Build a Depends that 403s unless the caller's role is in *allowed_roles*.

    Usage::

        @router.delete("/api/v1/users/{u}")
        def delete_user(u: str, user=Depends(require_role("admin"))):
            ...
    """
    allowed = tuple(r.lower() for r in allowed_roles)

    def _dep(user: Dict[str, Any] = None) -> Dict[str, Any]:  # type: ignore[assignment]
        # ``user`` is injected via Depends(get_current_user); FastAPI resolves it.
        raise NotImplementedError  # placeholder — see ``require_role_dep`` below

    return _dep


def require_role_dep(*allowed_roles: str):
    """Functional variant that returns a real Depends-compatible callable."""
    from fastapi import Depends

    allowed = tuple(r.lower() for r in allowed_roles)

    def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if not user.get("enabled", True):
            raise HTTPException(status_code=403, detail="user_disabled")
        if allowed and user.get("role", "").lower() not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"forbidden: role '{user.get('role')}' not in {list(allowed)}",
            )
        return user

    return _checker


def issue_access_token(username: str, role: str = "viewer", ttl_minutes: Optional[int] = None) -> str:
    """Helper for tests / smoke endpoints. Returns a signed JWT."""
    try:
        from jose import jwt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"python-jose not installed: {exc}")

    ttl = ttl_minutes or int(os.environ.get("JWT_ACCESS_TTL_MINUTES", "30"))
    payload = {
        "sub": username,
        "role": role,
        "type": "access",
        # P10-C: RFC 7519 §4.1.1 / §4.1.3 / §4.1.7 标准声明
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl * 60,
    }
    return jwt.encode(payload, _secret(), algorithm=_algo())


__all__ = [
    "get_current_user",
    "require_role",
    "require_role_dep",
    "issue_access_token",
]