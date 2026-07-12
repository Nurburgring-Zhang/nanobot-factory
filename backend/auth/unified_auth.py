#!/usr/bin/env python3
"""
Nanobot Factory - 统一认证系统 (Unified Auth)
文件: auth/unified_auth.py
功能: JWT + Argon2密码哈希 + SQLite持久化 + RBAC角色集成
兼容: 与 nanobot-factory 现有认证系统 (security/auth.py, core/rbac.py, core/multi_tenant.py) 完全兼容
作者: Hermes Agent
版本: v2.0.0
"""

import os
import sys
import json
import secrets
import hashlib
import hmac
import threading
import sqlite3
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

# JWT
try:
    import jwt
except ImportError:
    jwt = None
    print("[WARN] PyJWT not installed. Run: pip install PyJWT")

# P10-C: UUID for jti claim (RFC 7519 §4.1.7)
try:
    from uuid import uuid4 as _uuid4
except ImportError:  # pragma: no cover
    _uuid4 = None

# P10-C: JWT issuer / audience constants (RFC 7519 §4.1.1, §4.1.3)
JWT_ISSUER = "nanobot-factory"
JWT_AUDIENCE = "nanobot-factory-api"
JWT_MIN_SECRET_LENGTH = 16  # 与 AuditChain 一致 (audit_chain.py:153)

# Argon2 (优先) 或 fallback 到 hashlib pbkdf2
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    print("[WARN] argon2-cffi not installed, falling back to PBKDF2-SHA256. Run: pip install argon2-cffi")

# BruteForce protection (P10 Sprint D)
from .bruteforce import BruteForceProtector, BruteForceConfig, ThrottleResult

# Token revocation (P10R4-1 / P0-5)
from .token_revocation import TokenRevocationStore, get_revocation_store

# Audit log writer for user-management state changes (P21 P2 P3 R1-02 fix)
from .audit import AuditLog

logger = logging.getLogger("unified_auth")


# ============================================================================
# 角色枚举 — 与 core/rbac.py 保持兼容，并扩展 team_lead
# ============================================================================

class AdminConfigError(RuntimeError):
    """P11-D-1: 启动时检测到 admin 账户配置错误(缺 ADMIN_INITIAL_PASSWORD 等)抛此异常。"""


class UnifiedRole(str, Enum):
    """统一角色定义，兼容 rbac.py 的 Role 和多租户的 UserRole"""
    ADMIN = "admin"                   # 超级管理员 — 全部权限
    TEAM_LEAD = "team_lead"           # 团队负责人 — 管理生产/众包团队
    REVIEWER = "reviewer"             # 审核员 — 审核标注/质检
    ANNOTATOR = "annotator"           # 标注员 — 执行标注/生产
    VIEWER = "viewer"                 # 查看者 — 只读/提需求

    # 以下为 rbac.py 兼容角色，默认映射到上方角色
    ORG_OWNER = "org_owner"           # → TEAM_LEAD
    ORG_ADMIN = "org_admin"           # → TEAM_LEAD
    PROJECT_MANAGER = "project_manager"  # → TEAM_LEAD
    OPERATOR = "operator"             # → REVIEWER
    USER = "user"                     # → ANNOTATOR
    GUEST = "guest"                   # → VIEWER

    @classmethod
    def normalize(cls, role_str: str) -> "UnifiedRole":
        """将任意角色字符串规范化为统一角色"""
        role_str = role_str.lower().strip()
        mapping = {
            "admin": cls.ADMIN,
            "super_admin": cls.ADMIN,
            "team_lead": cls.TEAM_LEAD,
            "org_owner": cls.TEAM_LEAD,
            "org_admin": cls.TEAM_LEAD,
            "project_manager": cls.TEAM_LEAD,
            "reviewer": cls.REVIEWER,
            "operator": cls.REVIEWER,
            "qc_lead": cls.REVIEWER,
            "annotator": cls.ANNOTATOR,
            "user": cls.ANNOTATOR,
            "viewer": cls.VIEWER,
            "guest": cls.VIEWER,
        }
        return mapping.get(role_str, cls.VIEWER)


# ============================================================================
# 权限定义
# ============================================================================

ROLE_PERMISSIONS: Dict[UnifiedRole, List[str]] = {
    UnifiedRole.ADMIN: [
        # 所有权限
        "user:create", "user:read", "user:update", "user:delete",
        "tool:execute", "tool:manage",
        "agent:create", "agent:execute", "agent:view",
        "file:read", "file:write", "file:delete",
        "exec:sql", "system:config", "secret:access",
        "generate:image", "generate:video", "generate:3d",
        "project:create", "project:manage", "project:view",
        "task:create", "task:assign", "task:review", "task:view",
        "requirement:create", "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.TEAM_LEAD: [
        "user:read", "user:create",
        "tool:execute", "tool:manage",
        "agent:create", "agent:execute", "agent:view",
        "file:read", "file:write",
        "generate:image", "generate:video", "generate:3d",
        "project:create", "project:manage", "project:view",
        "task:create", "task:assign", "task:review", "task:view",
        "requirement:create", "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.REVIEWER: [
        "user:read",
        "tool:execute",
        "agent:execute", "agent:view",
        "file:read", "file:write",
        "project:view",
        "task:review", "task:view",
        "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.ANNOTATOR: [
        "user:read",
        "tool:execute",
        "agent:execute", "agent:view",
        "file:read", "file:write",
        "project:view",
        "task:view",
    ],
    UnifiedRole.VIEWER: [
        "user:read",
        "agent:view",
        "file:read",
        "project:view",
        "task:view",
        "requirement:create",   # 可以提需求
        "requirement:view",     # 可以查看进度
        "delivery:review",      # 可以审核交付
    ],
}


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class LoginResult:
    """
    登录结果 (P10 Sprint D 加入)
    status:
        - "success": 登录成功, tokens 字段有值
        - "invalid_credentials": 用户名/密码错误
        - "locked": 触发暴力破解防护, retry_after > 0
        - "inactive": 用户存在但 is_active=False
    """
    status: str
    tokens: Optional[Dict[str, Any]] = None
    user: Optional[Dict[str, Any]] = None
    retry_after: int = 0
    reason: str = ""
    locked_dimension: str = ""  # "account" | "ip" | ""
    lockout_level: str = "none"
    failed_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "tokens": self.tokens,
            "user": self.user,
            "retry_after": self.retry_after,
            "reason": self.reason,
            "locked_dimension": self.locked_dimension,
            "lockout_level": self.lockout_level,
            "failed_count": self.failed_count,
        }


@dataclass
class AuthUser:
    """统一认证用户模型"""
    user_id: str
    username: str
    email: str
    role: str  # UnifiedRole value
    password_hash: str = ""
    password_salt: str = ""    # argon2不需要salt（内置），pbkdf2需要
    hash_method: str = "argon2"  # "argon2" 或 "pbkdf2"
    is_active: bool = True
    is_verified: bool = True
    display_name: str = ""
    team: str = ""              # "production" | "crowdsource" | "client"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    last_login: Optional[str] = None
    login_count: int = 0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "display_name": self.display_name,
            "team": self.team,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "login_count": self.login_count,
        }


# ============================================================================
# 密码管理器 (Argon2 优先，PBKDF2 备用)
# ============================================================================

class PasswordManager:
    """密码哈希与验证 — Argon2id 优先，兼容 PBKDF2"""

    def __init__(self):
        if ARGON2_AVAILABLE:
            self._argon2 = PasswordHasher(
                time_cost=3,        # 迭代次数
                memory_cost=65536,  # 64 MB
                parallelism=4,      # 并行度
                hash_len=32,        # 哈希输出长度
                salt_len=16,        # salt长度（内置）
            )
        else:
            self._argon2 = None

    def hash_password(self, password: str) -> Tuple[str, str, str]:
        """
        哈希密码
        Returns: (hash_string, salt_string, method)
        - argon2: hash_string 包含完整哈希 (含内置salt), salt="" , method="argon2"
        - pbkdf2: hash_string=hex, salt=hex, method="pbkdf2"
        """
        if self._argon2:
            hash_str = self._argon2.hash(password)
            return hash_str, "", "argon2"
        else:
            salt = secrets.token_hex(32)
            hashed = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hashed.hex(), salt, "pbkdf2"

    def verify_password(self, password: str, hash_str: str, salt: str = "", method: str = "argon2") -> bool:
        """验证密码"""
        if method == "argon2" or (method == "" and self._argon2 and salt == ""):
            if not self._argon2:
                # argon2不可用但存储的是argon2哈希 -> 无法验证
                logger.error("argon2 not available, cannot verify argon2 hash")
                return False
            try:
                return self._argon2.verify(hash_str, password)
            except (VerifyMismatchError, VerificationError):
                return False
        elif method == "pbkdf2":
            computed, _ = self._hash_pbkdf2_only(password, salt)
            return hmac.compare_digest(computed.hex(), hash_str)
        else:
            # 未知方法，尝试 argon2 然后 pbkdf2
            if self._argon2:
                try:
                    return self._argon2.verify(hash_str, password)
                except Exception:
                    pass
            if salt:
                try:
                    computed, _ = self._hash_pbkdf2_only(password, salt)
                    return hmac.compare_digest(computed.hex(), hash_str)
                except Exception:
                    return False
            return False

    @staticmethod
    def _hash_pbkdf2_only(password: str, salt: str) -> Tuple[bytes, str]:
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hashed, salt

    @staticmethod
    def needs_rehash(password: str, hash_str: str, method: str = "pbkdf2") -> bool:
        """检查是否需要用 argon2 重新哈希"""
        return ARGON2_AVAILABLE and method == "pbkdf2"


# ============================================================================
# JWT 管理器
# ============================================================================

class JWTManager:
    """JWT 令牌管理

    P11-B 强化 (RFC 7519 合规 + OWASP A02):
      * 启动校验 secret_key 长度 >= JWT_MIN_SECRET_LENGTH (16 字符),
        与 ``imdf.engines.audit_chain.AuditChain`` 阈值一致
        (P10-C-1 — secret < 16 字符直接 raise ``ValueError``)。
      * 签发 access / refresh token 时强制写入 iss / aud / jti 三标准声明
        (RFC 7519 §4.1.1 / §4.1.3 / §4.1.7), jti 用 uuid4().hex 全局唯一,
        可作为黑名单 / 防重放的唯一 ID。
      * verify_token 强制校验 iss + aud (P11-B-2):
          - iss 必须等于 ``JWT_ISSUER`` ("nanobot-factory")
          - aud 必须等于 ``JWT_AUDIENCE`` ("nanobot-factory-api")
        不匹配的 token 一律返回 ``None`` (``jwt.InvalidTokenError`` 被吞掉),
        阻止伪造 token (跨系统 token 复用) 与弱密钥被绕过。
      * secret 强度校验 + iss/aud 强制 + jti 唯一 = RFC 7519 §4.1.1 / §4.1.3 /
        §4.1.7 三项标准声明 enforce, 对应 OWASP A02:2021 + A07:2021。
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        # P10-C-1: 启动时拒绝短 secret (与 AuditChain 一致, audit_chain.py:153)
        if not secret_key or not isinstance(secret_key, str):
            raise ValueError(
                "JWT secret_key must be a non-empty string"
            )
        if len(secret_key) < JWT_MIN_SECRET_LENGTH:
            raise ValueError(
                f"JWT secret must be >= {JWT_MIN_SECRET_LENGTH} chars "
                f"(got {len(secret_key)}). Use a strong random secret."
            )
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expiry = 3600      # 1小时
        self.refresh_token_expiry = 86400 * 7  # 7天

    def _new_jti(self) -> str:
        """RFC 7519 §4.1.7 jti — JWT ID, 全局唯一。"""
        if _uuid4 is not None:
            return _uuid4().hex
        # 极端 fallback: secrets.token_hex(16) 提供 128-bit 熵
        return secrets.token_hex(16)

    def create_access_token(self, user_id: str, username: str, role: str,
                            permissions: List[str] = None, expiry: int = None) -> str:
        """创建访问令牌"""
        if expiry is None:
            expiry = self.access_token_expiry
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            'sub': user_id,
            'username': username,
            'role': role,
            'permissions': permissions or [],
            'type': 'access',
            'iss': JWT_ISSUER,            # RFC 7519 §4.1.1
            'aud': JWT_AUDIENCE,          # RFC 7519 §4.1.3
            'jti': self._new_jti(),       # RFC 7519 §4.1.7
            'iat': now,
            'exp': now + timedelta(seconds=expiry),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str, expiry: int = None) -> str:
        """创建刷新令牌"""
        if expiry is None:
            expiry = self.refresh_token_expiry
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            'sub': user_id,
            'type': 'refresh',
            'iss': JWT_ISSUER,            # RFC 7519 §4.1.1
            'aud': JWT_AUDIENCE,          # RFC 7519 §4.1.3
            'jti': self._new_jti(),       # RFC 7519 §4.1.7
            'iat': now,
            'exp': now + timedelta(seconds=expiry),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = None) -> Optional[Dict[str, Any]]:
        """验证令牌

        P11-B: 强制校验 ``iss`` (RFC 7519 §4.1.1) + ``aud`` (RFC 7519 §4.1.3)
        标准声明 — iss 必须是 ``JWT_ISSUER`` ("nanobot-factory"), aud 必须是
        ``JWT_AUDIENCE`` ("nanobot-factory-api")。任何不匹配的 token 一律拒绝
        并返回 ``None`` (而不是 raise) 以保持调用方兼容。生产 token 由本类
        签发时已自动写入这 2 个声明, 校验不破坏现有流程; 旧 token (无 iss/aud)
        在迁移前可能无法通过 verify。
        """
        if not jwt:
            logger.error("PyJWT not installed")
            return None
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER,
                options={"verify_aud": True, "verify_iss": True},
            )
            if token_type and payload.get('type') != token_type:
                logger.warning(f"Token type mismatch: expected {token_type}")
                return None
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token无效: {e}")
            return None

    def decode_token_unsafe(self, token: str) -> Optional[Dict[str, Any]]:
        """不验证过期/iss/aud、仅解码 payload（用于调试 / 吊销场景）"""
        if not jwt:
            return None
        try:
            return jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm],
                options={
                    "verify_exp": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except Exception:
            return None


# ============================================================================
# SQLite 持久化存储
# ============================================================================

class AuthDatabase:
    """认证系统的 SQLite 持久化存储"""

    def __init__(self, db_path: str = ""):
        if not db_path:
            base = os.environ.get(
                "DATA_DIR",
                os.path.join(os.path.dirname(__file__), "..", "data")
            )
            os.makedirs(base, exist_ok=True)
            db_path = os.path.join(base, "unified_auth.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_users (
                        user_id     TEXT PRIMARY KEY,
                        username    TEXT NOT NULL UNIQUE,
                        email       TEXT NOT NULL DEFAULT '',
                        role        TEXT NOT NULL DEFAULT 'viewer',
                        password_hash TEXT NOT NULL DEFAULT '',
                        password_salt TEXT NOT NULL DEFAULT '',
                        hash_method TEXT NOT NULL DEFAULT 'argon2',
                        is_active   INTEGER NOT NULL DEFAULT 1,
                        is_verified INTEGER NOT NULL DEFAULT 1,
                        display_name TEXT NOT NULL DEFAULT '',
                        team        TEXT NOT NULL DEFAULT '',
                        metadata    TEXT NOT NULL DEFAULT '{}',
                        created_at  TEXT NOT NULL DEFAULT '',
                        last_login  TEXT,
                        login_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        session_id  TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL,
                        token_hash  TEXT NOT NULL,
                        token_type  TEXT NOT NULL DEFAULT 'access',
                        expires_at  TEXT NOT NULL,
                        created_at  TEXT NOT NULL DEFAULT '',
                        ip_address  TEXT,
                        user_agent  TEXT,
                        is_valid    INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_audit_log (
                        log_id      TEXT PRIMARY KEY,
                        user_id     TEXT,
                        action      TEXT NOT NULL,
                        resource    TEXT NOT NULL DEFAULT 'auth',
                        result      TEXT NOT NULL DEFAULT 'success',
                        ip_address  TEXT,
                        details     TEXT NOT NULL DEFAULT '{}',
                        timestamp   TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
                    )
                """)
                # 索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_username ON auth_users(username)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit_log(user_id)")
                conn.commit()
            finally:
                conn.close()

    # ---- 用户 CRUD ----

    def insert_user(self, user: AuthUser) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO auth_users
                    (user_id, username, email, role, password_hash, password_salt,
                     hash_method, is_active, is_verified, display_name, team,
                     metadata, created_at, last_login, login_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.user_id, user.username, user.email, user.role,
                    user.password_hash, user.password_salt, user.hash_method,
                    1 if user.is_active else 0, 1 if user.is_verified else 0,
                    user.display_name, user.team,
                    json.dumps(user.metadata, ensure_ascii=False),
                    user.created_at, user.last_login, user.login_count
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError as e:
                logger.error(f"Insert user failed: {e}")
                return False
            finally:
                conn.close()

    def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                if row:
                    return self._row_to_user(dict(row))
                return None
            finally:
                conn.close()

    def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM auth_users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row:
                    return self._row_to_user(dict(row))
                return None
            finally:
                conn.close()

    def list_users(self, role: str = None, team: str = None,
                   is_active: bool = None, limit: int = 200) -> List[AuthUser]:
        conds = []
        params = []
        if role:
            conds.append("role = ?")
            params.append(role)
        if team:
            conds.append("team = ?")
            params.append(team)
        if is_active is not None:
            conds.append("is_active = ?")
            params.append(1 if is_active else 0)
        # Safe concatenation: WHERE clause built from parameterized conditions
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM auth_users " + where + " ORDER BY created_at DESC LIMIT ?",
                    params + [limit]
                ).fetchall()
                return [self._row_to_user(dict(r)) for r in rows]
            finally:
                conn.close()

    def update_user(self, user_id: str, updates: dict) -> bool:
        # P21 P2 P1 (R2-NEW-01): SQL injection hardening.
        # The previous implementation used ``", ".join(k + ' = ?' for k in
        # filtered)`` then ``f"UPDATE auth_users SET {set_clause} WHERE ..."``
        # which mixes trusted (column names from a static allow-list) with
        # the *values* of those columns in the same f-string. While the
        # column names themselves are gated by ``allowed`` today, the
        # structure lets any future caller that adds an attacker-controlled
        # key slip through. Even with the allow-list, Bandit B608 (and
        # the R2 pentest reproducer) flag the f-string as risky. We now
        # build the SET clause from a *static* table that maps each
        # allowed column to a literal "?" placeholder, so user input never
        # touches the SQL string itself — only the bound parameter list.
        #
        # NOTE: ``metadata`` is a JSON-encoded string column; we re-encode
        # non-string values so we always pass a ``str`` to the DB.
        _COLUMN_BIND = {
            "email": "?",
            "role": "?",
            "is_active": "?",
            "is_verified": "?",
            "display_name": "?",
            "team": "?",
            "metadata": "?",
            "last_login": "?",
            "login_count": "?",
            "password_hash": "?",
            "password_salt": "?",
            "hash_method": "?",
        }
        allowed = set(_COLUMN_BIND)
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return False
        # Column names come ONLY from the static _COLUMN_BIND keys — never
        # from caller input. Bind placeholders are literal "?" characters.
        set_clause = ", ".join(f"{col} = {_COLUMN_BIND[col]}" for col in filtered)
        values: List[Any] = []
        for col, v in filtered.items():
            if col == "metadata" and not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            values.append(v)
        values.append(user_id)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE auth_users SET " + set_clause + " WHERE user_id = ?",
                    values,
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def delete_user(self, user_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM auth_users WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def user_exists(self, username: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def count_users(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM auth_users").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    @staticmethod
    def _row_to_user(row: dict) -> AuthUser:
        try:
            metadata = json.loads(row.get("metadata", "{}"))
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        return AuthUser(
            user_id=row.get("user_id", ""),
            username=row.get("username", ""),
            email=row.get("email", ""),
            role=row.get("role", "viewer"),
            password_hash=row.get("password_hash", ""),
            password_salt=row.get("password_salt", ""),
            hash_method=row.get("hash_method", "argon2"),
            is_active=bool(row.get("is_active", 1)),
            is_verified=bool(row.get("is_verified", 1)),
            display_name=row.get("display_name", ""),
            team=row.get("team", ""),
            metadata=metadata,
            created_at=row.get("created_at", ""),
            last_login=row.get("last_login"),
            login_count=row.get("login_count", 0),
        )


# ============================================================================
# 统一认证管理器
# ============================================================================

class UnifiedAuthManager:
    """
    统一认证管理器
    功能: 用户注册/登录/令牌管理/权限检查/审计日志
    兼容: security/auth.py 的 AuthManager 接口
    """

    def __init__(self, jwt_secret: str = "", db_path: str = "",
                 throttle_config: Optional[BruteForceConfig] = None,
                 throttle_protector: Optional[BruteForceProtector] = None,
                 enable_bruteforce_persistence: Optional[bool] = None):
        # JWT 密钥
        self.jwt_secret = jwt_secret or os.environ.get(
            "JWT_SECRET",
            secrets.token_hex(32)
        )
        self.jwt_manager = JWTManager(self.jwt_secret)
        self.password_manager = PasswordManager()
        self.db = AuthDatabase(db_path)

        # P10R4-1 / P0-4: BruteForce 持久化开关
        # 优先级: 显式参数 > 环境变量 > 默认 False
        # 环境变量: BRUTE_FORCE_PERSISTENCE (true/false/1/0/yes/no)
        if enable_bruteforce_persistence is None:
            _bf_persist_env = os.environ.get("BRUTE_FORCE_PERSISTENCE", "").strip().lower()
            enable_bruteforce_persistence = _bf_persist_env in ("true", "1", "yes", "on")
        self._bruteforce_persistence_enabled = enable_bruteforce_persistence

        # BruteForce 防护 (P10 Sprint D + P10R4-1) — 可注入, 测试用
        # 生产环境: 设 BRUTE_FORCE_PERSISTENCE=true 启用 SQLite 持久化层
        # (多 worker / 跨重启保留 lock state)
        if throttle_protector is not None:
            self.throttle = throttle_protector
        else:
            self.throttle = BruteForceProtector(
                config=throttle_config or BruteForceConfig(),
                enable_persistence=enable_bruteforce_persistence,
                db_path=self.db.db_path,
            )

        # Token Revocation (P10R4-1 / P0-5) — 可注入, 测试用
        # 共享 unified_auth.db (新表 auth_revoked_tokens)
        self.revocation = TokenRevocationStore(db_path=self.db.db_path)

        # P21 P2 P3 / R1-02 fix: audit log writer for state-changing user
        # management actions (user.created / password.changed /
        # user.deleted / user.updated).  Writes to the existing
        # ``auth_audit_log`` table; no schema change.
        self.audit_log = AuditLog(self.db, resource="user")

        # P10R4-1 / HIDDEN-4: 后台 GC 守护线程 (清理过期 revocation 条目)
        # 默认 off (避免污染单测), 生产设 TOKEN_REVOCATION_GC=true 启用
        _enable_gc = os.environ.get("TOKEN_REVOCATION_GC", "").strip().lower() in (
            "true", "1", "yes", "on"
        )
        self._revocation_gc_enabled = _enable_gc
        if _enable_gc:
            _gc_interval = int(os.environ.get("TOKEN_REVOCATION_GC_INTERVAL", "300"))
            self.revocation.start_background_gc(interval_seconds=_gc_interval)
            logger.info(
                "UnifiedAuthManager: token revocation background GC enabled, interval=%ds",
                _gc_interval,
            )

        # 启动时确保至少有一个 admin
        self._ensure_admin_exists()

    # ---- 初始化 ----

    def _ensure_admin_exists(self):
        """确保至少有一个管理员账户 — P11-D-1: 密码从 ADMIN_INITIAL_PASSWORD 注入。

        启动时读 env ``ADMIN_INITIAL_PASSWORD``:
        * 缺省或为空 + production 模式: 抛 ``AdminConfigError`` 立即 fail-fast
        * 缺省 + test 模式 (IMDF_TEST_MODE=1): 退化为 ephemeral random 16 字节密码
          并把密码写 stdout, 防止硬编码 ``Admin@2026!`` 残留
        * 显式提供: 直接使用

        部署时通过 ``.env`` / Vault / KMS 注入, 杜绝源码硬编码密码泄露。
        """
        existing = self.db.get_user_by_username("admin")
        if existing:
            return

        # P11-D-1: 强制从 env 注入, 禁止源码硬编码
        admin_password = os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()
        if not admin_password:
            test_mode = os.environ.get("IMDF_TEST_MODE", "").strip() == "1"
            if test_mode:
                # Test mode: 生成 ephemeral random 密码, 写 stdout (一次性)
                import sys
                admin_password = secrets.token_urlsafe(16)
                print(
                    f"[IMDF_TEST_MODE] Generated ephemeral admin password: "
                    f"{admin_password}",
                    file=sys.stderr,
                )
                logger.warning(
                    "IMDF_TEST_MODE=1 — ephemeral admin password generated; "
                    "set ADMIN_INITIAL_PASSWORD for stable admin login in CI"
                )
            else:
                # Production: fail-fast, 防止默默用弱密码
                raise AdminConfigError(
                    "ADMIN_INITIAL_PASSWORD env var is required to bootstrap "
                    "the default admin account. Set it in .env (e.g. "
                    "`python -c 'import secrets; print(secrets.token_urlsafe(24))'` "
                    "to generate a 32+ char random secret) or in your secret "
                    "manager. The legacy hardcoded default has been removed "
                    "for security reasons (P11-D-1)."
                )

        self._create_user(
            username="admin",
            password=admin_password,
            role=UnifiedRole.ADMIN.value,
            email="admin@nanobot.local",
            display_name="系统管理员",
            team="system",
            is_verified=True,
            actor="system",  # P21 P2 P3: bootstrap actor, not "admin"
        )
        logger.info("Default admin account created from ADMIN_INITIAL_PASSWORD")

    def _create_user(self, username: str, password: str, role: str,
                     email: str = "", display_name: str = "", team: str = "",
                     is_verified: bool = True, metadata: dict = None,
                     actor: Optional[str] = None) -> Optional[AuthUser]:
        """内部创建用户

        Args:
            actor: user_id of the actor performing the creation.  When
                ``None`` (the default), falls back to ``username``
                (self-registration).  The bootstrap path
                (``_ensure_admin_exists``) passes ``"system"``.
        """
        if self.db.user_exists(username):
            logger.warning(f"User already exists: {username}")
            return None

        user_id = f"u-{secrets.token_hex(8)}"
        hash_str, salt, method = self.password_manager.hash_password(password)

        user = AuthUser(
            user_id=user_id,
            username=username,
            email=email or f"{username}@nanobot.local",
            role=UnifiedRole.normalize(role).value,
            password_hash=hash_str,
            password_salt=salt,
            hash_method=method,
            is_active=True,
            is_verified=is_verified,
            display_name=display_name or username,
            team=team,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
            login_count=0,
        )
        if self.db.insert_user(user):
            logger.info(f"User created: {username} (role={user.role}, team={team})")
            # P21 P2 P3 / R1-02: record state-changing action in audit log
            # so forensic queries can answer "who created this user, when?"
            self.audit_log.write(
                action="user.created",
                actor=actor or username,
                target=user.user_id,
                details={
                    "role": user.role,
                    "team": user.team,
                    "email": user.email,
                },
            )
            return user
        return None

    # ---- 公共 API ----

    def register_user(self, username: str, password: str, role: str = "viewer",
                      email: str = "", display_name: str = "", team: str = "",
                      metadata: dict = None) -> Optional[AuthUser]:
        """
        注册新用户
        Args:
            username: 用户名
            password: 明文密码
            role: 角色 (admin/team_lead/reviewer/annotator/viewer)
            email: 邮箱
            display_name: 显示名称
            team: 所属团队 (production/crowdsource/client)
            metadata: 额外元数据
        Returns:
            AuthUser 或 None (用户名已存在)
        """
        return self._create_user(
            username=username, password=password, role=role,
            email=email, display_name=display_name, team=team,
            metadata=metadata
        )

    def login(self, username: str, password: str,
              ip_address: str = None, user_agent: str = None) -> LoginResult:
        """
        带暴力破解防护的登录入口 (P10 Sprint D)。

        流程:
            1. 检查账号 + IP 是否被锁定 (任一锁定 → 返回 LoginResult(status='locked'))
            2. 调用 authenticate() 验证密码
            3. 失败: record_failure(account + ip) → 可能触发锁定
            4. 成功: record_success(account + ip) → 清除计数

        Returns:
            LoginResult 对象, 调用方可按 status 分支处理:
              - 'success' → 200 + tokens
              - 'invalid_credentials' / 'inactive' → 401
              - 'locked' → 429 + Retry-After header
        """
        # 1. 预检锁定
        pre = self.throttle.check_lock(username=username, ip=ip_address)
        if not pre.allowed:
            logger.warning(
                "Login BLOCKED: username=%s ip=%s reason=%s retry_after=%ds",
                username, ip_address, pre.reason, pre.retry_after,
            )
            self._audit(
                "auth.locked",
                username=username,
                result="blocked",
                ip_address=ip_address,
                details={
                    "reason": pre.reason,
                    "lockout_level": pre.lockout_level,
                    "retry_after": pre.retry_after,
                    "failed_count": pre.failed_count,
                },
            )
            return LoginResult(
                status="locked",
                retry_after=pre.retry_after,
                reason=pre.reason,
                locked_dimension="ip" if pre.reason == "ip_locked" else "account",
                lockout_level=pre.lockout_level,
                failed_count=pre.failed_count,
            )

        # 2. 验证凭证
        tokens = self.authenticate(username, password, ip_address=ip_address,
                                   user_agent=user_agent)

        # 3. 成功: 清除失败计数
        if tokens:
            self.throttle.record_success(username=username, ip=ip_address)
            return LoginResult(
                status="success",
                tokens=tokens,
                user=tokens.get("user"),
                reason="ok",
            )

        # 4. 失败: 区分 user_not_found / wrong_password / inactive
        #    都视为一次失败 (减少账号枚举), 但审计日志分开记录
        user = self.db.get_user_by_username(username)
        if not user:
            failed_reason = "user_not_found"
        elif not user.is_active:
            failed_reason = "user_inactive"
        else:
            failed_reason = "wrong_password"

        post = self.throttle.record_failure(username=username, ip=ip_address)

        if not post.allowed:
            # 这次失败触发了新锁定
            logger.warning(
                "Login FAIL → LOCK TRIGGERED: username=%s ip=%s level=%s",
                username, ip_address, post.lockout_level,
            )
            self._audit(
                "auth.locked",
                username=username,
                result="locked",
                ip_address=ip_address,
                details={
                    "reason": failed_reason,
                    "lockout_level": post.lockout_level,
                    "retry_after": post.retry_after,
                    "failed_count": post.failed_count,
                },
            )
            return LoginResult(
                status="locked",
                retry_after=post.retry_after,
                reason=post.reason or failed_reason,
                locked_dimension="ip" if post.reason == "ip_locked" else "account",
                lockout_level=post.lockout_level,
                failed_count=post.failed_count,
            )

        # 未触发锁定, 仍然 invalid_credentials
        if failed_reason == "user_inactive":
            return LoginResult(status="inactive", reason=failed_reason)
        return LoginResult(status="invalid_credentials", reason=failed_reason)

    def authenticate(self, username: str, password: str,
                     ip_address: str = None, user_agent: str = None) -> Optional[Dict[str, Any]]:
        """
        用户认证 → 返回 JWT token pair
        Returns:
            {"access_token": str, "refresh_token": str, "user": dict} 或 None
        """
        user = self.db.get_user_by_username(username)
        if not user:
            logger.warning(f"Authentication failed: user not found: {username}")
            self._audit("auth.failed", username=username, result="failed",
                        ip_address=ip_address, details={"reason": "user_not_found"})
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed: user inactive: {username}")
            self._audit("auth.failed", user.user_id, "failed", ip_address,
                        details={"reason": "user_inactive"})
            return None

        if not self.password_manager.verify_password(
            password, user.password_hash, user.password_salt, user.hash_method
        ):
            logger.warning(f"Authentication failed: wrong password: {username}")
            self._audit("auth.failed", user.user_id, "failed", ip_address,
                        details={"reason": "wrong_password"})
            return None

        # 升级密码哈希 (pbkdf2 → argon2)
        if self.password_manager.needs_rehash(password, user.password_hash, user.hash_method):
            new_hash, _, new_method = self.password_manager.hash_password(password)
            self.db.update_user(user.user_id, {
                "password_hash": new_hash,
                "password_salt": "",
                "hash_method": new_method,
            })
            logger.info(f"Password upgraded to argon2 for user: {username}")

        # 更新登录信息
        now = datetime.now().isoformat()
        self.db.update_user(user.user_id, {
            "last_login": now,
            "login_count": user.login_count + 1,
        })

        # 生成令牌
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        access_token = self.jwt_manager.create_access_token(
            user.user_id, user.username, user.role, permissions
        )
        refresh_token = self.jwt_manager.create_refresh_token(user.user_id)

        self._audit("auth.success", user.user_id, "success", ip_address)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.jwt_manager.access_token_expiry,
            "user": user.to_dict(),
        }

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 access token — 增强版 (P10R4-1)

        流程:
          1. JWT 标准校验 (签名 + iss + aud + exp + jti)
          2. 检查 token-level 吊销 (is_revoked(jti))
          3. 检查 user-level 吊销 (is_user_revoked(sub))
          4. 检查全局吊销 (is_globally_revoked)

        任意一步失败 → return None (与原行为兼容).
        """
        payload = self.jwt_manager.verify_token(token, token_type="access")
        if not payload:
            return None
        # 2. token-level 吊销
        jti = payload.get("jti")
        if jti and self.revocation.is_revoked(jti):
            logger.warning(f"Token revoked (jti={jti[:8]}...): access denied")
            return None
        # 3. user-level 吊销 (改密 / 登出 / 禁用)
        user_id = payload.get("sub")
        if user_id and self.revocation.is_user_revoked(user_id):
            logger.warning(f"User-level token revoked (user={user_id}): access denied")
            return None
        # 4. 全局吊销 (security incident)
        if self.revocation.is_globally_revoked():
            logger.warning("Global token revocation active: access denied")
            return None
        return payload

    # ------------------------------------------------------------------
    # Token Revocation API (P10R4-1 / P0-5)
    # ------------------------------------------------------------------

    def revoke_token(self, token: str, reason: str = "logout",
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        吊销单个 token (通过 jti).

        Args:
            token: JWT 字符串 (会被解码取 jti + exp)
            reason: logout / admin_action / suspicious / etc.
            metadata: 任意附加信息 (IP / user agent)

        Returns:
            True 如果成功加入 revocation list.
        """
        # 用 unsafe decode 拿到 jti + exp (不必校验签名, 之后会再 verify)
        payload = self.jwt_manager.decode_token_unsafe(token)
        if not payload:
            logger.warning("revoke_token: cannot decode token")
            return False
        jti = payload.get("jti")
        if not jti:
            logger.warning("revoke_token: token has no jti claim")
            return False
        exp_dt = payload.get("exp")
        # exp 是 int/float epoch seconds
        import time as _t
        exp_epoch = float(exp_dt) if exp_dt else (_t.time() + 7 * 86400)
        user_id = payload.get("sub", "")
        return self.revocation.revoke(
            jti=jti,
            user_id=user_id,
            reason=reason,
            expires_at_epoch=exp_epoch,
            metadata=metadata or {},
        )

    def revoke_user(self, user_id: str, reason: str = "user_action",
                    metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        吊销某用户的所有 active token (改密/登出/禁用账号).

        Returns: 删除的旧 jti 数.
        """
        return self.revocation.revoke_user(
            user_id=user_id,
            reason=reason,
            metadata=metadata or {},
        )

    def revoke_all(self, reason: str = "security_incident") -> int:
        """紧急全场 token 吊销 (建议同时轮换 JWT_SECRET)."""
        return self.revocation.revoke_all(reason=reason)

    def clear_global_revocation(self) -> bool:
        """
        解除全场 token 吊销 (admin only, P10R4-1 / HIDDEN-5).

        Returns: True 如果之前处于全局吊销状态 (执行了清除).
        """
        return self.revocation.clear_global_revocation()

    def is_globally_revoked(self) -> bool:
        """检查是否处于全局 token 吊销状态."""
        return self.revocation.is_globally_revoked()

    def is_token_revoked(self, jti: str) -> bool:
        return self.revocation.is_revoked(jti)

    def is_user_revoked(self, user_id: str) -> bool:
        return self.revocation.is_user_revoked(user_id)

    def get_revocation_stats(self) -> Dict:
        return self.revocation.stats()

    def gc_revocations(self) -> int:
        return self.revocation.gc()

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """使用 refresh token 获取新的 access token"""
        payload = self.jwt_manager.verify_token(refresh_token, token_type="refresh")
        if not payload:
            return None
        user_id = payload.get("sub")
        user = self.db.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        access_token = self.jwt_manager.create_access_token(
            user.user_id, user.username, user.role, permissions
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.jwt_manager.access_token_expiry,
        }

    def get_user(self, user_id: str = None, username: str = None) -> Optional[AuthUser]:
        """获取用户信息"""
        if user_id:
            return self.db.get_user_by_id(user_id)
        if username:
            return self.db.get_user_by_username(username)
        return None

    def list_users(self, role: str = None, team: str = None,
                   is_active: bool = None) -> List[Dict[str, Any]]:
        """列出用户"""
        users = self.db.list_users(role=role, team=team, is_active=is_active)
        return [u.to_dict() for u in users]

    def delete_user(self, user_id: str, actor: Optional[str] = None) -> bool:
        """删除用户

        Args:
            user_id: 被删除用户
            actor:   执行删除的用户 id (admin), 默认 ``"system"`` 防止
                完全不知道是谁删的 (P21 P2 P3 / R1-02 forensic gap).
        """
        # Capture target metadata BEFORE deletion (the row will be gone
        # after delete).  The audit log is the *only* forensic record of
        # "who deleted what" once the user row is removed.
        target_user = self.db.get_user_by_id(user_id)
        target_username = target_user.username if target_user else None
        target_role = target_user.role if target_user else None

        ok = self.db.delete_user(user_id)
        if ok:
            # P21 P2 P3 / R1-02: record state-changing action in audit log
            # so forensic queries can answer "who deleted this user, when?"
            self.audit_log.write(
                action="user.deleted",
                actor=actor or "system",
                target=user_id,
                details={
                    "username": target_username,
                    "role": target_role,
                },
            )
        return ok

    def update_user(self, user_id: str, updates: dict,
                    actor: Optional[str] = None) -> bool:
        """Public API for user updates (P21 P2 P3 / R1-02 audit fix).

        Wraps ``AuthDatabase.update_user`` and writes a
        ``"user.updated"`` audit entry capturing the diff between
        the previous and new state, so forensic queries can answer
        "who changed role X to Y on user Z, when?".

        Args:
            user_id: target user
            updates: dict of column → new_value (filtered against
                ``_COLUMN_BIND`` allow-list inside ``db.update_user``)
            actor:   executing user id (admin / self), default ``"system"``.

        Notes:
            * Internal callers (e.g. ``authenticate`` upgrading the
              password hash) continue to use ``db.update_user``
              directly — those writes are NOT audited (they are not
              user-initiated state changes in the R1-02 sense).
        """
        # Snapshot the pre-state so we can compute a meaningful diff
        # in the audit entry (without snapshot, "what changed" is unknown).
        before = self.db.get_user_by_id(user_id)
        if not before:
            return False

        ok = self.db.update_user(user_id, updates)
        if not ok:
            return False

        # Compute a minimal diff (only columns that actually changed).
        diff: Dict[str, Any] = {}
        for key, new_val in (updates or {}).items():
            if not hasattr(before, key):
                continue
            old_val = getattr(before, key, None)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}

        # P21 P2 P3 / R1-02: record state-changing action in audit log.
        self.audit_log.write(
            action="user.updated",
            actor=actor or "system",
            target=user_id,
            details={
                "username": before.username,
                "changed_fields": sorted(diff.keys()),
                "diff": diff,
            } if diff else {
                "username": before.username,
                "changed_fields": [],
            },
        )
        return True

    def check_permission(self, user_id: str, required_permission: str) -> bool:
        """检查用户是否有某权限"""
        user = self.db.get_user_by_id(user_id)
        if not user or not user.is_active:
            return False
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        # admin 拥有所有权限
        if user.role == UnifiedRole.ADMIN.value:
            return True
        return required_permission in permissions

    def get_user_permissions(self, user_id: str) -> List[str]:
        """获取用户的所有权限"""
        user = self.db.get_user_by_id(user_id)
        if not user:
            return []
        return ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])

    def change_password(self, user_id: str, old_password: str,
                        new_password: str) -> bool:
        """
        修改密码 + 强制吊销该用户所有 active token (P10R4-1).

        OWASP A07 对标: 改密必须使旧 token 立即失效, 否则攻击者持有的 token
        在密码修改后仍可访问 (直到自然过期).
        """
        user = self.db.get_user_by_id(user_id)
        if not user:
            return False
        if not self.password_manager.verify_password(
            old_password, user.password_hash, user.password_salt, user.hash_method
        ):
            return False
        new_hash, new_salt, new_method = self.password_manager.hash_password(new_password)
        ok = self.db.update_user(user.user_id, {
            "password_hash": new_hash,
            "password_salt": new_salt,
            "hash_method": new_method,
        })
        if ok:
            # 强制吊销该用户所有 token (旧 token 不能继续访问)
            deleted = self.revoke_user(
                user_id=user_id,
                reason="password_changed",
                metadata={"actor": user_id, "self_service": True},
            )
            # P21 P2 P3 / R1-02: record password change in audit log
            # so forensic queries can answer "who changed this password, when?"
            self.audit_log.write(
                action="password.changed",
                actor=user_id,
                target=user_id,
                details={
                    "tokens_revoked": deleted,
                },
            )
            logger.info(
                "Password changed for user %s — revoked %d old token markers",
                user_id, deleted,
            )
        return ok

    # ---- 内部 ----

    def _audit(self, action: str, user_id: str = "", result: str = "success",
               ip_address: str = None, details: dict = None,
               username: str = ""):
        """记录审计日志"""
        log_id = f"log_{secrets.token_hex(8)}"
        with self.db._lock:
            conn = self.db._get_conn()
            try:
                conn.execute("""
                    INSERT INTO auth_audit_log
                    (log_id, user_id, action, resource, result, ip_address, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id,
                    user_id or username,
                    action,
                    "auth",
                    result,
                    ip_address,
                    json.dumps(details or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Audit log failed: {e}")
            finally:
                conn.close()

    def get_audit_logs(self, user_id: str = None, limit: int = 100) -> List[dict]:
        """获取审计日志"""
        with self.db._lock:
            conn = self.db._get_conn()
            try:
                if user_id:
                    rows = conn.execute(
                        "SELECT * FROM auth_audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                        (user_id, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM auth_audit_log ORDER BY timestamp DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


# ============================================================================
# 全局单例
# ============================================================================

_auth_instance: Optional[UnifiedAuthManager] = None
_auth_lock = threading.Lock()


def get_unified_auth(jwt_secret: str = "", db_path: str = "") -> UnifiedAuthManager:
    """获取统一认证管理器单例"""
    global _auth_instance
    if _auth_instance is None:
        with _auth_lock:
            if _auth_instance is None:
                _auth_instance = UnifiedAuthManager(
                    jwt_secret=jwt_secret,
                    db_path=db_path,
                )
    return _auth_instance


def reset_unified_auth():
    """重置单例（主要用于测试）"""
    global _auth_instance
    with _auth_lock:
        _auth_instance = None


# ============================================================================
# FastAPI 兼容的路由辅助
# ============================================================================

def create_auth_dependency(auth: UnifiedAuthManager = None):
    """
    创建 FastAPI 认证依赖
    Usage:
        from auth.unified_auth import create_auth_dependency, get_unified_auth
        auth = get_unified_auth()
        require_auth = create_auth_dependency(auth)

        @router.get("/protected")
        async def protected_route(current_user = Depends(require_auth)):
            return {"user": current_user}
    """
    from fastapi import Depends, HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    security = HTTPBearer()
    _auth = auth or get_unified_auth()

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Dict[str, Any]:
        token = credentials.credentials
        payload = _auth.verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        user = _auth.get_user(user_id=payload.get("sub"))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user.to_dict()

    return get_current_user


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'UnifiedRole', 'ROLE_PERMISSIONS',
    'AuthUser', 'PasswordManager', 'JWTManager',
    'AuthDatabase', 'UnifiedAuthManager',
    'get_unified_auth', 'reset_unified_auth',
    'create_auth_dependency',
]
