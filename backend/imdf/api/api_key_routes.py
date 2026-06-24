"""
API Key 管理路由 — 多用户自助版
=================================
每个用户只能管理自己的 Key。
Key 格式: imdf_sk-{32位随机hex}

POST   /api/v1/api-keys/create    — 当前登录用户生成新Key
GET    /api/v1/api-keys            — 只返回当前用户的Key
DELETE /api/v1/api-keys/{key_id}   — 吊销自己的Key

存储: data/api_keys.db (SQLite)
验证中间件: 检查 X-API-Key 头
"""

import os
import secrets
import sqlite3
import json
import sys
import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel

from api.auth_routes import get_current_user
# R2.5-W3: 路径参数校验
from api._common.validators import validate_id

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "api_keys.db"
)

# ─── bcrypt hashing for API keys ──────────────────────────────────────────
try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False
    try:
        from passlib.hash import bcrypt as passlib_bcrypt
        _PASSLIB_BCRYPT = True
    except ImportError:
        _PASSLIB_BCRYPT = False


def _hash_api_key(key: str) -> str:
    """Hash an API key using bcrypt (only store the hash)."""
    if _BCRYPT_AVAILABLE:
        return bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    elif _PASSLIB_BCRYPT:
        return passlib_bcrypt.hash(key)
    else:
        # Fallback to sha256 if bcrypt unavailable (less secure but better than plaintext)
        return "sha256:" + hashlib.sha256(key.encode()).hexdigest()


def _verify_api_key_hash(key: str, hash_value: str) -> bool:
    """Verify an API key against its bcrypt hash."""
    if hash_value.startswith("sha256:"):
        # Fallback verification
        return "sha256:" + hashlib.sha256(key.encode()).hexdigest() == hash_value
    if _BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(key.encode("utf-8"), hash_value.encode("utf-8"))
        except Exception:
            return False
    elif _PASSLIB_BCRYPT:
        try:
            return passlib_bcrypt.verify(key, hash_value)
        except Exception:
            return False
    return False


def get_db() -> sqlite3.Connection:
    """获取SQLite连接（线程级，每次调用创建新连接）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化API Keys数据库表（含 owner 字段）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id          TEXT PRIMARY KEY,
            key         TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL DEFAULT '',
            owner       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            expires_at  TEXT,
            is_active   INTEGER NOT NULL DEFAULT 1,
            scopes      TEXT DEFAULT '{}',
            last_used   TEXT
        )
        """
    )
    # Add owner column if upgrading from old schema
    try:
        conn.execute("SELECT owner FROM api_keys LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE api_keys ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        conn.commit()

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_owner ON api_keys(owner)"
    )
    conn.commit()
    conn.close()


def _generate_api_key() -> str:
    """生成 imdf_sk-{32位随机hex} 格式的API Key"""
    return "imdf_sk-" + secrets.token_hex(16)  # 32 hex chars after prefix


# ─── Models ─────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = "default"
    expires_at: Optional[str] = None
    scopes: dict = {}


class CreateKeyResponse(BaseModel):
    id: str
    key: str
    name: str
    created_at: str
    expires_at: Optional[str] = None


class ApiKeyEntry(BaseModel):
    id: str
    name: str
    created_at: str
    expires_at: Optional[str] = None
    is_active: bool
    last_used: Optional[str] = None


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.post("/create", response_model=dict)
async def create_api_key(
    req: CreateKeyRequest,
    current_user: dict = Depends(get_current_user),
):
    """当前登录用户生成新的API Key"""
    import uuid
    key_id = str(uuid.uuid4())
    api_key = _generate_api_key()
    api_key_hash = _hash_api_key(api_key)
    now = datetime.now(timezone.utc).isoformat()
    owner = current_user["username"]

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO api_keys (id, key, name, owner, created_at, expires_at, is_active, scopes)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (key_id, api_key_hash, req.name, owner, now, req.expires_at, json.dumps(req.scopes)),
        )
        conn.commit()
        return {
            "success": True,
            "data": {
                "id": key_id,
                "key": api_key,
                "name": req.name,
                "owner": owner,
                "created_at": now,
                "expires_at": req.expires_at,
            },
            "message": "API Key created",
        }
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Key already exists")
    finally:
        conn.close()


@router.get("", response_model=dict)
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户的所有API Key（不暴露key值本身）"""
    owner = current_user["username"]
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, created_at, expires_at, is_active, last_used
           FROM api_keys
           WHERE owner = ?
           ORDER BY created_at DESC""",
        (owner,),
    ).fetchall()
    conn.close()
    return {
        "success": True,
        "data": [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "is_active": bool(row["is_active"]),
                "last_used": row["last_used"],
            }
            for row in rows
        ],
        "message": "ok",
    }


@router.delete("/{key_id}", response_model=dict)
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """吊销自己的一个API Key（软删除）"""
    validate_id(key_id, "key_id")
    owner = current_user["username"]
    conn = get_db()

    # Only allow revoking own keys
    row = conn.execute(
        "SELECT owner FROM api_keys WHERE id = ?", (key_id,)
    ).fetchone()

    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="API Key not found")

    if row["owner"] != owner:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail="You can only revoke your own API Keys",
        )

    conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()
    return {"success": True, "data": None, "message": "API Key revoked"}


# ─── 验证中间件 ─────────────────────────────────────────────────────────────

async def verify_api_key(request: Request, x_api_key: Optional[str] = Header(None)):
    """验证X-API-Key头。

    如果请求包含X-API-Key头，验证其有效性。
    如果不包含，直接放行（非强制认证）。
    验证通过后设置 request.state.api_key_owner。

    API Key以bcrypt哈希存储，验证时遍历活跃密钥进行比对。
    """
    if x_api_key is None:
        return None  # 不强制

    conn = get_db()
    # 由于key以哈希存储，需要遍历所有活跃密钥进行比对
    rows = conn.execute(
        "SELECT id, key, owner, is_active, expires_at FROM api_keys WHERE is_active = 1"
    ).fetchall()
    matched_row = None
    for row in rows:
        if _verify_api_key_hash(x_api_key, row["key"]):
            matched_row = row
            break
    conn.close()

    if matched_row is None:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    if not matched_row["is_active"]:
        raise HTTPException(status_code=401, detail="API Key revoked")
    if matched_row["expires_at"]:
        exp = datetime.fromisoformat(matched_row["expires_at"])
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API Key expired")
    # 更新最后使用时间
    conn_update = get_db()
    conn_update.execute(
        "UPDATE api_keys SET last_used = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), matched_row["id"]),
    )
    conn_update.commit()
    conn_update.close()

    # Attach owner info to request state for downstream use
    request.state.api_key_owner = matched_row["owner"]
    return matched_row["id"]


# 初始化数据库
init_db()
